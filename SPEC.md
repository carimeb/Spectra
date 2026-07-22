# Spectra — Especificação da demo

> **Engineering intelligence, decomposed.**
> Protótipo público que demonstra como modelar uma plataforma de engineering intelligence (repositórios, componentes de arquitetura, áreas organizacionais, dependências e vulnerabilidades) em MongoDB Atlas, substituindo um modelo relacional rígido por documentos flexíveis, travessias de grafo com `$graphLookup` e um agente de IA que responde perguntas em português.

---

## 0. Regras invioláveis

1. **NUNCA** mencionar nomes de empresas, bancos, domínios internos ou URLs de clientes em nenhum arquivo, código, comentário, dado de seed ou texto. O repositório será público. Hosts de exemplo devem ser genéricos (ex.: `https://dev.azure.com`, `https://devops.example.internal`).
2. **Todos os dados são 100% sintéticos**, gerados por script de seed com semente determinística. Nomes de sistemas, pessoas, áreas e repositórios são fictícios.
3. Idioma da UI e das respostas do agente: **português (pt-BR)**. Identificadores de código (variáveis, campos, endpoints): **inglês**.
4. O projeto deve **rodar localmente com no máximo 4 comandos** (documentados no README): configurar `.env`, instalar dependências, rodar seed, subir o servidor.
5. Trabalhar **por fases** (seção 10). Ao final de cada fase, rodar o smoke test da fase antes de avançar.

## 1. Contexto (por que esta demo existe)

O cenário-alvo é uma plataforma interna de engineering intelligence hoje em SQL Server (~62 tabelas), com estas dores:

- **Esquema rígido**: para adicionar um atributo novo a um componente de arquitetura, o time criou um modelo EAV (tabelas `ArchComponentAttribute` + `ArchAttribute`) — três tabelas e dois JOINs para ler um atributo.
- **Relacionamentos manuais**: o grafo de componentes existe em tabelas de adjacência (`ArchComponentRelation` com `ComponentId → ParentId`; `Area` com `ParentId` recursivo). O grafo é **raso (3–5 níveis) e largo (muitos N:N)**.
- **Cada pergunta nova vira código novo**: métricas de repositório são calculadas por uma function SQL de ~300 linhas com 6 CTEs (`RepositoryGetAnalysis`), consumida por dashboards.

**Pergunta-norte que a demo precisa responder bem:**
> "Aplicações .NET na versão X precisam migrar para a versão Y — quais áreas de negócio (BUs) são afetadas, quantas aplicações, e quem são os responsáveis?"

A demo responde a isso três vezes: como pipeline de agregação (query-herói A), como visualização de grafo (módulo Mapa & Grafo) e como pergunta em linguagem natural (módulo Copilot).

## 2. Decisões fixas de arquitetura

| Decisão | Valor |
|---|---|
| Nome do projeto/repo | `spectra` |
| Banco | MongoDB Atlas, cluster dedicado **M10**, **MongoDB 8.0+**, database `spectra`. Nuvem e região são transparentes para a demo — **não citar** provedor de nuvem nem região em código, README ou docs |
| Backend | **Python + FastAPI** (único runtime), driver `pymongo` (síncrono é suficiente) |
| Agente | **LangGraph** + `langchain-mongodb` + `langchain-anthropic` — modelo Claude acessado **exclusivamente via AI gateway corporativo** (seção 8.1); a demo nunca recebe nem usa chave direta de provedor |
| Embeddings | **Voyage AI** (`voyage-3-lite`, 512 dims), acesso configurável por env (via gateway ou endpoint direto — seção 8.2). Sem configuração de embeddings, o seed pula o campo `embedding` e a busca híbrida degrada graciosamente para full-text apenas (log de aviso, nunca erro) |
| Frontend | HTML/CSS/JS vanilla, single-page, estático, servido pelo próprio FastAPI (`StaticFiles`) |
| Visualização de grafo | `vis-network` via CDN |
| Dev tooling | MongoDB **MCP Server** (`mongodb-mcp-server` via `npx`) configurado em `.mcp.json`; **MongoDB Agent Skills** instaladas no Claude Code |

Variáveis de ambiente (`.env.example` com placeholders e comentários):

