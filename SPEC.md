# Spectra — Especificação técnica

> **Engineering intelligence, decomposed.**
> Protótipo público que demonstra como modelar uma plataforma de engineering intelligence
> (repositórios, componentes de arquitetura, áreas organizacionais, dependências e
> vulnerabilidades) em MongoDB Atlas, substituindo um modelo relacional rígido por documentos
> flexíveis, travessias de grafo com `$graphLookup` e um agente de IA que responde em português.

Instruções de instalação e uso estão no [README](README.md). Este documento descreve o
contexto, as decisões de arquitetura e os contratos técnicos do protótipo.

## 1. Contexto

O cenário de referência é uma plataforma interna de engineering intelligence originalmente em SQL Server
(~62 tabelas), com três limitações típicas do modelo relacional:

- **Esquema rígido**: para adicionar um atributo novo a um componente de arquitetura, o modelo
  usa EAV (tabelas `ArchComponentAttribute` + `ArchAttribute`): três tabelas e dois JOINs para
  ler um único atributo.
- **Relacionamentos manuais**: o grafo de componentes vive em tabelas de adjacência
  (`ArchComponentRelation` com `ComponentId → ParentId`; `Area` com `ParentId` recursivo).
  O grafo é **raso (3–5 níveis) e largo (muitos N:N)**.
- **Cada pergunta nova vira código novo**: métricas de repositório são calculadas por uma
  function SQL de ~300 linhas com 6 CTEs (`RepositoryGetAnalysis`), consumida por dashboards.

**Pergunta-norte que o protótipo responde bem:**
> "Aplicações .NET na versão X precisam migrar para a versão Y — quais áreas de negócio (BUs)
> são afetadas, quantas aplicações, e quem são os responsáveis?"

O protótipo responde a isso três vezes: como pipeline de agregação (análise de impacto), como
visualização (a hierarquia de áreas acesa pela análise) e como pergunta em linguagem natural
(módulo Copilot).

## 2. Princípios

1. **Todos os dados são 100% sintéticos**, gerados por seed determinístico (`Faker("pt_BR")`,
   semente fixa). Nomes de sistemas, pessoas, áreas e repositórios são fictícios, plausíveis
   para um domínio financeiro genérico.
2. **Idioma**: UI e respostas do agente em **português (pt-BR)**; identificadores de código
   (variáveis, campos, endpoints) em **inglês**.
3. **Rodar localmente em no máximo 4 comandos** (documentados no README).
4. Hosts de exemplo sempre **genéricos** (ex.: `https://dev.azure.com`,
   `https://devops.example.internal`); segredos só em `.env`, que é gitignorado.

## 3. Decisões de arquitetura

| Decisão | Valor |
|---|---|
| Banco | MongoDB Atlas, cluster dedicado **M10+**, **MongoDB 8.0+**, database `spectra` |
| Backend | **Python + FastAPI** (único runtime), driver `pymongo` síncrono |
| Agente | **LangGraph** (`create_react_agent`) + `langchain-anthropic`, modelo Claude acessado via endpoint configurável (AI gateway ou API Anthropic); checkpointer MongoDB (`agent_checkpoints`) |
| Busca do agente | Atlas Search full-text (analyzer português) sobre `name`/`description`; com serviço de embeddings configurado, vira híbrida (full-text + vetorial com rank fusion) |
| Frontend | HTML/CSS/JS vanilla, single-page estático, servido pelo FastAPI (`StaticFiles`) |
| Visualização de grafo | `vis-network` via CDN |
| Dev tooling | MongoDB **MCP Server** via `npx` (`.mcp.json`) + MongoDB Agent Skills |

Variáveis de ambiente (placeholders comentados em `.env.example`): `MONGODB_URI`, `MONGODB_DB`,
`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_PROTOCOL` (`anthropic`|`openai`),
`EMBEDDINGS_API_KEY`/`EMBEDDINGS_BASE_URL`/`EMBEDDINGS_PROTOCOL`/`EMBEDDINGS_MODEL` (opcionais).
O acesso ao LLM acontece exclusivamente por essas variáveis, dentro de uma única função
(`get_chat_model()`); o modelo nunca é hardcoded.

## 4. Estrutura do repositório

