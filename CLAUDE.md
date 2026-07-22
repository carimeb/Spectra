# CLAUDE.md — Spectra

Guia curto para o Claude Code trabalhar neste repositório. A especificação
completa está em [`SPEC.md`](./SPEC.md); este arquivo resume o que é **inviolável**
e o que já está **decidido** (não reabrir sem instrução explícita).

> **Spectra — Engineering intelligence, decomposed.** Protótipo público que modela
> uma plataforma de engineering intelligence em MongoDB Atlas (documentos flexíveis,
> `$graphLookup` e um agente de IA em pt-BR), substituindo um modelo relacional rígido.

## Regras invioláveis

1. **Repositório é público.** NUNCA mencionar nomes de empresas, clientes, bancos,
   domínios internos ou URLs de clientes/infra corporativa em qualquer arquivo,
   código, comentário, dado de seed, commit ou mensagem de commit. Hosts de exemplo
   sempre genéricos (ex.: `https://dev.azure.com`, `https://devops.example.internal`).
2. **Todos os dados são 100% sintéticos**, gerados por seed determinístico
   (`Faker("pt_BR")`, `random.seed(42)`). Nomes de sistemas, pessoas, áreas e repos
   são fictícios e plausíveis para um domínio financeiro **genérico**.
3. **Idioma**: UI e respostas do agente em **português (pt-BR)**; identificadores de
   código (variáveis, campos, endpoints) em **inglês**.
4. **Rodar localmente em no máximo 4 comandos**, documentados no README
   (configurar `.env` → instalar deps → rodar seed → subir o servidor).
5. **Trabalhar por fases** (seção 10 do SPEC). Ao fim de cada fase, rodar o smoke
   test da fase antes de avançar.
6. **Acesso a LLM só via AI gateway corporativo.** Nunca chamar `api.anthropic.com`
   direto nem manipular chave direta de provedor — apenas `LLM_BASE_URL` +
   `LLM_API_KEY` + `LLM_MODEL`. Modelo nunca hardcoded.
7. **Segredos e nomes internos jamais entram no repo.** `.gitignore` contém `.env` e
   `CLAUDE.local.md` desde o primeiro commit. Erros de auth/quota do gateway viram
   mensagem amigável no Copilot — nunca stacktrace na UI nem token em log.

## Decisões fixas de arquitetura

| Item | Decisão |
|---|---|
| Projeto/repo | `spectra` |
| Banco | MongoDB Atlas, cluster **M10**, **MongoDB 8.0+**, DB `spectra`. Nunca citar provedor de nuvem nem região |
| Backend | **Python + FastAPI** (runtime único), driver `pymongo` síncrono |
| Agente | **LangGraph** (`create_react_agent`) + `langchain-mongodb` + `langchain-anthropic`, Claude via gateway; checkpointer MongoDB (`agent_checkpoints`) |
| Embeddings | **Voyage** `voyage-3-lite`, **512 dims**, configurável por env; degrada graciosamente para full-text quando ausente (log de aviso, nunca erro) |
| Frontend | HTML/CSS/JS vanilla, single-page estático, servido pelo FastAPI (`StaticFiles`) |
| Grafo | `vis-network` via CDN |
| Dev tooling | MongoDB **MCP Server** via `npx` (`.mcp.json`) + MongoDB Agent Skills |

## Modelo de dados — 6 collections

`archComponents`, `areas`, `repositories`, `users`, `dependencies`, `vulnerabilities`.
Princípios fixos:

- **Arestas moram nos nós** (array `relations` em `archComponents`); `$graphLookup`
  navega `relations.targetId → _id`. Sem collection de arestas.
- **Atributos antes EAV → campos nomeados** no documento (`attributes`, livre por doc).
- **Métricas antes calculadas por function SQL → campos materializados**
  (`repositories.analysis`, computed pattern).
- `_id` string legível (slug), ex.: `comp-pagamentos-core`, `area-cartoes`.

## Decisões de fidelidade ao schema do cliente (verificadas no DDL — autoritativas)

Estas decisões refinam o SPEC após conferência com o DDL real. Em conflito, **estas valem**:

1. **DOIS grafos independentes** (a fonte não os liga):
   - **Arquitetura**: `archComponents` ↔ `archComponents`, arestas **NÃO-tipadas** (`relations[] = [{targetId}]`), espelhando `ArchComponentRelation` (pai/filho sem tipo). Componentes **não** referenciam repos/áreas/usuários.
   - **Operacional**: `repositories` → `areas` (RepositoryArea) → hierarquia `Area.ParentId` → responsáveis (AreaUserDetail).
2. **`targetFramework` NÃO existe** — a versão .NET é **derivada** da dependência de runtime (`CodeProjectDependency`: nome+versão, ex.: `Microsoft.AspNetCore.App 6.0.x → net6.0`). Não armazenar como campo.
3. **Enriquecimentos de demo** (rotular como tais, não são da fonte): `description` e `embedding`, e o vocabulário dos `attributes` (placeholders até termos os nomes reais de `ArchAttribute`).
4. **Renames de fidelidade**: `cve`→`sourceVulnerabilityId`, `packageName`→`artifactDetails`; `users` ganha `empresa`/`isTerceiro`; `areas` usa `cost`/`revenue`/`isActive`; `repositories.location` tem 4 valores (cloud/server/payments/unidentified); `analysis` inclui `isOnCloudActiveWithDeploy`; `dependencies` ganha `conformityStatus`/`codeProjectPath`.

## Queries-herói (contrato de resposta é fixo)

- **A — Impacto de migração .NET X→Y** (`GET /api/graph/impact?framework=net6.0`), **grafo OPERACIONAL**:
  `dependencies` (derivar framework) → `$group` por repo → `$lookup repositories` → `$graphLookup areas`
  (subindo `Area.ParentId` até a BU) → responsáveis (AreaUserDetail) → agrupa por BU. "Aplicações" = projetos/repos.
  `effortScore` usa a **fórmula fechada do SPEC §6.1**; sempre com `effortBreakdown`.
- **B — Hierarquia de áreas recursiva** (`GET /api/areas/tree`): `$graphLookup` descendo `Area.ParentId`, JSON aninhado.
- **C — Esquema flexível sem migração** (`/api/schema/components/*`): adicionar atributo/relação e re-executar A/grafo sem migração alguma.
- **Grafo de arquitetura** (módulo Mapa & Copilot): `$graphLookup` em `archComponents.relations` responde "quais sistemas dependem de X" + busca híbrida sobre `description`.

## Env vars (só placeholders no `.env.example`)

`MONGODB_URI`, `MONGODB_DB`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`,
`EMBEDDINGS_API_KEY` (opcional), `EMBEDDINGS_BASE_URL` (opcional),
`EMBEDDINGS_PROTOCOL` (`voyage`|`openai`), `EMBEDDINGS_MODEL`.
Documentar de forma **genérica** ("endpoint do seu gateway ou da API Anthropic") —
sem nomes internos de infraestrutura.

## Antes de qualquer push

`grep -ri` por nomes internos/URLs corporativas (fora de `CLAUDE.local.md` e `.env`)
tem que voltar vazio. Se algo do contexto interno precisar virar doc, usar os termos
genéricos do SPEC ("AI gateway", "serviço de embeddings").