```
MONGODB_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/
MONGODB_DB=spectra
LLM_BASE_URL=            # endpoint do AI gateway corporativo (protocolo Anthropic Messages API)
LLM_API_KEY=             # token emitido pelo gateway — nunca uma chave direta de provedor
LLM_MODEL=               # id do modelo Claude exposto pelo gateway
EMBEDDINGS_API_KEY=      # opcional — token do serviço de embeddings (gateway interno ou provedor); sem ele, busca vetorial é desativada
EMBEDDINGS_BASE_URL=     # opcional — endpoint do serviço de embeddings; vazio = endpoint padrão do provedor
EMBEDDINGS_PROTOCOL=voyage   # "voyage" (default) ou "openai" — protocolo que o endpoint de embeddings expõe
EMBEDDINGS_MODEL=voyage-3-lite   # id do modelo no serviço de embeddings (catálogos internos podem usar outro nome)
```

## 3. Estrutura do repositório

```
spectra/
├── README.md
├── LICENSE                     # MIT
├── .env.example
├── .gitignore                  # inclui .env, __pycache__, .venv
├── .mcp.json                   # MongoDB MCP Server para o Claude Code
├── requirements.txt
├── backend/
│   ├── main.py                 # app FastAPI, monta routers + frontend estático
│   ├── db.py                   # cliente Mongo singleton, helpers
│   ├── routers/
│   │   ├── graph.py            # /api/graph/*  (queries-herói A e travessias)
│   │   ├── areas.py            # /api/areas/*  (query-herói B)
│   │   ├── schema_flex.py      # /api/schema/* (query-herói C)
│   │   ├── repositories.py     # /api/repositories
│   │   └── copilot.py          # /api/copilot/chat
│   ├── pipelines/
│   │   ├── impact.py           # pipeline da query-herói A (documentado linha a linha)
│   │   └── hierarchy.py        # pipeline da query-herói B
│   └── agent/
│       ├── graph_agent.py      # grafo LangGraph, checkpointer MongoDB
│       ├── tools.py            # graph_traversal + hybrid_search
│       └── prompts.py          # system prompt em pt-BR
├── seed/
│   ├── seed.py                 # ponto de entrada: python seed/seed.py
│   ├── generators.py           # geradores por collection (Faker, seed=42)
│   └── indexes.py              # cria índices regulares + Atlas Search + Vector Search
└── frontend/
    ├── index.html              # landing + shell com sidebar
    ├── styles.css
    ├── app.js                  # roteamento de módulos, fetch helpers
    └── modules/
        ├── graph.js            # Mapa & Grafo
        ├── schema.js           # Esquema Flexível
        ├── repositories.js     # Repositórios & Dependências
        └── copilot.js          # Copilot (chat)
```

## 4. Modelagem de dados (6 collections)

Princípio geral: **as arestas do grafo moram dentro dos nós** (array `relations`), porque o grafo é raso e largo — `$graphLookup` navega `relations.targetId → _id` sem collection de arestas. Atributos que no relacional eram EAV viram **campos nomeados no próprio documento**. Métricas que eram calculadas por function SQL viram **campos materializados (computed pattern)**.

Usar `_id` string legível (slug) em todas as collections para facilitar leitura em demo (ex.: `"comp-payments-api"`, `"area-cartoes"`).

### 4.1 `archComponents` — nós do grafo de arquitetura

```json
{
  "_id": "comp-pagamentos-core",
  "name": "Pagamentos Core",
  "type": "system",
  "description": "Sistema central de processamento de pagamentos. Orquestra autorização, liquidação e conciliação de transações em tempo real.",
  "attributes": {
    "criticality": "high",
    "exposure": "internal",
    "dataClassification": "confidential"
  },
  "relations": [
    { "targetId": "comp-antifraude" },
    { "targetId": "comp-cadastro-core" }
  ],
  "embedding": [0.013, -0.221, "..."],
  "createdAt": { "$date": "2024-03-11T00:00:00Z" },
  "updatedAt": { "$date": "2026-05-20T00:00:00Z" }
}
```

