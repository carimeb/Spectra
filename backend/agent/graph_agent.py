"""Agente ReAct do Copilot (LangGraph) com checkpointer MongoDB.

Acesso ao LLM SEMPRE via endpoint configurável (SPEC §9): apenas LLM_BASE_URL + LLM_API_KEY +
LLM_MODEL do .env, modelo nunca hardcoded. A escolha de protocolo (Anthropic-compatible,
padrão, ou OpenAI-compatible, plano B) fica confinada a get_chat_model(); nenhum outro
arquivo conhece o provedor. A memória de conversa persiste por sessionId na collection
`agent_checkpoints` — até a memória do agente mora no mesmo banco.
"""
from __future__ import annotations

import os
from functools import lru_cache

from backend.agent.prompts import SYSTEM_PROMPT
from backend.agent.tools import ALL_TOOLS
from backend.db import get_client


def llm_configured() -> bool:
    return bool(os.environ.get("LLM_API_KEY") and os.environ.get("LLM_MODEL"))


@lru_cache(maxsize=1)
def get_chat_model():
    """Única função que constrói o chat model (troca de protocolo acontece SÓ aqui)."""
    base_url = os.environ.get("LLM_BASE_URL") or None
    api_key = os.environ.get("LLM_API_KEY")
    model = os.environ.get("LLM_MODEL")
    protocol = os.environ.get("LLM_PROTOCOL", "anthropic").lower()

    if protocol == "openai":  # plano B: endpoint OpenAI-compatible do gateway
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model, api_key=api_key, base_url=base_url, temperature=0)

    from langchain_anthropic import ChatAnthropic

    # O cliente Anthropic acrescenta /v1/... sozinho; se a base do gateway já vier
    # com /v1 no fim (comum em snippets), removê-lo evita um 404 em /v1/v1/messages.
    if base_url and base_url.rstrip("/").endswith("/v1"):
        base_url = base_url.rstrip("/")[: -len("/v1")]

    # sem temperature: modelos Claude recentes rejeitam o parâmetro (deprecated)
    return ChatAnthropic(model=model, api_key=api_key, base_url=base_url, max_tokens=1500)


@lru_cache(maxsize=1)
def get_checkpointer():
    """Checkpointer MongoDB: a memória do agente mora no mesmo banco (agent_checkpoints)."""
    from langgraph.checkpoint.mongodb import MongoDBSaver

    return MongoDBSaver(
        get_client(),
        db_name=os.environ.get("MONGODB_DB", "spectra"),
        checkpoint_collection_name="agent_checkpoints",
        writes_collection_name="agent_checkpoint_writes",
    )


@lru_cache(maxsize=1)
def get_agent():
    """Agente ReAct com as 4 tools e checkpointer MongoDB (memória por sessionId)."""
    from langgraph.prebuilt import create_react_agent

    return create_react_agent(
        get_chat_model(), ALL_TOOLS, prompt=SYSTEM_PROMPT, checkpointer=get_checkpointer()
    )


def get_memory(session_id: str) -> dict:
    """Lê DE VOLTA do Atlas a memória persistida da sessão (painel da UI).

    Não usa estado em processo: o que aparece aqui é o que o checkpointer gravou
    na collection `agent_checkpoints` — qualquer outro agente/sistema leria o mesmo.
    """
    from backend.db import get_db

    saver = get_checkpointer()
    tup = saver.get_tuple({"configurable": {"thread_id": session_id}})
    count = get_db().agent_checkpoints.count_documents({"thread_id": session_id})

    messages = []
    if tup:
        for m in tup.checkpoint.get("channel_values", {}).get("messages", []):
            role = getattr(m, "type", "?")
            tool_calls = getattr(m, "tool_calls", None) or []
            if role == "ai" and tool_calls:
                text = "chamou " + ", ".join(tc.get("name", "?") for tc in tool_calls)
            else:
                content = m.content
                if isinstance(content, list):
                    content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
                text = str(content).strip()
            messages.append({"role": role,
                             "text": text[:110] + ("…" if len(text) > 110 else "")})
    return {"collection": "agent_checkpoints", "sessionId": session_id,
            "checkpoints": count, "messages": messages}


def run_agent(message: str, session_id: str) -> dict:
    """Roda o agente e devolve {reply, toolCalls} (contrato do /api/copilot/chat)."""
    agent = get_agent()
    result = agent.invoke(
        {"messages": [("user", message)]},
        config={"configurable": {"thread_id": session_id}},
    )
    messages = result.get("messages", [])

    # recorta o último turno: da última HumanMessage em diante
    last_human = 0
    for i, m in enumerate(messages):
        if getattr(m, "type", "") == "human":
            last_human = i
    turn = messages[last_human:]

    # transparência: quais tools o agente usou (a UI mostra isso na resposta)
    outputs_by_call_id = {
        getattr(m, "tool_call_id", None): str(getattr(m, "content", ""))
        for m in turn if getattr(m, "type", "") == "tool"
    }
    tool_calls = []
    for m in turn:
        for tc in getattr(m, "tool_calls", None) or []:
            summary = outputs_by_call_id.get(tc.get("id"), "")
            tool_calls.append({
                "tool": tc.get("name", "?"),
                "input": tc.get("args", {}),
                "summary": summary[:220] + ("…" if len(summary) > 220 else ""),
            })

    reply = ""
    for m in reversed(turn):
        if getattr(m, "type", "") == "ai" and not getattr(m, "tool_calls", None):
            content = m.content
            if isinstance(content, list):  # blocos de conteúdo (formato Anthropic)
                content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
            reply = str(content).strip()
            break

    return {"reply": reply or "Não consegui elaborar uma resposta.", "toolCalls": tool_calls}
