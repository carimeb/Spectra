# CLAUDE.md — Spectra

Guia para trabalhar neste repositório com assistentes de código. A especificação técnica
completa está em [`SPEC.md`](./SPEC.md); instalação e uso, no [`README.md`](./README.md).

> **Spectra — Engineering intelligence, decomposed.** Protótipo público de engineering
> intelligence em MongoDB Atlas: documentos flexíveis, `$graphLookup` e um agente de IA em pt-BR
> substituindo um modelo relacional rígido (EAV, tabelas de adjacência, function SQL de análise).

## Regras do repositório

1. **Este repositório é público.** Nunca incluir nomes de empresas reais, domínios internos,
   URLs corporativas ou segredos em arquivo, código, comentário, dado de seed, commit ou
   mensagem de commit. Hosts de exemplo sempre genéricos (ex.: `https://dev.azure.com`,
   `https://devops.example.internal`). `.env` e `*.local.md` são gitignorados.
2. **Todos os dados são 100% sintéticos**, gerados por seed determinístico (`Faker("pt_BR")`,
   semente fixa). Nomes de sistemas, pessoas, áreas e repositórios são fictícios, plausíveis
   para um domínio financeiro genérico.
3. **Idioma**: UI e respostas do agente em **português (pt-BR)**, sem travessões (preferir
   vírgulas e dois-pontos); identificadores de código (variáveis, campos, endpoints) em **inglês**.
4. **Setup em no máximo 4 comandos**, documentados no README.
5. **Acesso a LLM só por configuração**: `LLM_BASE_URL` + `LLM_API_KEY` + `LLM_MODEL`
   (+ `LLM_PROTOCOL`), lidos exclusivamente dentro de `get_chat_model()`. Modelo nunca
   hardcoded. Erros de auth/quota viram mensagem amigável no Copilot; nunca stacktrace na UI
   nem token em log.
6. Antes de qualquer push, conferir que nenhum segredo ou host não-genérico entrou em arquivo
   versionado.

## Decisões fixas de arquitetura

| Item | Decisão |
|---|---|
| Banco | MongoDB Atlas, cluster **M10+**, **MongoDB 8.0+**, DB `spectra` |
| Backend | **Python + FastAPI** (runtime único), driver `pymongo` síncrono |
| Agente | **LangGraph** (`create_react_agent`) + `langchain-anthropic`; checkpointer MongoDB (`agent_checkpoints`); 4 tools curadas, duas por grafo |
| Busca do agente | Atlas Search full-text (analyzer português); com embeddings configurados (512 dims, opcional), híbrida com rank fusion; sem eles, degrada graciosamente (aviso em log, nunca erro) |
| Frontend | HTML/CSS/JS vanilla, single-page estático servido pelo FastAPI; `vis-network` via CDN |
| Dev tooling | MongoDB **MCP Server** via `npx` (`.mcp.json`) + MongoDB Agent Skills |

## Modelo de dados — 6 collections

`archComponents`, `areas`, `repositories`, `users`, `dependencies`, `vulnerabilities`.
Princípios fixos (detalhes e exemplos no SPEC §5):

- **Dois grafos independentes**, fiéis à origem relacional: arquitetura
  (`archComponents` ↔ `archComponents`, arestas não-tipadas em `relations[]`; `A → B` = "A
  depende de B") e operacional (`repositories` → `areas` → hierarquia `parentId` →
  responsáveis). Componentes não referenciam repositórios/áreas/usuários.
- **Arestas moram nos nós**: `$graphLookup` navega `relations.targetId → _id`; sem collection
  de arestas.
- **Atributos antes EAV → campos nomeados** no documento (`attributes`, livre por documento).
- **Métricas antes calculadas por function SQL → campos materializados** em
  `repositories.analysis` (computed pattern, atualizado na escrita).
- **`targetFramework` não existe**: a versão .NET é derivada da dependência de runtime
  (`Microsoft.AspNetCore.App 6.0.x → net6.0`; `Microsoft.AspNet.* → net48`).
- `_id` string legível (slug), ex.: `comp-motor-de-credito`, `area-cartoes`.
- Enriquecimentos que não vêm da origem relacional (rotulados como tais): `description`,
  `embedding` e o vocabulário dos `attributes`.

## Contratos que não mudam sem decisão explícita

- **Análise de impacto** (`GET /api/graph/impact?framework=`): resposta por BU
  `{bu, appCount, repoCount, projects[], managers[], effortScore, effortBreakdown}`; a fórmula
  do `effortScore` está fechada no SPEC §7.1 e o score nunca aparece sem o breakdown.
- **Árvore de áreas** (`GET /api/areas/tree`): JSON aninhado com `repoCount` por nó.
- **Esquema flexível** (`/api/schema/components/*`): `$set`/`$addToSet` com validação de alvo.
- **Copilot** (`POST /api/copilot/chat`): `{reply, toolCalls[]}`; `GET /api/copilot/memory`
  lê a sessão de volta de `agent_checkpoints`.
- Todo painel "ver a consulta" da UI exibe o pipeline/comando REAL executado (endpoints
  `*/query`), nunca uma versão simplificada.

## Comandos úteis

```bash
python seed/seed.py                      # recria dados + índices (idempotente, determinístico)
uvicorn backend.main:app                 # API + frontend em http://localhost:8000
uvicorn backend.main:app --reload        # com autoreload para desenvolvimento
```

Smoke test rápido: `GET /api/health` (ping + contagens), análise de impacto com `net6.0`
(deve retornar 12 BUs com `effortBreakdown` consistente: small+medium+large == repoCount) e as
4 perguntas de exemplo do SPEC §9 no Copilot.
