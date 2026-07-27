"""/api/copilot/chat — chat do agente.

Erros de auth/quota do gateway viram mensagem amigável (nunca stacktrace na UI
nem token em log). Sem LLM configurado, o endpoint responde orientando a
configuração em vez de falhar.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/copilot", tags=["Copilot"])
log = logging.getLogger("spectra.copilot")

FRIENDLY_UNAVAILABLE = (
    "O serviço de IA está indisponível no momento. Verifique as credenciais do "
    "gateway no .env (LLM_BASE_URL, LLM_API_KEY, LLM_MODEL) ou tente novamente em instantes."
)
FRIENDLY_NOT_CONFIGURED = (
    "O Copilot ainda não está configurado neste ambiente. Preencha LLM_BASE_URL, "
    "LLM_API_KEY e LLM_MODEL no .env (endpoint do seu AI gateway ou da API Anthropic) "
    "e reinicie o servidor."
)


class ChatBody(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    sessionId: str = Field(default="default", max_length=64)


def _safe_log(exc: Exception) -> None:
    """Loga o erro sem nunca expor o token do gateway."""
    msg = str(exc)
    key = os.environ.get("LLM_API_KEY")
    if key:
        msg = msg.replace(key, "***")
    log.error("copilot: %s: %s", type(exc).__name__, msg[:300])


@router.get("/memory", summary="Memória da sessão lida do Atlas (painel de transparência da UI)")
def memory(sessionId: str = "default"):
    """Lê de volta, da collection `agent_checkpoints`, a conversa que o checkpointer
    persistiu para a sessão — a prova de que a memória do agente mora no banco."""
    from backend.agent.graph_agent import get_memory

    try:
        return get_memory(sessionId)
    except Exception as exc:  # noqa: BLE001
        _safe_log(exc)
        return {"collection": "agent_checkpoints", "sessionId": sessionId,
                "checkpoints": 0, "messages": []}


@router.post("/chat", summary="Conversa com o Copilot (agente sobre os dados)")
def chat(body: ChatBody):
    """Envia uma pergunta em pt-BR ao agente. A resposta traz `reply` e `toolCalls`
    (quais ferramentas o agente usou, com inputs e resumo, exibidos pela UI).
    A memória da conversa persiste por `sessionId` na collection `agent_checkpoints`."""
    from backend.agent.graph_agent import llm_configured, run_agent

    if not llm_configured():
        return {"reply": FRIENDLY_NOT_CONFIGURED, "toolCalls": [], "configured": False}

    try:
        result = run_agent(body.message, body.sessionId)
        return {**result, "configured": True}
    except Exception as exc:  # noqa: BLE001 — resposta amigável, sem stacktrace na UI
        _safe_log(exc)
        return {"reply": FRIENDLY_UNAVAILABLE, "toolCalls": [], "configured": True}
