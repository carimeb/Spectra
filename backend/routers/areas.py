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


def _resolve_root_id(db, root_id: str | None) -> str:
    """Resolve o rootId pedido (ou a raiz da organização, se vazio)."""
    if root_id is None:
        root = db.areas.find_one({"parentId": None})
        if not root:
            raise HTTPException(status_code=404, detail="nenhuma área raiz encontrada (rode o seed)")
        return root["_id"]
    if not db.areas.find_one({"_id": root_id}):
        raise HTTPException(status_code=404, detail=f"área {root_id!r} não encontrada")
    return root_id


@router.get("/tree/query", summary="Consultas reais da árvore de áreas (para exibir na UI)")
def areas_tree_query(rootId: str | None = Query(None, description="Raiz da subárvore; vazio = raiz da organização")):
    """Retorna as mesmas consultas que `/tree` executa: o `$graphLookup` que desce a
    hierarquia (substitui a CTE recursiva) e a agregação de repositórios por área."""
    root_id = _resolve_root_id(get_db(), rootId)
    return {"steps": [
        {"title": "descer a hierarquia inteira a partir da raiz (era: CTE recursiva em Area.ParentId)",
         "collection": "areas", "pipeline": build_descendants_pipeline(root_id)},
        {"title": "contagem de repositórios por área (anexada a cada nó da árvore)",
         "collection": "repositories", "pipeline": repo_counts_pipeline()},
    ]}


@router.get("/tree", summary="Árvore de áreas (query-herói B)")
def areas_tree(rootId: str | None = Query(None, description="Raiz da subárvore; vazio = raiz da organização")):
    """Retorna a hierarquia de áreas como JSON aninhado `{id, name, level, repoCount, children}`,
    usando `$graphLookup` descendo `Area.ParentId`. Com contagem de repositórios por nó.
    """
    db = get_db()
    root_id = _resolve_root_id(db, rootId)
    result = list(db.areas.aggregate(build_descendants_pipeline(root_id)))
    root_doc = result[0]
    areas = [root_doc] + root_doc.get("descendants", [])

    counts = {r["_id"]: r["count"] for r in db.repositories.aggregate(repo_counts_pipeline())}
    return build_tree(areas, counts, root_id)