- `type` ∈ `{"system","application","platform","integration","database","queue"}` (vem de `ArchComponentType`).
- **`relations` é grafo ISOLADO componente↔componente e NÃO-tipado** — espelha `ArchComponentRelation` (pai/filho, sem coluna de tipo). Não há arestas para repos/áreas/usuários (essa ligação não existe na fonte); os dois grafos são separados.
- `attributes` é **livre por documento** — documentos diferentes podem ter chaves diferentes (ponto da query-herói C). Era EAV (`ArchComponentAttribute`+`ArchAttribute`).
- `description` (enriquecimento de demo, não vem da fonte): pt-BR, 2–4 frases, corpus da busca híbrida.
- `embedding` (enriquecimento): vetor da `description` (voyage-3-lite, 512 dims). Omitir quando não houver `EMBEDDINGS_API_KEY`.

### 4.2 `areas` — hierarquia organizacional (recursiva)

```json
{
  "_id": "area-cartoes",
  "name": "Cartões",
  "level": "bu",
  "parentId": "area-diretoria-produtos",
  "managerId": "user-0007",
  "techLeadId": "user-0019",
  "cost": 1042000.00,
  "revenue": 5300000.00,
  "isActive": true
}
```

- `level` ∈ `{"company","directorate","bu","squad"}` — deriva de `Area.Type` (tinyint) na fonte; 4 níveis, raiz única com `parentId: null`.
- Mantém adjacência (`parentId`) de propósito: espelha `Area.ParentId` e é o insumo da query-herói B.
- `cost`/`revenue`/`isActive` são campos reais de `Area`. `managerId`/`techLeadId` são derivados de `AreaUserDetail` (N:N com papel) — denormalização de conveniência.

### 4.3 `repositories` — computed pattern (substitui a function SQL)

Espelha as ~20 colunas do resultado da function de análise, **pré-computadas no documento**:

```json
{
  "_id": "repo-pagamentos-core-api",
  "name": "pagamentos-core-api",
  "projectId": "proj-meios-de-pagamento",
  "projectName": "Meios de Pagamento",
  "createdAt": { "$date": "2022-06-01T00:00:00Z" },
  "lastCommitDate": { "$date": "2026-05-14T00:00:00Z" },
  "location": "cloud",
  "analysis": {
    "isDeprecated": false,
    "isDeployable": true,
    "isLib": false,
    "isDeleted": false,
    "repositoryType": "csproj",
    "hasLastCommit": true,
    "commitTotal": 1382,
    "hasSucceededDeploy": true,
    "isOnCloudActive": true,
    "isOnServerActive": false,
    "isOnCloudActiveWithDeploy": true
  },
  "areaId": "area-cartoes",
  "topDependencies": [
    { "name": "Microsoft.AspNetCore.App", "version": "6.0.25", "type": "framework" },
    { "name": "Newtonsoft.Json", "version": "13.0.3", "type": "nuget" }
  ]
}
```

- `analysis` = campos que no relacional exigiam 6 CTEs; aqui já vêm prontos (o consumidor de BI lê direto, sem function). Inclui `isOnCloudActiveWithDeploy` (existe no resultado da function real).
- `topDependencies` = extended reference com top-5 dependências (o detalhe completo está em `dependencies`).
- `location` ∈ `{"cloud","server","payments","unidentified"}` (espelha `RepositoryLocation` da function; hosts genéricos).
- **NÃO há `targetFramework`**: a versão .NET é derivada da dependência de runtime (ver §6.1). Outros campos reais úteis: `gitId`, `defaultBranch`, `isDisabled`, `firstCommitDate`.

### 4.4 `users` — identidades embutidas (subset pattern)

```json
{
  "_id": "user-0042",
  "name": "Helena Ribeiro",
  "email": "helena.ribeiro@example.com",
  "role": "tech_lead",
  "identities": [
    { "provider": "azure-devops", "principal": "helena.ribeiro" },
    { "provider": "github", "principal": "helenar-dev" }
  ]
}
```

### 4.5 `dependencies` — collection de fatos (granular)

Uma linha por (repositório × pacote):

```json
{
  "_id": "dep-000131",
  "repositoryId": "repo-pagamentos-core-api",
  "name": "Microsoft.AspNetCore.App",
  "version": "6.0.25",
  "type": "framework",
  "conformityStatus": "compliant",
  "codeProjectPath": "src/pagamentos-core-api/pagamentos-core-api.csproj"
}
```

