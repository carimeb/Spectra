"""/api/repositories — lista filtrável + drilldown com vulnerabilidades."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.db import get_db
from backend.pipelines.impact import framework_match

router = APIRouter(prefix="/repositories", tags=["Repositórios"])


@router.get("", summary="Lista paginada de repositórios (com filtros)")
def list_repositories(
    deprecated: bool | None = Query(None),
    framework: str | None = Query(None, description="net48, net6.0 ou net8.0 (derivado das dependências)"),
    areaId: str | None = Query(None),
    q: str | None = Query(None, description="busca por nome"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
):
    db = get_db()
    query: dict = {}
    if deprecated is not None:
        query["analysis.isDeprecated"] = deprecated
    if areaId:
        query["areaId"] = areaId
    if q:
        query["name"] = {"$regex": q, "$options": "i"}
    if framework:
        try:
            match = framework_match(framework)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        # framework é DERIVADO: filtra pelos repos cuja dependência de runtime bate
        repo_ids = db.dependencies.distinct("repositoryId", match)
        query["_id"] = {"$in": repo_ids}

    total = db.repositories.count_documents(query)
    items = list(db.repositories.find(query).sort("name", 1).skip(skip).limit(limit))
    return {"total": total, "limit": limit, "skip": skip, "items": items}


@router.get("/{repository_id}", summary="Documento completo + vulnerabilidades do repo")
def get_repository(repository_id: str):
    db = get_db()
    repo = db.repositories.find_one({"_id": repository_id})
    if not repo:
        raise HTTPException(status_code=404, detail=f"repositório {repository_id!r} não encontrado")
    vulns = list(db.vulnerabilities.find({"repositoryId": repository_id}))
    return {"repository": repo, "vulnerabilities": vulns}
