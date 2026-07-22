"""/api/areas/* — hierarquia de áreas recursiva (query-herói B)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.db import get_db
from backend.pipelines.hierarchy import (
    build_descendants_pipeline,
    build_tree,
    repo_counts_pipeline,
)

router = APIRouter(prefix="/areas", tags=["Áreas"])


@router.get("/tree", summary="Árvore de áreas (query-herói B)")
def areas_tree(rootId: str | None = Query(None, description="Raiz da subárvore; vazio = raiz da organização")):
    """Retorna a hierarquia de áreas como JSON aninhado `{id, name, level, repoCount, children}`,
    usando `$graphLookup` descendo `Area.ParentId`. Com contagem de repositórios por nó.
    """
    db = get_db()

    root_id = rootId
    if root_id is None:
        root = db.areas.find_one({"parentId": None})
        if not root:
            raise HTTPException(status_code=404, detail="nenhuma área raiz encontrada (rode o seed)")
        root_id = root["_id"]
    elif not db.areas.find_one({"_id": root_id}):
        raise HTTPException(status_code=404, detail=f"área {root_id!r} não encontrada")

    result = list(db.areas.aggregate(build_descendants_pipeline(root_id)))
    root_doc = result[0]
    areas = [root_doc] + root_doc.get("descendants", [])

    counts = {r["_id"]: r["count"] for r in db.repositories.aggregate(repo_counts_pipeline())}
    return build_tree(areas, counts, root_id)