Espelha `CodeProjectDependency`. **Não há `targetFramework`**: a versão .NET é DERIVADA
do par (`name`, `version`) da dependência de runtime — `Microsoft.AspNetCore.App 6.0.x`
→ `net6.0`; `8.0.x` → `net8.0`; `Microsoft.AspNet.*` → `net48`. Essa derivação é o
primeiro estágio da query-herói A. Distribuição no seed: ~60 repos em net6.0.

### 4.6 `vulnerabilities` — collection de fatos

```json
{
  "_id": "vuln-00007",
  "repositoryId": "repo-pagamentos-core-api",
  "repositoryName": "pagamentos-core-api",
  "artifactDetails": "Newtonsoft.Json",
  "severity": "high",
  "sourceVulnerabilityId": "CVE-2024-99999",
  "source": "SCA",
  "status": "open",
  "detectedAt": { "$date": "2026-04-02T00:00:00Z" }
}
```

Espelha `CodeVulnerability`: `artifactDetails` (era `packageName`) ← `ArtifactDetails`;
`sourceVulnerabilityId` (era `cve`) ← `SourceVulnerabilityId` (nem sempre é CVE — pode
ser `GHSA-…`); `severity` ← `SeverityLevel`; `status` ← `State`; `detectedAt` ← `FirstTimeFound`.

### 4.7 Índices (criados por `seed/indexes.py`)

- Regulares: `archComponents.relations.targetId`, `areas.parentId`, `dependencies.repositoryId`, `dependencies.name` (derivação de framework na query A), `vulnerabilities.repositoryId`, `repositories.areaId`.
- **Atlas Search** (`default`) em `archComponents`: full-text sobre `name` + `description`, analyzer `lucene.portuguese`.
- **Atlas Vector Search** (`vector_index`) em `archComponents.embedding`: 512 dims, `cosine`. Criar apenas se embeddings existirem.
- Criação via `pymongo` (`create_search_index`); tratar caso "índice já existe" como sucesso idempotente.

## 5. Seed sintético (`seed/seed.py`)

- `Faker("pt_BR")`, `random.seed(42)` — **determinístico**.
- `python seed/seed.py` faz drop das collections, insere tudo, cria índices, imprime resumo por collection.
- Volumes: 1 company + 4 directorates + 12 BUs + 24 squads (=41 `areas`); 80 `users`; 150 `archComponents` (mistura de types, 2–6 `relations` cada, formando grafo conexo de 3–5 níveis: dependência → app → sistema → plataforma); 300 `repositories` (~15% deprecated, ~20% libs, distribuição realista de commits); ~2.500 `dependencies` (com concentração intencional: **~60 repositórios em `net6.0`** para a query de impacto retornar resultado expressivo); ~350 `vulnerabilities`.
- Nomes de sistemas/repos plausíveis para um domínio de serviços financeiros **genérico** (ex.: "Motor de Crédito", "Onboarding Digital", "Conciliação Contábil") — nunca reais.
- Coerência referencial: todo `targetId` em `relations` deve existir; todo `repositoryId` em fatos deve existir; `repositories.topDependencies` deve ser derivado de `dependencies`.

## 6. As três queries-herói

Implementar cada uma em `backend/pipelines/` como função que retorna o pipeline (lista de estágios), com **comentário por estágio** — os pipelines serão mostrados ao vivo.

### 6.1 Query A — Impacto de migração .NET X → Y (`impact.py`)

Endpoint: `GET /api/graph/impact?framework=net6.0`

> **Fidelidade (verificado no DDL):** o impacto flui pelo **grafo operacional**
> (`Repository`→`Area`→responsáveis). O grafo de arquitetura (`ArchComponent`) é
> **separado** na fonte — não há vínculo repo↔componente —, então **não** entra
> aqui. A versão .NET é **derivada** da dependência de runtime (não há campo
> `targetFramework`). "Aplicações" = projetos/repositórios reais.

Esqueleto do pipeline (partindo de `dependencies` = `CodeProjectDependency`):

