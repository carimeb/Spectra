"""/api/graph/* — análise de impacto (query-herói A) e vizinhança do grafo de arquitetura."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.db import get_db
from backend.pipelines.impact import build_impact_pipeline, framework_match

router = APIRouter(prefix="/graph", tags=["Grafo & Impacto"])


@router.get("/impact", summary="Impacto de migração .NET (query-herói A)")
def impact(framework: str = Query("net6.0", description="Versão .NET de origem: net48, net6.0 ou net8.0")):
    """Quais BUs são afetadas ao migrar apps de uma versão .NET, quantas aplicações,
    quantos repositórios, os responsáveis e um `effortScore` (com breakdown explicativo).

    A versão .NET é derivada da dependência de runtime; o impacto sobe pela hierarquia
    de áreas (grafo operacional). Retorna a lista de BUs ordenada por nº de aplicações.
    """
    try:
        pipeline = build_impact_pipeline(framework)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return list(get_db().dependencies.aggregate(pipeline))


@router.get("/component/{component_id}", summary="Vizinhança de um componente (para vis-network)")
def component_neighborhood(component_id: str, depth: int = Query(2, ge=1, le=4)):
    """Retorna `{nodes, edges}` prontos para o vis-network: o componente, quem ele
    referencia (downstream) e quem o referencia (upstream), até `depth` saltos.
    Usa `$graphLookup` nos dois sentidos sobre `archComponents.relations`.
    """
    db = get_db()
    max_depth = max(0, depth - 1)
    pipeline = [
        {"$match": {"_id": component_id}},
        # downstream: seguindo relations.targetId (o que este componente usa)
        {"$graphLookup": {
            "from": "archComponents", "startWith": "$relations.targetId",
            "connectFromField": "relations.targetId", "connectToField": "_id",
            "as": "downstream", "maxDepth": max_depth,
        }},
        # upstream: quem aponta para este componente (quem depende dele)
        {"$graphLookup": {
            "from": "archComponents", "startWith": "$_id",
            "connectFromField": "_id", "connectToField": "relations.targetId",
            "as": "upstream", "maxDepth": max_depth,
        }},
    ]
    result = list(db.archComponents.aggregate(pipeline))
    if not result:
        raise HTTPException(status_code=404, detail=f"componente {component_id!r} não encontrado")

    root = result[0]
    docs: dict[str, dict] = {root["_id"]: root}
    for d in root.get("downstream", []) + root.get("upstream", []):
        docs[d["_id"]] = d

    nodes = [{"id": d["_id"], "label": d["name"], "type": d["type"]} for d in docs.values()]
    edges = []
    for d in docs.values():
        for rel in d.get("relations", []):
            if rel["targetId"] in docs:
                edges.append({"from": d["_id"], "to": rel["targetId"]})
    return {"nodes": nodes, "edges": edges}