```
spectra/
├── README.md                   # instalação, módulos, ponte de BI, caminho .NET
├── .env.example
├── .mcp.json                   # MongoDB MCP Server (dev tooling)
├── requirements.txt
├── docs/
│   └── powerbi.md              # Power BI via Atlas SQL, com validação $sql
├── backend/
│   ├── main.py                 # app FastAPI, routers + frontend estático
│   ├── db.py                   # cliente Mongo singleton
│   ├── embeddings.py           # get_embeddings() única (voyage|openai), opcional
│   ├── routers/
│   │   ├── graph.py            # /api/graph/*  (impacto + vizinhança do grafo de arquitetura)
│   │   ├── areas.py            # /api/areas/*  (árvore de áreas)
│   │   ├── schema_flex.py      # /api/schema/* (esquema flexível)
│   │   ├── repositories.py     # /api/repositories
│   │   ├── stats.py            # /api/stats (KPIs da Visão Geral)
│   │   └── copilot.py          # /api/copilot/chat + /api/copilot/memory
│   ├── pipelines/
│   │   ├── impact.py           # pipeline da análise de impacto (anotado por estágio)
│   │   ├── hierarchy.py        # pipeline da árvore de áreas
│   │   └── neighborhood.py     # vizinhança de componente ($graphLookup bidirecional)
│   └── agent/
│       ├── graph_agent.py      # get_chat_model(), agente ReAct, checkpointer, memória
│       ├── tools.py            # 4 tools curadas (2 por grafo)
│       └── prompts.py          # system prompt em pt-BR
├── seed/
│   ├── seed.py                 # python seed/seed.py (idempotente)
│   ├── generators.py           # geradores por collection (determinístico)
│   └── indexes.py              # índices regulares + Atlas Search (+ vetorial, se houver embeddings)
└── frontend/
    ├── index.html              # landing + shell com sidebar
    ├── styles.css
    ├── app.js                  # roteamento de módulos, fetch, highlight de código/JSON
    └── modules/
        ├── graph.js            # Mapa & Grafo (grafo de arquitetura)
        ├── operational.js      # Hierarquia e Análise de Esforço (grafo operacional)
        ├── schema.js           # Esquema Flexível
        ├── repositories.js     # Dashboard (computed pattern + Atlas SQL)
        └── copilot.js          # Copilot (chat + painel de ferramentas/memória)
```

## 5. Modelo de dados (6 collections)

Princípio geral: **as arestas do grafo moram dentro dos nós** (array `relations`), porque o
grafo é raso e largo: `$graphLookup` navega `relations.targetId → _id` sem collection de
arestas. Atributos que no relacional eram EAV viram **campos nomeados no próprio documento**.
Métricas que eram calculadas por function SQL viram **campos materializados (computed pattern)**.
`_id` é uma string legível (slug) em todas as collections (ex.: `"comp-motor-de-credito"`,
`"area-cartoes"`).

### 5.1 Dois grafos independentes (fidelidade à origem)

A fonte relacional **não liga** componentes de arquitetura a repositórios ou áreas, e o modelo
preserva isso:

- **Grafo de ARQUITETURA**: `archComponents` ↔ `archComponents`, arestas **não-tipadas**
  (`relations[] = [{targetId}]`), espelhando `ArchComponentRelation` (pai/filho sem tipo).
- **Grafo OPERACIONAL**: `repositories` → `areas` (espelha `RepositoryArea`) → hierarquia
  `Area.ParentId` → responsáveis (espelha `AreaUserDetail`).

Semântica da aresta de arquitetura: `A → B` significa "A depende de B" (dirigida, acíclica).

### 5.2 `archComponents` — nós do grafo de arquitetura

```json
{
  "_id": "comp-motor-de-credito",
  "name": "Motor de Crédito",
  "type": "system",
  "description": "Sistema transacional de crédito. Processa esteiras de aprovação...",
  "attributes": { "criticality": "high", "exposure": "internal" },
  "relations": [ { "targetId": "comp-servico-de-cambio-47" } ],
  "createdAt": { "$date": "2024-03-11T00:00:00Z" },
  "updatedAt": { "$date": "2026-05-20T00:00:00Z" }
}
```

- `type` ∈ `{"system","application","platform","integration","database","queue"}`.
- `attributes` é **livre por documento**: documentos diferentes podem ter chaves diferentes
  (era EAV no relacional).
