"""Cliente MongoDB singleton e helpers compartilhados.

Toda a aplicação (API, seed, agente) obtém o banco por aqui, para que exista
um único ponto de configuração de conexão. As credenciais vêm sempre do .env
(nunca hardcoded).
"""
from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database

load_dotenv()

# Nomes das 6 collections — centralizados para evitar strings soltas pelo código.
COLLECTIONS = [
    "users",
    "areas",
    "archComponents",
    "repositories",
    "dependencies",
    "vulnerabilities",
]


@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    """Retorna um MongoClient único por processo (cacheado)."""
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        raise RuntimeError(
            "MONGODB_URI não definido. Copie .env.example para .env e preencha a "
            "connection string do seu cluster Atlas."
        )
    return MongoClient(uri, appname="spectra")


def get_db() -> Database:
    """Retorna o Database configurado em MONGODB_DB (default: 'spectra')."""
    db_name = os.environ.get("MONGODB_DB", "spectra")
    return get_client()[db_name]


def ping() -> bool:
    """Testa a conexão com o Atlas. Levanta exceção do driver se falhar."""
    get_client().admin.command("ping")
    return True


def collection_counts() -> dict[str, int]:
    """Contagem de documentos por collection — usado por /api/health e pelo seed."""
    db = get_db()
    return {name: db[name].count_documents({}) for name in COLLECTIONS}
