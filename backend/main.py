"""App FastAPI do Spectra: monta os routers da API e serve o frontend estático.

Rodar: `uvicorn backend.main:app --reload`
Docs interativas (usadas na demo): http://localhost:8000/docs
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.db import collection_counts, ping
from backend.routers import areas, graph, repositories, schema_flex

app = FastAPI(
    title="Spectra API",
    description="Engineering intelligence, decomposed — API de grafo, áreas, "
    "esquema flexível e repositórios sobre MongoDB Atlas.",
    version="0.2.0",
)

# CORS liberado para desenvolvimento local (demo).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (graph.router, areas.router, schema_flex.router, repositories.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health", tags=["Saúde"], summary="Ping no Atlas + contagem por collection")
def health():
    try:
        ping()
        return {"status": "ok", "collections": collection_counts()}
    except Exception as exc:  # noqa: BLE001 — resposta amigável, sem stacktrace na UI
        return {"status": "degraded", "detail": "não foi possível conectar ao banco"}


# Frontend estático (Fase 3). Montado por último para não capturar as rotas /api.
_FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.isdir(_FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIR, html=True), name="frontend")
