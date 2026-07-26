"""/api/stats — KPIs agregados para a Visão Geral (prévia de dashboard)."""
from __future__ import annotations

from fastapi import APIRouter

from backend.db import get_db
from backend.pipelines.impact import framework_match

router = APIRouter(prefix="/stats", tags=["Visão geral"])


def _group_counts(db, collection: str, field: str) -> dict[str, int]:
    return {
        r["_id"]: r["count"]
        for r in db[collection].aggregate([{"$group": {"_id": f"${field}", "count": {"$sum": 1}}}])
    }


@router.get("/query", summary="As consultas reais que alimentam os KPIs (para exibição na UI)")
def stats_query():
    """Espelha, em notação de shell, as agregações que `/stats` executa — para a UI
    mostrar ao desenvolvedor exatamente como cada número é obtido."""
    return [
        {"title": "Repositórios: total, deprecados e libs",
         "code": 'db.repositories.countDocuments({})\n'
                 'db.repositories.countDocuments({ "analysis.isDeprecated": true })\n'
                 'db.repositories.countDocuments({ "analysis.isLib": true })'},
        {"title": "Cloud vs On-Prem (contagem por localização)",
         "code": 'db.repositories.aggregate([\n  { $group: { _id: "$location", count: { $sum: 1 } } }\n])'},
        {"title": "Frameworks .NET (versão derivada da dependência de runtime)",
         "code": 'db.dependencies.distinct("repositoryId", {\n  name: "Microsoft.AspNetCore.App",\n  '
                 + r'version: { $regex: "^6\." }' + '\n})'},
        {"title": "Componentes de arquitetura por tipo",
         "code": 'db.archComponents.aggregate([\n  { $group: { _id: "$type", count: { $sum: 1 } } }\n])'},
        {"title": "Vulnerabilidades abertas por severidade",
         "code": 'db.vulnerabilities.aggregate([\n  { $match: { status: "open" } },\n'
                 '  { $group: { _id: "$severity", count: { $sum: 1 } } }\n])'},
        {"title": "Áreas por nível (company / directorate / bu / squad)",
         "code": 'db.areas.aggregate([\n  { $group: { _id: "$level", count: { $sum: 1 } } }\n])'},
    ]


@router.get("", summary="KPIs agregados (repos, componentes, áreas, vulnerabilidades)")
def stats():
    db = get_db()

    frameworks = {
        fw: len(db.dependencies.distinct("repositoryId", framework_match(fw)))
        for fw in ("net48", "net6.0", "net8.0")
    }
    open_by_sev = {
        r["_id"]: r["count"]
        for r in db.vulnerabilities.aggregate([
            {"$match": {"status": "open"}},
            {"$group": {"_id": "$severity", "count": {"$sum": 1}}},
        ])
    }

    return {
        "repositories": {
            "total": db.repositories.count_documents({}),
            "deprecated": db.repositories.count_documents({"analysis.isDeprecated": True}),
            "libs": db.repositories.count_documents({"analysis.isLib": True}),
            "byLocation": _group_counts(db, "repositories", "location"),
            "byFramework": frameworks,
        },
        "components": {
            "total": db.archComponents.count_documents({}),
            "byType": _group_counts(db, "archComponents", "type"),
        },
        "areas": {
            "total": db.areas.count_documents({}),
            "byLevel": _group_counts(db, "areas", "level"),
        },
        "vulnerabilities": {
            "open": db.vulnerabilities.count_documents({"status": "open"}),
            "total": db.vulnerabilities.count_documents({}),
            "openBySeverity": open_by_sev,
        },
        "users": {
            "total": db.users.count_documents({}),
            "terceiros": db.users.count_documents({"isTerceiro": True}),
        },
    }