```python
[
  # 1. Derivar a versão .NET do pacote de runtime e filtrar a versão de origem.
  #    (net6.0/net8.0 <- Microsoft.AspNetCore.App 6.0.x/8.0.x ; net48 <- Microsoft.AspNet.*)
  {"$match": {"name": "Microsoft.AspNetCore.App", "version": {"$regex": r"^6\."}}},
  {"$group": {"_id": "$repositoryId"}},

  # 2. Junta o documento do repositório (métricas pré-computadas = function RepositoryGetAnalysis)
  {"$lookup": {"from": "repositories", "localField": "_id",
                "foreignField": "_id", "as": "repo"}},
  {"$unwind": "$repo"},
  {"$match": {"repo.analysis.isDeleted": False, "repo.analysis.isDeprecated": False}},

  # 3. Sobe a hierarquia de áreas até a BU (RepositoryArea -> Area.ParentId)
  {"$graphLookup": {
      "from": "areas",
      "startWith": "$repo.areaId",
      "connectFromField": "parentId",
      "connectToField": "_id",
      "as": "areaChain",
      "maxDepth": 3
  }},

  # 4. Responsáveis (managerId / techLeadId da cadeia de áreas = AreaUserDetail)
  {"$lookup": {"from": "users", "localField": "areaChain.managerId",
                "foreignField": "_id", "as": "managers"}},

  # 5. Agrega por BU: nº de apps (projetos), nº de repos, responsáveis, proxy de esforço
  {"$group": { ... }},
  {"$sort": {"appCount": -1}}
]
```

Resposta agrupada por BU: `{ bu, appCount, repoCount, projects[], managers[], effortScore, effortBreakdown }`
(`appCount` = nº de projetos distintos; `repoCount` = nº de repositórios afetados).

**Fórmula fechada do `effortScore`** (não inventar outra): soma, por repositório afetado, de `pontos_tamanho + pontos_risco`, onde:

- `pontos_tamanho` = **1** se `analysis.commitTotal < 200`, **2** se `200–1000`, **3** se `> 1000`;
- `pontos_risco` = **1** se o repositório tem ≥1 vulnerabilidade `status: "open"` com `severity` `high` ou `critical` (migrar e corrigir juntos custa mais), senão **0**.

`effortBreakdown` = `{ smallRepos, mediumRepos, largeRepos, reposWithOpenVulns }` — a UI e o Copilot usam o breakdown para *explicar* o número, nunca mostrar o score sem explicação. Documentar no código que o score é ilustrativo; o ponto da demo é que ele nasce de campos já materializados no documento (`analysis.commitTotal` + `vulnerabilities`), sem nenhuma CTE. Ajustar o esqueleto conforme necessário para produzir resultado correto — o formato de resposta é o contrato.

### 6.2 Query B — Hierarquia de áreas recursiva (`hierarchy.py`)

Endpoint: `GET /api/areas/tree?rootId=area-...` (default: raiz).
`$graphLookup` em `areas` descendo (`connectFromField: "_id"`, `connectToField: "parentId"`), `depthField` para montar a árvore; resposta em JSON aninhado `{id, name, level, children: [...]}` com contagem de repositórios agregada por nó.

### 6.3 Query C — Esquema flexível sem migração (`schema_flex.py`)

- `POST /api/schema/components/{id}/attributes` — body `{"key": "...", "value": ...}` → `$set` em `attributes.<key>`.
- `POST /api/schema/components/{id}/relations` — adiciona `{type, targetId, targetCollection}` ao array `relations` (validar que o alvo existe).
- `GET /api/schema/components/{id}` — retorna o documento cru.
- A narrativa da demo: adicionar `attributes.pciScope: true` e uma relation nova a um componente e **re-executar a query A / o grafo sem tocar em nada** — nenhuma migração, nenhuma tabela nova, nenhum deploy.

## 7. API (FastAPI)

- `main.py`: CORS liberado para localhost, routers com prefixo `/api`, `StaticFiles` servindo `frontend/` na raiz (`/` → `index.html`). Swagger automático em `/docs` (usado em demo — manter títulos e descrições dos endpoints em pt-BR caprichados).
- Endpoints além dos das seções 6.x:
  - `GET /api/repositories?deprecated=&framework=&areaId=&q=` — lista paginada com filtros.
  - `GET /api/repositories/{id}` — documento completo + vulnerabilidades do repo.
  - `GET /api/graph/component/{id}?depth=2` — vizinhança do nó (para o Mapa & Grafo), retorna `{nodes:[], edges:[]}` pronto para vis-network.
  - `POST /api/copilot/chat` — body `{"message": "...", "sessionId": "..."}`; resposta `{"reply": "...", "toolCalls": [{tool, input, summary}]}` (a UI mostra quais tools o agente usou — isso é parte da demo).
  - `GET /api/health` — ping no Atlas + contagem por collection.

