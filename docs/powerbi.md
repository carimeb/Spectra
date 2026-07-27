# BI sem quebrar: Power BI via Atlas SQL

No cenário que o Spectra modela, o principal consumidor das métricas de repositório
é o **Power BI**, e ele não pode quebrar na migração. Este guia mostra a ponte:
o documento `repositories` já carrega as métricas prontas no objeto `analysis{}`
(computed pattern), e o **Atlas SQL** expõe essa collection como uma "tabela" SQL
que o Power BI lê diretamente. A function SQL de análise deixa de existir e o
dashboard continua funcionando.

> Todos os dados são sintéticos. Nenhum passo depende de infraestrutura interna.

## Pré-requisitos

- Cluster Atlas **M10+ (MongoDB 8.0+)** com o seed do Spectra carregado (`python seed/seed.py`);
- `mongosh` instalado (para a validação sem Power BI);
- Para o passo do Power BI: **Windows** com **Power BI Desktop 64-bit** atualizado.

## 1. Habilitar o Atlas SQL (instância federada)

O Atlas SQL roda sobre o **Atlas Data Federation**: uma instância federada expõe o
cluster com uma interface SQL.

1. No Atlas, abra **Data Federation** no menu do projeto.
2. Use o **Quick Start do Atlas SQL** (botão *Create Federated Database* → opção
   Atlas SQL) e selecione o cluster e o database `spectra` como fonte.
3. Ao concluir, a instância federada aparece listada com os "virtual databases"
   mapeando suas collections.

Documentação: [Getting Started (SQL Interface)](https://www.mongodb.com/docs/atlas/data-federation/query/sql/getting-started/get-started-advanced/).

## 2. Obter a connection string

1. Na instância federada, clique em **Connect**.
2. Para a validação via shell, escolha **Shell** e copie a connection string do
   `mongosh` (autenticação por usuário/senha do Atlas).
3. Para o Power BI, o mesmo modal oferece a opção **Atlas SQL** com a URI usada
   pelo conector/driver ODBC.

Só um usuário autentica por conexão na instância federada; se rodar `db.auth()`
no meio da sessão, as permissões anteriores são substituídas.

## 3. Gerar o schema relacional (`sqlGenerateSchema`)

O Atlas SQL descreve cada collection com um schema (gerado automaticamente por
amostragem no Quick Start). Para (re)gerar explicitamente o schema de
`repositories`, conecte o `mongosh` **na instância federada** e rode:

```javascript
use admin
db.runCommand({
  sqlGenerateSchema: 1,
  sampleNamespaces: ["spectra.repositories"],
  sampleSize: 1000,
  setSchemas: true
})
```

Para conferir o schema gravado:

```javascript
db.getSiblingDB("spectra").runCommand({ sqlGetSchema: "repositories" })
```

O ponto importante para o BI: o objeto `analysis` aparece no schema como um
subdocumento tipado, e as ferramentas SQL o acessam **como colunas** via caminho
com ponto (`analysis.commitTotal`, `analysis.isDeprecated`, ...). Essa "tabela"
é o substituto direto do resultado da antiga function de análise.

Documentação: [sqlGenerateSchema](https://www.mongodb.com/docs/atlas/data-federation/query/sql/sqlgenerateschema/).

## 4. Conectar o Power BI

1. Instale o **MongoDB ODBC Driver** mais recente
   ([download](https://www.mongodb.com/try/download/odbc-driver); versão 1.2+
   habilita Direct Query).
2. O conector **MongoDB Atlas SQL** já vem certificado nas versões atuais do
   Power BI Desktop. Se a sua versão não o tiver, copie o arquivo do conector
   para `C:\Users\<user>\Documents\Power BI Desktop\Custom Connectors`.
3. No Power BI Desktop: **Get Data → MongoDB Atlas SQL**, informe a URI do passo 2
   e o database `spectra`, e autentique com usuário/senha do Atlas.
4. Selecione a "tabela" `repositories` no navegador de dados. Os campos de
   `analysis` chegam achatados como colunas.

Documentação: [Connect from Power BI](https://www.mongodb.com/docs/atlas/data-federation/query/sql/powerbi/connect/).

## 5. Visual mínimo de exemplo

Com a tabela `repositories` carregada:

- **Linhas**: `areaId`;
- **Colunas**: `location` (cloud / server / payments / unidentified);
- **Valores**: contagem de `_id`;
- Filtro opcional: `analysis.isDeprecated = false`.

Observação de fidelidade: a versão .NET **não é um campo** de `repositories`
(ela é derivada da dependência de runtime em `dependencies`, como faz a análise
de impacto do protótipo). Para um visual por framework, agregue previamente em uma
view ou traga também a "tabela" `dependencies` e relacione por `repositoryId`.

## 6. Validação sem Power BI (`$sql` no mongosh)

O conector do Power BI consome o mesmo endpoint SQL da instância federada, então
se o `$sql` responde no `mongosh`, o Power BI responde. Conectado à instância
federada (passo 2):

```javascript
use spectra
db.aggregate([{
  $sql: {
    statement: "SELECT areaId, location, COUNT(*) AS repos FROM repositories WHERE analysis.isDeprecated = false GROUP BY areaId, location ORDER BY repos DESC LIMIT 10",
    format: "jdbc",
    dialect: "mongosql"
  }
}])
```

Ou, na forma curta (sujeita a mudanças): ``db.sql(`SELECT ... `)``.

Documentação: [Connect from the MongoDB Shell](https://www.mongodb.com/docs/atlas/data-federation/query/sql/shell/connect/).

## A narrativa em uma frase

O documento `repositories` com o `analysis{}` materializado é exatamente o que o
BI passa a ler: a function de ~300 linhas deixa de existir e o dashboard não
quebra, porque o Atlas SQL entrega a mesma leitura em SQL padrão.
