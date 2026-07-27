"""Criação de índices: regulares + Atlas Search + Atlas Vector Search.

Idempotente: "índice já existe" é tratado como sucesso. Os índices de busca
(Atlas Search / Vector Search) são criados via pymongo `create_search_index`;
eles ficam disponíveis de forma assíncrona no Atlas (BUILDING -> READY).
"""
from __future__ import annotations

from pymongo.database import Database
from pymongo.errors import OperationFailure
from pymongo.operations import SearchIndexModel

from backend.embeddings import EXPECTED_DIMS

SEARCH_INDEX_NAME = "default"
VECTOR_INDEX_NAME = "vector_index"


def _safe(fn, *args, **kwargs) -> str:
    """Executa criação de índice tolerando 'já existe'."""
    try:
        return fn(*args, **kwargs)
    except OperationFailure as exc:
        msg = str(exc).lower()
        if "already exists" in msg or "indexoptionsconflict" in msg or "duplicate" in msg:
            return "already-exists"
        raise


def create_regular_indexes(db: Database) -> None:
    _safe(db.archComponents.create_index, "relations.targetId")
    _safe(db.areas.create_index, "parentId")
    _safe(db.dependencies.create_index, "repositoryId")
    # 'name' (+ version) é o pivô da derivação de framework da análise de impacto
    _safe(db.dependencies.create_index, [("name", 1), ("version", 1)])
    _safe(db.vulnerabilities.create_index, "repositoryId")
    _safe(db.repositories.create_index, "areaId")


def create_search_index(db: Database) -> None:
    """Atlas Search full-text sobre name + description (analyzer português)."""
    model = SearchIndexModel(
        definition={
            "mappings": {
                "dynamic": False,
                "fields": {
                    "name": {"type": "string", "analyzer": "lucene.portuguese"},
                    "description": {"type": "string", "analyzer": "lucene.portuguese"},
                },
            }
        },
        name=SEARCH_INDEX_NAME,
    )
    _safe(db.archComponents.create_search_index, model)


def create_vector_index(db: Database) -> None:
    """Atlas Vector Search em archComponents.embedding (512 dims, cosine).

    Só deve ser chamado quando os documentos têm embedding.
    """
    model = SearchIndexModel(
        definition={
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": EXPECTED_DIMS,
                    "similarity": "cosine",
                }
            ]
        },
        name=VECTOR_INDEX_NAME,
        type="vectorSearch",
    )
    _safe(db.archComponents.create_search_index, model)


def create_all(db: Database, with_vector: bool) -> list[str]:
    """Cria todos os índices. Retorna a lista de nomes de índices de busca criados."""
    created = []
    create_regular_indexes(db)
    create_search_index(db)
    created.append(SEARCH_INDEX_NAME)
    if with_vector:
        create_vector_index(db)
        created.append(VECTOR_INDEX_NAME)
    return created