- `description` é enriquecimento do protótipo (não vem da fonte): pt-BR, 2–3 frases, corpus da
  busca do agente. Com embeddings configurados no seed, o documento ganha também um campo
  `embedding` (512 dims).

### 5.3 `areas` — hierarquia organizacional (recursiva)

```json
{
  "_id": "area-cartoes", "name": "Cartões", "level": "bu",
  "parentId": "area-diretoria-produtos",
  "managerId": "user-0007", "techLeadId": "user-0019",
  "cost": 1042000.00, "revenue": 5300000.00, "isActive": true
}
```

- `level` ∈ `{"company","directorate","bu","squad"}`; raiz única com `parentId: null`.
- Mantém adjacência (`parentId`) de propósito: é o insumo do `$graphLookup` da árvore.
- `managerId`/`techLeadId` denormalizam a relação N:N área-pessoa com papel.

### 5.4 `repositories` — computed pattern

Espelha as ~20 colunas do resultado da function de análise, **pré-computadas no documento**:

```json
{
  "_id": "repo-0169", "name": "antifraude-api-169",
  "projectId": "proj-antifraude", "projectName": "Antifraude",
  "gitId": "16310", "defaultBranch": "master", "isDisabled": false,
  "createdAt": {"$date": "..."}, "firstCommitDate": {"$date": "..."}, "lastCommitDate": {"$date": "..."},
  "location": "cloud",
  "analysis": {
    "isDeprecated": false, "isDeployable": true, "isLib": false, "isDeleted": false,
    "repositoryType": "csproj", "hasLastCommit": true, "commitTotal": 909,
    "hasSucceededDeploy": true, "isOnCloudActive": true, "isOnServerActive": false,
    "isOnCloudActiveWithDeploy": true
  },
  "areaId": "area-cartoes",
  "topDependencies": [ { "name": "Microsoft.AspNetCore.App", "version": "6.0.25", "type": "framework" } ]
}
```

- `analysis` = os campos que no relacional exigiam 6 CTEs; aqui já vêm prontos e são
  **atualizados na escrita** (quem ingere o dado regrava os campos; o banco não os recalcula).
- `topDependencies` = extended reference com as top-5 dependências (detalhe em `dependencies`).
- `location` ∈ `{"cloud","server","payments","unidentified"}`.
- **Não há `targetFramework`**: a versão .NET é **derivada** da dependência de runtime (§7.1).

### 5.5 `users` — identidades embutidas (subset pattern)

```json
{
  "_id": "user-0042", "name": "Helena Ribeiro", "email": "helena.ribeiro@example.com",
  "role": "tech_lead", "empresa": "Interno", "isTerceiro": false,
  "identities": [ { "provider": "azure-devops", "principal": "helena.ribeiro" } ]
}
```

### 5.6 `dependencies` — collection de fatos (granular)

Uma linha por (repositório × pacote):

```json
{
  "_id": "dep-000131", "repositoryId": "repo-0169",
  "name": "Microsoft.AspNetCore.App", "version": "6.0.25", "type": "framework",
  "conformityStatus": "compliant",
  "codeProjectPath": "src/antifraude-api-169/antifraude-api-169.csproj"
}
```

A versão .NET é derivada do par (`name`, `version`) da dependência de runtime:
`Microsoft.AspNetCore.App 6.0.x` → `net6.0`; `8.0.x` → `net8.0`; `Microsoft.AspNet.*` → `net48`.

### 5.7 `vulnerabilities` — collection de fatos

```json
{
  "_id": "vuln-00007", "repositoryId": "repo-0169", "repositoryName": "antifraude-api-169",
  "artifactDetails": "Newtonsoft.Json", "severity": "high",
  "sourceVulnerabilityId": "CVE-2024-99999", "source": "SCA",
  "status": "open", "detectedAt": { "$date": "2026-04-02T00:00:00Z" }
}
```

`sourceVulnerabilityId` nem sempre é CVE (pode ser `GHSA-…`), por isso o nome do campo.

### 5.8 Índices (criados por `seed/indexes.py`)

- Regulares: `archComponents.relations.targetId`, `areas.parentId`, `dependencies.repositoryId`,
  `dependencies.name+version` (derivação de framework), `vulnerabilities.repositoryId`,
  `repositories.areaId`.
