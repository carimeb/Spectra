"""Acesso a embeddings — função única compartilhada por seed e agente.

Decisão de protocolo (voyage x openai) e de configuração fica confinada aqui,
espelhando o padrão de get_chat_model(). Sem EMBEDDINGS_API_KEY, retorna None e
o chamador degrada graciosamente (nunca erro).

Independentemente de protocolo/modelo, o vetor DEVE ter 512 dims (o índice é
512/cosine). Se o serviço devolver outra dimensão, o seed falha com mensagem clara.
"""
from __future__ import annotations

import os

EXPECTED_DIMS = 512


def get_embeddings():
    """Retorna um cliente de embeddings LangChain configurado, ou None.

    - EMBEDDINGS_PROTOCOL=voyage  -> langchain-voyageai
    - EMBEDDINGS_PROTOCOL=openai  -> langchain-openai (OpenAI-compatible, base_url)
    Imports são lazy para não exigir os pacotes quando embeddings estão desligados.
    """
    api_key = os.environ.get("EMBEDDINGS_API_KEY")
    if not api_key:
        return None

    protocol = os.environ.get("EMBEDDINGS_PROTOCOL", "voyage").lower()
    model = os.environ.get("EMBEDDINGS_MODEL", "voyage-3-lite")
    base_url = os.environ.get("EMBEDDINGS_BASE_URL") or None

    if protocol == "openai":
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(model=model, api_key=api_key, base_url=base_url)

    # default: voyage
    from langchain_voyageai import VoyageAIEmbeddings

    kwargs = {"model": model, "api_key": api_key}
    if base_url:
        # alguns gateways expõem Voyage atrás de um base_url customizado
        kwargs["voyage_api_base"] = base_url
    return VoyageAIEmbeddings(**kwargs)
