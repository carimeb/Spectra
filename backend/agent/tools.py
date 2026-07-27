"""Ferramentas do Copilot.

Dois grafos independentes (fiel à origem), e as ferramentas respeitam a separação:
  - ARQUITETURA: `hybrid_search` (texto sobre name/description) e `graph_traversal`
    ($graphLookup em archComponents.relations, nos dois sentidos).
  - OPERACIONAL: `impact_analysis` (query-herói A) e `area_info` (áreas + responsáveis).

Escada de degradação da busca (nunca erro, sempre resposta):
  1. embeddings configurados no runtime -> busca híbrida (full-text + vetorial, rank fusion);
  2. sem embeddings no runtime -> full-text puro via Atlas Search (mesma assinatura);
  3. índice Atlas Search indisponível -> regex simples em name/description.
"""
from __future__ import annotations

import json
import logging

from langchain_core.tools import tool
from pymongo.errors import OperationFailure

from backend.db import get_db
from backend.embeddings import get_embeddings
from backend.pipelines.impact import build_impact_pipeline

log = logging.getLogger("spectra.copilot")

SEARCH_INDEX = "default"
VECTOR_INDEX = "vector_index"


def _compact(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


# --------------------------------------------------------------------------- #
# Busca híbrida (grafo de ARQUITETURA)
# --------------------------------------------------------------------------- #
def _fulltext_search(query: str, limit: int = 5) -> list[dict]:
    db = get_db()
    pipeline = [
        {"$search": {"index": SEARCH_INDEX,
                     "text": {"query": query, "path": ["name", "description"]}}},
        {"$limit": limit},
        {"$project": {"name": 1, "type": 1, "description": 1,
                      "score": {"$meta": "searchScore"}}},
    ]
    return list(db.archComponents.aggregate(pipeline))


def _regex_search(query: str, limit: int = 5) -> list[dict]:
    db = get_db()
    docs = db.archComponents.find(
        {"$or": [{"name": {"$regex": query, "$options": "i"}},
                 {"description": {"$regex": query, "$options": "i"}}]},
        {"name": 1, "type": 1, "description": 1},
    ).limit(limit)
    return list(docs)


def _vector_search(query: str, limit: int = 5) -> list[dict] | None:
    """Busca vetorial sobre archComponents.embedding; None se não configurada."""
    client = get_embeddings()
    if client is None:
        return None
    db = get_db()
    if not db.archComponents.find_one({"embedding": {"$exists": True}}, {"_id": 1}):
        return None
    vector = client.embed_query(query)
    pipeline = [
        {"$vectorSearch": {"index": VECTOR_INDEX, "path": "embedding",
                           "queryVector": vector, "numCandidates": 50, "limit": limit}},
        {"$project": {"name": 1, "type": 1, "description": 1,
                      "score": {"$meta": "vectorSearchScore"}}},
    ]
    return list(db.archComponents.aggregate(pipeline))


def _rank_fusion(lists: list[list[dict]], k: int = 60, limit: int = 5) -> list[dict]:
    """Reciprocal rank fusion entre listas de resultados (por _id)."""
    scores: dict[str, float] = {}
    docs: dict[str, dict] = {}
    for results in lists:
        for rank, doc in enumerate(results):
            _id = doc["_id"]
            scores[_id] = scores.get(_id, 0.0) + 1.0 / (k + rank + 1)
            docs.setdefault(_id, doc)
    ordered = sorted(scores, key=scores.get, reverse=True)[:limit]
    return [docs[_id] for _id in ordered]


@tool
def hybrid_search(query: str) -> str:
    """Busca componentes de ARQUITETURA por texto livre (nome e descrição), combinando
    busca textual e semântica. Use quando o usuário citar um sistema/tema sem dar o id
    exato (ex.: "algo relacionado a conciliação de pagamentos"). Retorna id, name, type
    e description dos componentes mais relevantes; use o id em graph_traversal."""
    try:
        text = _fulltext_search(query)
    except OperationFailure:
        log.warning("Atlas Search indisponível; caindo para regex.")
        text = _regex_search(query)

    try:
        vector = _vector_search(query)
    except Exception as exc:  # noqa: BLE001 — embeddings nunca derrubam a busca
        log.warning("busca vetorial indisponível (%s); usando só full-text.", type(exc).__name__)
        vector = None

    results = _rank_fusion([text, vector]) if vector else text[:5]
    out = [{"id": d["_id"], "name": d["name"], "type": d["type"],
            "description": (d.get("description") or "")[:180]} for d in results]
    return _compact(out)


# --------------------------------------------------------------------------- #
# Travessia do grafo de ARQUITETURA
# --------------------------------------------------------------------------- #
def _resolve_component(ref: str) -> dict | None:
    db = get_db()
    doc = db.archComponents.find_one({"_id": ref}, {"name": 1, "type": 1})
    if doc:
        return doc
    return db.archComponents.find_one(
        {"name": {"$regex": f"^{ref}$", "$options": "i"}}, {"name": 1, "type": 1}
    )


@tool
def graph_traversal(start: str, direction: str = "up", max_depth: int = 3) -> str:
    """Percorre o grafo de ARQUITETURA a partir de um componente (id ou nome exato).
    direction="up": quem depende dele (impacto/dependentes); direction="down": do que
    ele depende. Use para perguntas como "quais sistemas dependem de X" ou "o que X usa".
    Retorna os componentes alcançados com a profundidade de cada um."""
    comp = _resolve_component(start)
    if not comp:
        return _compact({"error": f"componente '{start}' não encontrado; use hybrid_search antes"})

    db = get_db()
    max_depth = max(0, min(int(max_depth), 5) - 1)
    if direction == "down":
        lookup = {"startWith": "$relations.targetId",
                  "connectFromField": "relations.targetId", "connectToField": "_id"}
    else:
        lookup = {"startWith": "$_id",
                  "connectFromField": "_id", "connectToField": "relations.targetId"}
    pipeline = [
        {"$match": {"_id": comp["_id"]}},
        {"$graphLookup": {"from": "archComponents", **lookup,
                          "as": "found", "depthField": "depth", "maxDepth": max_depth}},
        {"$project": {"found.name": 1, "found.type": 1, "found._id": 1, "found.depth": 1}},
    ]
    result = list(db.archComponents.aggregate(pipeline))
    found = sorted(result[0].get("found", []), key=lambda d: (d["depth"], d["name"])) if result else []
    return _compact({
        "start": {"id": comp["_id"], "name": comp["name"]},
        "direction": "quem depende dele" if direction == "up" else "do que ele depende",
        "count": len(found),
        "components": [{"id": d["_id"], "name": d["name"], "type": d["type"],
                        "depth": int(d["depth"]) + 1} for d in found[:30]],
    })


# --------------------------------------------------------------------------- #
# Grafo OPERACIONAL: impacto de migração e áreas/responsáveis
# --------------------------------------------------------------------------- #
@tool
def impact_analysis(framework: str = "net6.0") -> str:
    """Analisa o impacto de migrar as aplicações de uma versão .NET (net48, net6.0 ou
    net8.0) no grafo OPERACIONAL: quais BUs são afetadas, quantas aplicações e
    repositórios, os responsáveis e o esforço estimado (com detalhamento). Use para
    perguntas de migração/impacto por área de negócio."""
    try:
        pipeline = build_impact_pipeline(framework)
    except ValueError as exc:
        return _compact({"error": str(exc)})
    rows = list(get_db().dependencies.aggregate(pipeline))
    out = [{
        "bu": r["bu"]["name"], "appCount": r["appCount"], "repoCount": r["repoCount"],
        "effortScore": r["effortScore"], "effortBreakdown": r["effortBreakdown"],
        "responsibles": [m["name"] for m in r.get("managers", [])],
    } for r in rows]
    return _compact({"framework": framework, "busAffected": len(out), "bus": out})


@tool
def area_info(name: str) -> str:
    """Consulta uma área organizacional pelo nome (ex.: "Cartões"): nível, responsáveis
    (gestor e tech lead), quantidade de repositórios e a cadeia de áreas acima dela.
    Use para perguntas sobre responsáveis, estrutura organizacional ou uma BU/squad."""
    db = get_db()
    area = db.areas.find_one({"name": {"$regex": f"^{name}$", "$options": "i"}})
    if not area:
        area = db.areas.find_one({"name": {"$regex": name, "$options": "i"}})
    if not area:
        return _compact({"error": f"área '{name}' não encontrada"})

    users = {u["_id"]: u for u in db.users.find(
        {"_id": {"$in": [area.get("managerId"), area.get("techLeadId")]}})}
    chain, parent_id = [], area.get("parentId")
    while parent_id:
        parent = db.areas.find_one({"_id": parent_id}, {"name": 1, "level": 1, "parentId": 1})
        if not parent:
            break
        chain.append({"name": parent["name"], "level": parent["level"]})
        parent_id = parent.get("parentId")

    def _person(uid):
        u = users.get(uid)
        return {"name": u["name"], "email": u["email"]} if u else None

    return _compact({
        "id": area["_id"], "name": area["name"], "level": area["level"],
        "manager": _person(area.get("managerId")),
        "techLead": _person(area.get("techLeadId")),
        "repoCount": db.repositories.count_documents({"areaId": area["_id"]}),
        "parentChain": chain,
    })


ALL_TOOLS = [hybrid_search, graph_traversal, impact_analysis, area_info]