## 8. Agente LangGraph (`backend/agent/`)

- Grafo ReAct simples (`create_react_agent` do LangGraph) com modelo Claude via `langchain-anthropic`, **sempre através do AI gateway** (seção 8.1). O nome do modelo vem de `LLM_MODEL` — nunca hardcoded.

### 8.1 Acesso ao LLM via AI gateway (obrigatório)

O acesso a modelos generativos é centralizado num AI gateway corporativo (controle de acesso, rastreamento de custos e guardrails de segurança/compliance). Consequências para o código:

- A demo **nunca** chama `api.anthropic.com` diretamente e **nunca** manipula chave de provedor — apenas `LLM_BASE_URL` + `LLM_API_KEY` + `LLM_MODEL` do `.env`.
- Construir o chat model numa **única função** `get_chat_model()` em `graph_agent.py`: `ChatAnthropic(model=LLM_MODEL, base_url=LLM_BASE_URL, api_key=LLM_API_KEY)`. O gateway expõe um endpoint **Anthropic-compatible** (Messages API) — esse é o caminho padrão — e também um endpoint **OpenAI-compatible**; o `base_url` customizado é o único ajuste necessário e o resto do código do agente não sabe que existe um gateway.
- Se for necessário usar o caminho OpenAI-compatible, a troca acontece **somente** dentro de `get_chat_model()` (ex.: `ChatOpenAI` com os mesmos três env vars); nenhum outro arquivo conhece o provedor.
- Erros de auth/quota vindos do gateway viram resposta amigável do Copilot ("o serviço de IA está indisponível no momento") — nunca stacktrace na UI nem log com o token.
- No `.env.example` e no README, documentar os três env vars de forma genérica ("endpoint do seu gateway ou da API Anthropic") — **sem citar nomes internos de infraestrutura** (regra inviolável 1).

### 8.2 Embeddings — dois momentos, escada de fallback

Embeddings acontecem em **dois momentos distintos**, e a estratégia de fallback trata cada um:

1. **Seed-time (documentos)**: o `seed.py` embute as `description` dos `archComponents`. Isso roda **fora do runtime da demo** — pode usar o gateway (se ele cobrir embedding models) ou um acesso pontual ao endpoint do provedor, uma única vez. Os vetores ficam persistidos no documento.
2. **Query-time (pergunta do usuário)**: a tool `hybrid_search` precisa embutir a query a cada chamada. Só funciona se houver acesso a embeddings **no runtime**.

Regras de implementação:

- Espelhar o padrão do chat model: **única função** `get_embeddings()` (em `tools.py` ou módulo compartilhado) que lê `EMBEDDINGS_API_KEY` + `EMBEDDINGS_BASE_URL` + `EMBEDDINGS_PROTOCOL` e retorna o cliente configurado, ou `None` se não houver configuração. Seed e tool usam a mesma função.
- **Dois protocolos possíveis, decisão confinada a `get_embeddings()`**: com `EMBEDDINGS_PROTOCOL=voyage`, cliente Voyage (`langchain-voyageai`); com `EMBEDDINGS_PROTOCOL=openai`, cliente OpenAI-compatible (`OpenAIEmbeddings` com `base_url`) — cobre gateways internos que expõem embeddings no formato `/v1/embeddings`. O nome do modelo vem de `EMBEDDINGS_MODEL` (default `voyage-3-lite`; catálogos internos podem expor outro id para o mesmo modelo). Independentemente de protocolo e nome, o **índice permanece 512 dims / cosine** — se o serviço devolver vetor de outra dimensão, falhar o seed com mensagem clara (índice e vetores precisam bater).
- Escada de degradação (nunca erro, sempre log de aviso):
  1. embeddings configurados no runtime → busca híbrida completa (full-text + vetorial, rank fusion);
  2. documentos embutidos no seed mas sem embeddings no runtime → `hybrid_search` cai para full-text puro via Atlas Search, mesma assinatura;
  3. nenhum embedding em lugar nenhum → idem (2), e o índice vetorial simplesmente não é criado.
