"""/api/graph/* — análise de impacto (query-herói A) e vizinhança do grafo de arquitetura."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.db import get_db
from backend.pipelines.impact import build_impact_pipeline, framework_match
from backend.pipelines.neighborhood import build_neighborhood_pipeline

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


@router.get("/impact/query", summary="Pipeline real da análise de impacto (para exibir na UI)")
def impact_query(framework: str = Query("net6.0", description="net48, net6.0 ou net8.0")):
    """Retorna o mesmo pipeline de agregação que `/impact` executa, para a UI mostrar
    ao desenvolvedor exatamente a query que roda (e ele reproduzir na app dele)."""
    try:
        return {"collection": "dependencies", "pipeline": build_impact_pipeline(framework)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/components", summary="Lista leve de componentes (id/name/type) para busca")
def list_components(q: str | None = Query(None), limit: int = Query(300, ge=1, le=1000)):
    db = get_db()
    query = {"name": {"$regex": q, "$options": "i"}} if q else {}
    docs = db.archComponents.find(query, {"name": 1, "type": 1}).sort("name", 1).limit(limit)
    return [{"id": d["_id"], "name": d["name"], "type": d["type"]} for d in docs]


@router.get("/component/{component_id}", summary="Vizinhança de um componente (para vis-network)")
def component_neighborhood(component_id: str, depth: int = Query(2, ge=1, le=4)):
    """Retorna `{nodes, edges}` prontos para o vis-network: o componente, quem ele
    referencia (downstream) e quem o referencia (upstream), até `depth` saltos.
    Usa `$graphLookup` nos dois sentidos sobre `archComponents.relations`.
    """
    db = get_db()
    pipeline = build_neighborhood_pipeline(component_id, depth)
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


@router.get("/component/{component_id}/query", summary="Pipeline real da vizinhança (para exibir na UI)")
def component_neighborhood_query(component_id: str, depth: int = Query(2, ge=1, le=4)):
    """Retorna o mesmo pipeline de `$graphLookup` que `/component/{id}` executa,
    para a UI mostrar ao desenvolvedor a travessia real do grafo de arquitetura."""
    return {"collection": "archComponents", "pipeline": build_neighborhood_pipeline(component_id, depth)}
