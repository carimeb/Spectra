"""/api/schema/* — esquema flexível sem migração (query-herói C).

Adicionar um atributo nomeado ou uma relação a um componente e re-executar as
queries/o grafo sem nenhuma migração, tabela nova ou deploy.
"""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from backend.db import get_db

router = APIRouter(prefix="/schema", tags=["Esquema Flexível"])

_KEY_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")


class AttributeBody(BaseModel):
    key: str
    value: Any

    @field_validator("key")
    @classmethod
    def _valid_key(cls, v: str) -> str:
        if not _KEY_RE.match(v):
            raise ValueError("key deve começar com letra e conter só letras/dígitos/_ (sem pontos)")
        return v


class RelationBody(BaseModel):
    targetId: str  # id de outro archComponent (grafo componente↔componente, não-tipado)


@router.get("/components/{component_id}", summary="Documento cru do componente")
def get_component(component_id: str):
    doc = get_db().archComponents.find_one({"_id": component_id})
    if not doc:
        raise HTTPException(status_code=404, detail=f"componente {component_id!r} não encontrado")
    return doc


@router.post("/components/{component_id}/attributes", summary="Adicionar atributo (sem migração)")
def add_attribute(component_id: str, body: AttributeBody):
    """`$set` em `attributes.<key>` — nenhum ALTER TABLE, nenhuma coluna nova."""
    db = get_db()
    res = db.archComponents.update_one(
        {"_id": component_id}, {"$set": {f"attributes.{body.key}": body.value}}
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail=f"componente {component_id!r} não encontrado")
    return db.archComponents.find_one({"_id": component_id})


@router.post("/components/{component_id}/relations", summary="Adicionar relação (valida o alvo)")
def add_relation(component_id: str, body: RelationBody):
    """Adiciona `{targetId}` ao array `relations` (aresta não-tipada componente↔componente).
    Valida que o alvo existe e evita duplicatas/auto-referência."""
    db = get_db()
    if not db.archComponents.find_one({"_id": component_id}):
        raise HTTPException(status_code=404, detail=f"componente {component_id!r} não encontrado")
    if body.targetId == component_id:
        raise HTTPException(status_code=400, detail="um componente não pode referenciar a si mesmo")
    if not db.archComponents.find_one({"_id": body.targetId}):
        raise HTTPException(status_code=400, detail=f"alvo {body.targetId!r} não existe em archComponents")

    db.archComponents.update_one(
        {"_id": component_id},
        {"$addToSet": {"relations": {"targetId": body.targetId}}},
    )
    return db.archComponents.find_one({"_id": component_id})
