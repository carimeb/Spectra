"""Vizinhança de um componente no grafo de ARQUITETURA (módulo Mapa & Grafo).

Dois `$graphLookup` sobre `archComponents.relations` (arestas não-tipadas,
espelhando ArchComponentRelation): downstream segue `relations.targetId` (o que
o componente usa) e upstream inverte a direção (quem depende dele). O router
converte o resultado em `{nodes, edges}` para o vis-network, e a UI exibe este
mesmo pipeline no painel de query da tela.
"""
from __future__ import annotations


def build_neighborhood_pipeline(component_id: str, depth: int) -> list[dict]:
    # depth = nº de saltos a partir do componente; maxDepth do $graphLookup é 0-based
    max_depth = max(0, depth - 1)
    return [
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