- A demo precisa estar **apresentável em qualquer degrau da escada** — a disponibilidade de embeddings via gateway não pode ser pré-requisito para a Fase 4 passar.
- **Checkpointer MongoDB** (`langgraph-checkpoint-mongodb`) persistindo estado por `sessionId` na collection `agent_checkpoints` — mencionar no README: até a memória do agente mora no mesmo banco.
- **Tool 1 — `graph_traversal`**: parâmetros `{start_id, direction: "up"|"down", max_depth}`; executa `$graphLookup` em `archComponents` e devolve nós + profundidade em JSON compacto. Descrição da tool em português, explícita sobre quando usar (perguntas de impacto, dependência, "quem é afetado por").
- **Tool 2 — `hybrid_search`**: parâmetro `{query}`; usa o retriever híbrido do `langchain-mongodb` (full-text + vetorial com rank fusion) sobre `archComponents.description`. Sem `EMBEDDINGS_API_KEY`, cair para full-text puro via Atlas Search (mesma assinatura).
- System prompt (`prompts.py`), em pt-BR: papel ("assistente de engineering intelligence"), instrução para **sempre citar os componentes/áreas encontrados pelos tools**, para encadear tools quando a pergunta exigir (buscar → travessia), e para responder "não encontrei" quando os tools voltarem vazios (nunca inventar).
- Perguntas de referência que o agente precisa responder bem (usar como teste manual):
  1. "Quais BUs são afetadas se migrarmos as apps de net6.0 para net8.0?"
  2. "Quais sistemas dependem do Motor de Crédito?"
  3. "Existe algum sistema relacionado a conciliação de pagamentos?" (híbrida)
  4. "Quem é o responsável técnico da área Cartões?"

## 9. Frontend (`frontend/`)

Referência visual: **https://carimeb.github.io/Maestro/** (mesma linguagem: landing page hero + shell de app com sidebar escura, cards limpos, tipografia sóbria). Sem frameworks — HTML/CSS/JS vanilla + vis-network via CDN. Responsivo o suficiente para projetar em tela (1280px+); não precisa de mobile.

1. **Landing** (`/`): hero com nome Spectra + tagline "Engineering intelligence, decomposed", 3 cards explicando as dores resolvidas (esquema flexível, grafo nativo, IA sobre os dados), botão "Abrir demo" que revela o shell.
2. **Shell**: sidebar com 4 módulos + indicador de conexão (via `/api/health`).
   - **Mapa & Grafo**: campo de busca de componente + canvas vis-network alimentado por `/api/graph/component/{id}`; clique num nó expande a vizinhança; painel lateral com o documento JSON do nó selecionado (syntax highlight simples). Botão "Análise de impacto" que roda a query A e pinta as BUs afetadas com contagens.
   - **Esquema Flexível**: seletor de componente, visualização do JSON cru, formulário para adicionar atributo/relação (query C), e um "antes/depois" mostrando que o documento mudou e o grafo continuou respondendo.
   - **Repositórios & Dependências**: tabela filtrável (framework, deprecated, área) sobre `/api/repositories`, com drilldown para o documento + vulnerabilidades — destaque visual para o objeto `analysis` (o "fim da function de 300 linhas").
   - **Copilot** (badge "novo" na sidebar): chat em pt-BR sobre `/api/copilot/chat`; cada resposta mostra, num bloco recolhível, as tools chamadas e seus inputs (transparência do agente é parte do pitch).

## 10. Fases de trabalho e critérios de aceite

**Fase 1 — Fundação e dados**: estrutura do repo, `.env.example`, `db.py`, seed completo + índices.
✅ Aceite: `python seed/seed.py` roda limpo duas vezes seguidas (idempotente) e imprime contagens esperadas; `mongosh`/MCP confirma grafo conexo (nenhum `relations.targetId` órfão — incluir checagem no próprio seed).

