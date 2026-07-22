"""Query-herói B — Hierarquia de áreas recursiva.

`$graphLookup` DESCENDO a adjacência `Area.ParentId` (substitui a CTE recursiva /
a tabela de caminho materializado `AreaPath`). O router monta a árvore aninhada e
anexa a contagem de repositórios por nó.
"""
from __future__ import annotations


def build_descendants_pipeline(root_id: str) -> list[dict]:
    """Retorna o nó raiz + todos os descendentes (flat, com profundidade)."""
    return [
        {"$match": {"_id": root_id}},
        {"$graphLookup": {
            "from": "areas",
            "startWith": "$_id",
            "connectFromField": "_id",     # de cada área...
            "connectToField": "parentId",  # ...acha quem a tem como parentId (filhos)
            "as": "descendants",
            "depthField": "depth",
        }},
    ]


def repo_counts_pipeline() -> list[dict]:
    """Contagem de repositórios agregada por área (para anexar em cada nó)."""
    return [{"$group": {"_id": "$areaId", "count": {"$sum": 1}}}]


def build_tree(areas: list[dict], repo_counts: dict[str, int], root_id: str) -> dict:
    """Monta JSON aninhado {id, name, level, repoCount, children:[...]} a partir do flat."""
    by_parent: dict[str | None, list[dict]] = {}
    for a in areas:
        by_parent.setdefault(a.get("parentId"), []).append(a)

    def node(area: dict) -> dict:
        children = sorted(by_parent.get(area["_id"], []), key=lambda x: x["name"])
        return {
            "id": area["_id"],
            "name": area["name"],
            "level": area["level"],
            "repoCount": repo_counts.get(area["_id"], 0),
            "children": [node(c) for c in children],
        }

    root = next(a for a in areas if a["_id"] == root_id)
    return node(root)