- **Atlas Search** (`default`) em `archComponents`: full-text sobre `name` + `description`,
  analyzer `lucene.portuguese`.
- **Atlas Vector Search** (`vector_index`) em `archComponents.embedding`: 512 dims, `cosine`;
  criado apenas quando o seed rodou com embeddings configurados.
- Criação idempotente ("índice já existe" é sucesso).

## 6. Seed sintético (`seed/seed.py`)

- `Faker("pt_BR")` com semente fixa: **determinístico** (duas execuções produzem o mesmo resultado).
- `python seed/seed.py` dropa as collections, insere tudo, valida coerência referencial
  (nenhuma referência órfã), cria índices e imprime um resumo por collection.
- Volumes: 41 `areas` (1 company + 4 directorates + 12 BUs + 24 squads); 80 `users`;
  150 `archComponents` (grafo conexo de 3–5 níveis); 300 `repositories`; ~2.400 `dependencies`
  (com ~60 repositórios em `net6.0`); 350 `vulnerabilities`.
- As `description` dos componentes combinam vocabulário por domínio de negócio com moldes por
  tipo de componente, para o corpus da busca ser variado.

## 7. As três consultas centrais

Cada uma vive em `backend/pipelines/` como função que retorna o pipeline (lista de estágios),
com comentário por estágio; a UI exibe os pipelines reais nos painéis "ver a consulta".

### 7.1 Impacto de migração .NET (`impact.py`)

Endpoint: `GET /api/graph/impact?framework=net6.0` (grafo **operacional**).

Estágios: derivar a versão .NET da dependência de runtime (`$match` em `dependencies`) →
`$group` por repositório → `$lookup` do documento do repositório (métricas prontas em
`analysis`) → risco por vulnerabilidade aberta high/critical → `$graphLookup` subindo a
hierarquia de áreas até a BU → `$group` por BU → responsáveis (`$lookup` em `users`).

Contrato de resposta, por BU:
`{ bu, appCount, repoCount, projects[], managers[], effortScore, effortBreakdown }`.

**Fórmula fechada do `effortScore`**: soma, por repositório afetado, de
`pontos_tamanho + pontos_risco`, onde `pontos_tamanho` = 1 se `analysis.commitTotal < 200`,
2 se 200–1000, 3 se > 1000; e `pontos_risco` = 1 se o repositório tem ≥1 vulnerabilidade
`open` com severidade `high`/`critical`, senão 0. O score é ilustrativo e sempre acompanha o
`effortBreakdown` (`{smallRepos, mediumRepos, largeRepos, reposWithOpenVulns}`), que o explica.
O ponto técnico: nasce de campos já materializados, sem nenhuma CTE.

### 7.2 Hierarquia de áreas (`hierarchy.py`)

Endpoint: `GET /api/areas/tree?rootId=...` (default: raiz). `$graphLookup` descendo a
adjacência `parentId` (`connectFromField: "_id"`, `connectToField: "parentId"`); resposta em
JSON aninhado `{id, name, level, repoCount, children[]}` com contagem de repositórios por nó.

### 7.3 Esquema flexível sem migração (`schema_flex.py`)

- `POST /api/schema/components/{id}/attributes` — `{"key", "value"}` → `$set` em `attributes.<key>`.
- `POST /api/schema/components/{id}/relations` — adiciona `{targetId}` a `relations`
  (valida que o alvo existe, sem duplicatas nem auto-referência).
- `GET /api/schema/components/{id}` — documento cru.

Exemplo: adicionar `attributes.pciScope: true` a um componente e re-executar o grafo e a
análise de impacto, sem migração de modelo, tabela nova ou deploy. A UI re-executa as
consultas de leitura após cada escrita, como prova.

## 8. API (FastAPI)

`main.py` monta CORS para desenvolvimento local, routers com prefixo `/api` e `StaticFiles`
servindo `frontend/` na raiz. Swagger em `/docs`, com títulos e descrições em pt-BR.

Endpoints além dos da seção 7:

- `GET /api/repositories?deprecated=&framework=&areaId=&q=` — lista paginada com filtros
  (framework é derivado via `dependencies`).