**Fase 2 — Pipelines e API**: routers + pipelines das 3 queries-herói + endpoints auxiliares.
✅ Aceite: `uvicorn backend.main:app` sobe; `/docs` lista tudo; query A com `net6.0` retorna ≥3 BUs com contagens > 0 e `effortScore` > 0 em cada BU, com `effortBreakdown` consistente (`smallRepos + mediumRepos + largeRepos == repoCount`); árvore de áreas tem 4 níveis; POST de atributo novo altera o documento e a query A continua funcionando.

**Fase 3 — Frontend**: landing + shell + módulos Mapa & Grafo, Esquema Flexível, Repositórios.
✅ Aceite: fluxo completo clicável sem erros de console; grafo renderiza e expande; impacto pinta BUs.

**Fase 4 — Copilot**: agente, tools, checkpointer, módulo de chat.
✅ Aceite: as 4 perguntas de referência (seção 8) respondem corretamente citando dados reais do seed; bloco de tools aparece na UI; sem `EMBEDDINGS_API_KEY` o agente segue funcional.

**Fase 5 — README, ponte de BI e polimento**: README com: o que é o Spectra e que dores demonstra; arquitetura (diagrama em Mermaid); pré-requisitos; setup em 4 comandos; como criar o cluster Atlas (**M10, MongoDB 8.0+** — sem citar provedor de nuvem ou região) e obter a URI; roteiro de demo sugerido (ordem dos módulos); seção "Desenvolvendo com IA" explicando como usar o **MongoDB MCP Server** (`.mcp.json` incluso) e as **MongoDB Agent Skills** no Claude Code para explorar e evoluir o projeto; seção "**BI sem quebrar: Power BI via Atlas SQL**" apontando para `docs/powerbi.md` (seção 12); seção "**Caminho para produção em .NET**" explicando que a modelagem da demo se transporta direto para a stack .NET do cenário-alvo via **driver C# oficial do MongoDB** e **provider do MongoDB para Entity Framework Core** (o `$graphLookup` e as agregações rodam idênticos a partir do C#; o FastAPI é só o runtime da demo); licença MIT; aviso de que todos os dados são sintéticos.
✅ Aceite: clonar em diretório limpo e seguir só o README reproduz a demo; `docs/powerbi.md` existe e cumpre o aceite da seção 12.

## 11. `.mcp.json` (dev tooling)

```json
{
  "mcpServers": {
    "mongodb": {
      "command": "npx",
      "args": ["-y", "mongodb-mcp-server", "--connectionString", "${MONGODB_URI}"]
    }
  }
}
```

Usado durante o desenvolvimento (e demonstrado ao cliente) para inspecionar collections, validar pipelines e checar índices direto do Claude Code.

## 12. Coexistência com BI — Power BI via Atlas SQL

No cenário-alvo, o consumidor principal das métricas é o **Power BI e ele não pode quebrar**. A demo deixa a ponte construída e documentada, mesmo sem uma licença de Power BI disponível para o teste de ponta a ponta. Consultar a documentação oficial do Atlas SQL ao implementar — não confiar em memória para nomes de comandos e telas.

Entregáveis (executados na Fase 5):

1. **`docs/powerbi.md`** com passo a passo completo e reproduzível:
   - habilitar o **Atlas SQL** para o cluster (instância federada com interface SQL) e obter a connection string;
   - gerar o schema relacional das collections com `sqlGenerateSchema`, mapeando `repositories` com o objeto `analysis` achatado em colunas — essa é a "tabela" que o BI passa a ler no lugar da function SQL;
   - instalar o **MongoDB Atlas SQL connector para Power BI** (custom connector + driver ODBC) e conectar ao endpoint;
   - montar um visual mínimo de exemplo (contagem de repositórios por área × `targetFramework`).
2. **Validação sem Power BI**: instrução `mongosh` (ou script) executando uma query `$sql` contra a instância federada — ex.: `SELECT areaId, targetFramework, COUNT(*) FROM repositories GROUP BY areaId, targetFramework`. Se o `$sql` responde, o conector do Power BI responde: é o mesmo endpoint.
3. **Narrativa no README**: o documento `repositories` com computed pattern é exatamente o que o BI lê — a function de ~300 linhas deixa de existir e o dashboard não quebra.

✅ Aceite: seguir `docs/powerbi.md` num ambiente limpo funciona até o passo da validação `$sql`; nenhum passo depende de infraestrutura interna ou cita nomes de clientes.
