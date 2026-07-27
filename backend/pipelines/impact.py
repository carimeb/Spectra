"""Consulta central: impacto de migração .NET X → Y.

Grafo OPERACIONAL (fiel à origem relacional): dependency → repository → hierarquia de áreas →
responsáveis, agrupado por BU. A versão .NET é DERIVADA da dependência de runtime
(não existe campo targetFramework). O grafo de arquitetura (archComponents) é
separado na fonte e NÃO participa desta query.

Cada estágio está anotado com o equivalente relacional de origem.
"""
from __future__ import annotations


def framework_match(framework: str) -> dict:
    """Traduz a versão .NET pedida para o filtro na dependência de RUNTIME.

    É a materialização da regra de derivação (ver seed/generators.derive_framework):
      net6.0 / net8.0 <- Microsoft.AspNetCore.App 6.0.x / 8.0.x
      net48           <- Microsoft.AspNet.WebApi.Core
    """
    fw = framework.lower()
    if fw in ("net6.0", "net8.0"):
        major = fw.replace("net", "").split(".")[0]
        return {"name": "Microsoft.AspNetCore.App", "version": {"$regex": rf"^{major}\."}}
    if fw == "net48":
        return {"name": "Microsoft.AspNet.WebApi.Core"}
    raise ValueError(f"framework não suportado: {framework!r} (use net48, net6.0 ou net8.0)")


def build_impact_pipeline(framework: str) -> list[dict]:
    match = framework_match(framework)
    return [
        # 1. Derivar a versão .NET do pacote de runtime e filtrar a origem.
        #    (relacional: WHERE em CodeProjectDependency por nome+versão)
        {"$match": match},
        {"$group": {"_id": "$repositoryId"}},

        # 2. Documento do repositório — métricas já materializadas (analysis{}).
        #    (relacional: JOIN Repository + a function RepositoryGetAnalysis)
        {"$lookup": {"from": "repositories", "localField": "_id",
                     "foreignField": "_id", "as": "repo"}},
        {"$unwind": "$repo"},
        {"$match": {"repo.analysis.isDeleted": False, "repo.analysis.isDeprecated": False}},

        # 3. Risco: existe vulnerabilidade ABERTA high/critical no repo?
        #    (relacional: JOIN CodeVulnerability filtrando State/SeverityLevel)
        {"$lookup": {
            "from": "vulnerabilities",
            "let": {"rid": "$repo._id"},
            "pipeline": [
                {"$match": {"$expr": {"$and": [
                    {"$eq": ["$repositoryId", "$$rid"]},
                    {"$eq": ["$status", "open"]},
                    {"$in": ["$severity", ["high", "critical"]]},
                ]}}},
                {"$limit": 1},
            ],
            "as": "openVulns",
        }},

        # 4. Fórmula fechada do effortScore (SPEC §7.1): pontos_tamanho + pontos_risco.
        #    O ponto técnico: nasce de campos JÁ materializados (commitTotal + vulns),
        #    sem nenhuma CTE. Score ilustrativo; a UI explica pelo breakdown.
        {"$addFields": {
            "sizePoints": {"$switch": {"branches": [
                {"case": {"$lt": ["$repo.analysis.commitTotal", 200]}, "then": 1},
                {"case": {"$lte": ["$repo.analysis.commitTotal", 1000]}, "then": 2},
            ], "default": 3}},
            "sizeBucket": {"$switch": {"branches": [
                {"case": {"$lt": ["$repo.analysis.commitTotal", 200]}, "then": "small"},
                {"case": {"$lte": ["$repo.analysis.commitTotal", 1000]}, "then": "medium"},
            ], "default": "large"}},
            "hasOpenVuln": {"$gt": [{"$size": "$openVulns"}, 0]},
        }},
        {"$addFields": {"riskPoints": {"$cond": ["$hasOpenVuln", 1, 0]}}},

        # 5. Subir a hierarquia de áreas até a BU.
        #    (relacional: RepositoryArea + CTE recursiva em Area.ParentId)
        {"$graphLookup": {
            "from": "areas", "startWith": "$repo.areaId",
            "connectFromField": "parentId", "connectToField": "_id",
            "as": "areaChain", "depthField": "depth",
        }},
        {"$addFields": {"buArea": {"$first": {"$filter": {
            "input": "$areaChain", "as": "a", "cond": {"$eq": ["$$a.level", "bu"]},
        }}}}},
        {"$match": {"buArea": {"$ne": None}}},

        # 6. Agregar por BU.
        {"$group": {
            "_id": "$buArea._id",
            "buName": {"$first": "$buArea.name"},
            "managerId": {"$first": "$buArea.managerId"},
            "techLeadId": {"$first": "$buArea.techLeadId"},
            "repoCount": {"$sum": 1},
            "projects": {"$addToSet": "$repo.projectName"},
            "effortScore": {"$sum": {"$add": ["$sizePoints", "$riskPoints"]}},
            "smallRepos": {"$sum": {"$cond": [{"$eq": ["$sizeBucket", "small"]}, 1, 0]}},
            "mediumRepos": {"$sum": {"$cond": [{"$eq": ["$sizeBucket", "medium"]}, 1, 0]}},
            "largeRepos": {"$sum": {"$cond": [{"$eq": ["$sizeBucket", "large"]}, 1, 0]}},
            "reposWithOpenVulns": {"$sum": {"$cond": ["$hasOpenVuln", 1, 0]}},
        }},

        # 7. Responsáveis da BU (managerId/techLeadId) — via AreaUserDetail.
        {"$addFields": {"responsibleIds": {"$setUnion": [["$managerId"], ["$techLeadId"]]}}},
        {"$lookup": {"from": "users", "localField": "responsibleIds",
                     "foreignField": "_id", "as": "managers"}},

        # 8. Formato final (contrato de resposta).
        {"$project": {
            "_id": 0,
            "bu": {"id": "$_id", "name": "$buName"},
            "appCount": {"$size": "$projects"},
            "repoCount": 1,
            "projects": {"$sortArray": {"input": "$projects", "sortBy": 1}},
            "managers": {"$map": {"input": "$managers", "as": "m",
                                  "in": {"id": "$$m._id", "name": "$$m.name", "role": "$$m.role"}}},
            "effortScore": 1,
            "effortBreakdown": {
                "smallRepos": "$smallRepos", "mediumRepos": "$mediumRepos",
                "largeRepos": "$largeRepos", "reposWithOpenVulns": "$reposWithOpenVulns",
            },
        }},
        {"$sort": {"appCount": -1, "repoCount": -1, "bu.name": 1}},
    ]