- `GET /api/repositories/{id}` — documento completo + vulnerabilidades do repositório.
- `GET /api/graph/components?q=` — lista leve (id/name/type) para busca.
- `GET /api/graph/component/{id}?depth=` — vizinhança bidirecional para o vis-network
  (`{nodes, edges}`); `GET /api/graph/component/{id}/query` retorna o pipeline real.
- `GET /api/graph/impact/query`, `GET /api/areas/tree/query`, `GET /api/stats/query` —
  as consultas reais que cada tela executa, para exibição na UI.
- `GET /api/stats` — KPIs agregados.
- `POST /api/copilot/chat` — `{"message", "sessionId"}` → `{"reply", "toolCalls":[{tool, input, summary}]}`.
- `GET /api/copilot/memory?sessionId=` — a conversa persistida em `agent_checkpoints`, lida de
  volta do banco (alimenta o painel de transparência da UI).
- `GET /api/health` — ping no Atlas + contagem por collection.

## 9. Agente (backend/agent/)

Agente ReAct (`create_react_agent` do LangGraph) com modelo Claude acessado pelo endpoint
configurado em env. Consequências de desenho:

- O código **nunca** manipula chave direta de provedor: apenas `LLM_BASE_URL` + `LLM_API_KEY` +
  `LLM_MODEL` (+ `LLM_PROTOCOL`), lidos numa **única função** `get_chat_model()`. Trocar de
  gateway ou de protocolo não toca nenhum outro arquivo.
- Erros de auth/quota viram resposta amigável do Copilot; nunca stacktrace na UI, nunca token
  em log.
- **Checkpointer MongoDB** (`langgraph-checkpoint-mongodb`): o estado da conversa persiste por
  `sessionId` na collection `agent_checkpoints` — a memória do agente mora no mesmo banco, e
  qualquer outro sistema pode lê-la pelo driver.
- **4 ferramentas curadas**, duas por grafo, reutilizando as mesmas consultas das telas:
  - `hybrid_search` (arquitetura): busca por texto sobre `name`/`description`; escada de
    degradação: híbrida (com embeddings) → full-text Atlas Search → regex.
  - `graph_traversal` (arquitetura): `$graphLookup` bidirecional em `relations[]`.
  - `impact_analysis` (operacional): o pipeline de `impact.py`.
  - `area_info` (operacional): área + responsáveis + cadeia hierárquica.
- System prompt em pt-BR (`prompts.py`): responder só com base nas ferramentas, citar os nomes
  retornados, encadear busca → travessia quando necessário, respeitar a separação dos dois
  grafos e dizer "não encontrei" quando as ferramentas voltarem vazias.

Perguntas de exemplo que o agente responde bem (úteis como teste manual):

1. "Quais BUs são afetadas se migrarmos as apps de net6.0 para net8.0?"
2. "Quais sistemas dependem do Motor de Crédito?"
3. "Existe algum sistema relacionado a conciliação de pagamentos?"
4. "Quem é o responsável técnico da área Cartões?"

## 10. Frontend (`frontend/`)

HTML/CSS/JS vanilla + vis-network via CDN, tema escuro, projetado para telas de 1280px+.
Landing com as três limitações do modelo relacional e shell com sidebar de 6 módulos (descritos no README). Padrões
transversais: badge identificando o grafo de cada tela ("grafo de arquitetura" /
"grafo operacional"), contraste "Era: ..." ligando cada tela à limitação relacional que ela resolve,
painéis "ver a consulta" com o comando MongoDB real colorido, e documentos crus com campos-chave
(`relations[]`, `attributes`, `analysis{}`) em destaque.

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

Conecta o MongoDB MCP Server a assistentes de código (Claude Code e similares) para inspecionar
collections, validar pipelines e checar índices durante o desenvolvimento.

## 12. Coexistência com BI — Power BI via Atlas SQL

O consumidor típico das métricas é uma ferramenta de BI, e ela não pode quebrar. O documento
`repositories`, com o `analysis{}` materializado, é exatamente o que o BI passa a ler via
**Atlas SQL** (instância federada com interface SQL): a function de ~300 linhas deixa de
existir e o dashboard continua funcionando. O passo a passo completo, incluindo a validação
por `$sql` no `mongosh` que dispensa uma licença de Power BI, está em
[`docs/powerbi.md`](docs/powerbi.md).
