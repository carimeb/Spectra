"""Geradores determinísticos das 6 collections do Spectra.

Tudo é 100% sintético e reprodutível (Faker + random com seed=42). Nenhum nome
real de empresa/cliente/pessoa. Domínio: serviços financeiros GENÉRICOS.

FIDELIDADE AO SCHEMA DE ORIGEM (decisões tomadas a partir do DDL do cliente):
- Existem DOIS grafos independentes na fonte, e nós os mantemos separados:
  * grafo de ARQUITETURA: archComponents <-> archComponents (arestas NÃO-tipadas,
    espelhando ArchComponentRelation, que é só pai/filho). archComponents NÃO
    referenciam repositórios/áreas/usuários (essa ligação não existe na origem).
  * grafo OPERACIONAL: repositories -> areas (RepositoryArea) -> hierarquia de áreas
    (Area.ParentId) -> responsáveis (AreaUserDetail). É este que a query-herói A usa.
- A versão .NET NÃO é um campo da fonte: é DERIVADA da dependência de runtime
  (CodeProjectDependency: nome + versão). Não armazenamos `targetFramework`.
- Enriquecimentos de demo (não vêm da fonte, rotulados como tais): `description`
  e `embedding` (busca híbrida), e o vocabulário dos `attributes` (placeholders).

Ordem de geração (coerência referencial):
    users -> areas -> repositories -> dependencies -> (topDependencies)
          -> vulnerabilities -> archComponents (isolado; sem refs externas)
"""
from __future__ import annotations

import random
import unicodedata
from datetime import datetime, timedelta, timezone

from faker import Faker

fake = Faker("pt_BR")

# Data de referência fixa (determinismo — não usar datetime.now()).
REF = datetime(2026, 7, 1, tzinfo=timezone.utc)

SEED = 42


def reset_seed(seed: int = SEED) -> None:
    random.seed(seed)
    Faker.seed(seed)


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    out = []
    for ch in text:
        if ch.isalnum():
            out.append(ch)
        elif ch in " -_/.":
            out.append("-")
    slug = "".join(out)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-")


def _date_between(start_days_ago: int, end_days_ago: int) -> datetime:
    days = random.randint(end_days_ago, start_days_ago)
    return REF - timedelta(days=days, hours=random.randint(0, 23))


# --------------------------------------------------------------------------- #
# Vocabulário de domínio (financeiro, genérico e fictício)
# --------------------------------------------------------------------------- #
DOMAIN_NOUNS = [
    "Pagamentos", "Crédito", "Cobrança", "Antifraude", "Onboarding", "Conciliação",
    "Investimentos", "Cartões", "Câmbio", "Seguros", "Empréstimos", "Faturas",
    "Boletos", "Transferências", "Recebíveis", "Garantias", "Cadastro", "Limites",
    "Liquidação", "Compliance",
]
SYSTEM_PREFIXES = ["Motor de", "Núcleo de", "Plataforma de", "Central de", "Hub de"]
APP_PREFIXES = ["Serviço de", "Gateway de", "App de", "Portal de", "Worker de", "API de"]

NUGET_PACKAGES = [
    "Newtonsoft.Json", "Serilog", "AutoMapper", "FluentValidation", "Polly",
    "Dapper", "MediatR", "Swashbuckle.AspNetCore", "MongoDB.Driver", "StackExchange.Redis",
    "MassTransit", "Hangfire", "RestSharp", "Refit", "Microsoft.EntityFrameworkCore",
    "Azure.Messaging.ServiceBus", "Confluent.Kafka", "Elastic.Clients.Elasticsearch",
    "IdentityModel", "OpenTelemetry",
]

ROLES = ["developer", "developer", "developer", "tech_lead", "manager", "architect", "sre"]

# empresas (User.Empresa); "Interno" = efetivo, demais = terceiros (User.IsTerceiro)
EMPRESAS_INTERNO = "Interno"
EMPRESAS_TERCEIROS = ["Parceiro Alfa", "Parceiro Beta", "Consultoria Gama"]


# --------------------------------------------------------------------------- #
# users  (User + UserIdentities + UserRoles)
# --------------------------------------------------------------------------- #
def gen_users(n: int = 80) -> list[dict]:
    users = []
    seen_handles: set[str] = set()
    for i in range(n):
        name = fake.name()
        parts = [p for p in slugify(name).split("-") if p]
        handle = ".".join(parts[:2]) if len(parts) >= 2 else parts[0]
        base_handle = handle
        k = 2
        while handle in seen_handles:
            handle = f"{base_handle}{k}"
            k += 1
        seen_handles.add(handle)

        identities = [{"provider": "azure-devops", "principal": handle}]
        if random.random() < 0.5:
            identities.append({"provider": "github", "principal": f"{parts[0]}-dev"})

        is_terceiro = random.random() < 0.25
        empresa = random.choice(EMPRESAS_TERCEIROS) if is_terceiro else EMPRESAS_INTERNO

        users.append(
            {
                "_id": f"user-{i:04d}",
                "name": name,
                "email": f"{handle}@example.com",
                "role": random.choice(ROLES),
                "empresa": empresa,        # User.Empresa
                "isTerceiro": is_terceiro,  # User.IsTerceiro
                "identities": identities,   # UserIdentities (ProfileType->provider, ProfileId->principal)
            }
        )
    return users


# --------------------------------------------------------------------------- #
# areas  (Area + AreaUserDetail p/ manager/techLead)
# --------------------------------------------------------------------------- #
DIRECTORATE_NAMES = [
    "Diretoria de Produtos", "Diretoria de Plataformas",
    "Diretoria de Dados", "Diretoria de Operações",
]
BU_NAMES = [
    "Cartões", "Meios de Pagamento", "Crédito", "Investimentos", "Seguros",
    "Câmbio", "Conta Digital", "Empréstimos", "Onboarding", "Cobrança",
    "Conciliação Contábil", "Antifraude",
]


def gen_areas(user_ids: list[str]):
    areas: list[dict] = []
    used_slugs: set[str] = set()

    def mk_slug(prefix: str, name: str) -> str:
        base = f"{prefix}-{slugify(name)}"
        slug = base
        k = 2
        while slug in used_slugs:
            slug = f"{base}-{k}"
            k += 1
        used_slugs.add(slug)
        return slug

    def mk_area(_id, name, level, parent):
        # level deriva de Area.Type (tinyint) na origem; managerId/techLeadId derivam
        # de AreaUserDetail.Role. cost/revenue/isActive são campos reais de Area.
        return {
            "_id": _id, "name": name, "level": level, "parentId": parent,
            "managerId": random.choice(user_ids), "techLeadId": random.choice(user_ids),
            "cost": round(random.uniform(50_000, 2_000_000), 2),
            "revenue": round(random.uniform(0, 8_000_000), 2),
            "isActive": random.random() > 0.05,
        }

    company_id = "area-company"
    used_slugs.add(company_id)
    areas.append(mk_area(company_id, "Grupo Financeiro", "company", None))

    directorate_ids = []
    for name in DIRECTORATE_NAMES:
        _id = mk_slug("area", name)
        directorate_ids.append(_id)
        areas.append(mk_area(_id, name, "directorate", company_id))

    bu_ids = []
    for idx, name in enumerate(BU_NAMES):
        _id = mk_slug("area", name)
        bu_ids.append(_id)
        areas.append(mk_area(_id, name, "bu", directorate_ids[idx % len(directorate_ids)]))

    squad_ids = []
    for idx in range(24):
        bu = bu_ids[idx % len(bu_ids)]
        bu_name = next(a["name"] for a in areas if a["_id"] == bu)
        name = f"Squad {bu_name} {idx // len(bu_ids) + 1}"
        _id = mk_slug("area", name)
        squad_ids.append(_id)
        areas.append(mk_area(_id, name, "squad", bu))

    return areas, directorate_ids, bu_ids, squad_ids


# --------------------------------------------------------------------------- #
# repositories  (Repository + Project + RepositoryArea + function RepositoryGetAnalysis)
# --------------------------------------------------------------------------- #
# location espelha RepositoryLocation da function (4 valores reais; "unidentified"
# corrige o typo "undentified" da fonte — ver DECK).
LOCATIONS = (["cloud"] * 65) + (["server"] * 25) + (["payments"] * 7) + (["unidentified"] * 3)

# distribuição interna de framework (NÃO vira campo; guia a dependência de runtime)
def _framework_distribution(n: int) -> list[str]:
    frameworks = (["net6.0"] * 60) + (["net8.0"] * 140) + (["net48"] * (n - 200))
    random.shuffle(frameworks)
    return frameworks


def gen_repositories(bu_ids: list[str], squad_ids: list[str], n: int = 300):
    """Gera repos. Retorna (repos, frameworks) — frameworks é interno (não persistido)."""
    repos: list[dict] = []
    frameworks = _framework_distribution(n)
    area_pool = squad_ids + bu_ids

    for i in range(n):
        is_lib = random.random() < 0.20
        is_deprecated = random.random() < 0.15
        commit_total = random.choice(
            [random.randint(5, 199)] * 2
            + [random.randint(200, 1000)] * 3
            + [random.randint(1001, 4000)]
        )
        location = random.choice(LOCATIONS)
        is_deployable = not is_lib
        has_deploy = is_deployable and not is_deprecated
        is_cloud_active = location == "cloud" and not is_deprecated
        noun = random.choice(DOMAIN_NOUNS)
        suffix = "lib" if is_lib else random.choice(["api", "service", "worker", "gateway"])
        name = f"{slugify(noun)}-{suffix}-{i:03d}"

        repos.append(
            {
                "_id": f"repo-{i:04d}",
                "name": name,
                "gitId": f"{random.randint(10000, 99999)}",           # Repository.GitId
                "defaultBranch": random.choice(["main", "master", "develop"]),  # Repository.DefaultBranch
                "isDisabled": random.random() < 0.05,                 # Repository.IsDisabled
                "projectId": f"proj-{slugify(noun)}",
                "projectName": noun,                                   # Project.Name
                "createdAt": _date_between(1400, 400),
                "firstCommitDate": _date_between(1400, 400),           # Repository.FirstCommitDate
                "lastCommitDate": _date_between(400, 3) if not is_deprecated else _date_between(1200, 500),
                "location": location,
                # analysis{} = saída materializada da function RepositoryGetAnalysis (6 CTEs)
                "analysis": {
                    "isDeprecated": is_deprecated,
                    "isDeployable": is_deployable,
                    "isLib": is_lib,
                    "isDeleted": False,
                    "repositoryType": "csproj",
                    "hasLastCommit": True,
                    "commitTotal": commit_total,
                    "hasSucceededDeploy": has_deploy,
                    "isOnCloudActive": is_cloud_active,
                    "isOnServerActive": location == "server" and not is_deprecated,
                    "isOnCloudActiveWithDeploy": is_cloud_active and has_deploy,
                },
                "areaId": random.choice(area_pool),                    # via RepositoryArea
                "topDependencies": [],
            }
        )
    return repos, frameworks


# --------------------------------------------------------------------------- #
# dependencies  (CodeProjectDependency)  — sem targetFramework/ecosystem
# --------------------------------------------------------------------------- #
CONFORMITY = ["compliant", "compliant", "compliant", "outdated", "vulnerable", "unknown"]


def _runtime_dependency(framework: str) -> dict:
    """A dependência de runtime cuja (nome, versão) IMPLICA a versão .NET.

    net6.0 / net8.0 -> Microsoft.AspNetCore.App 6.0.x / 8.0.x
    net48           -> Microsoft.AspNet.WebApi.Core 5.2.9 (ASP.NET clássico)
    """
    if framework == "net48":
        return {"name": "Microsoft.AspNet.WebApi.Core", "version": "5.2.9"}
    major = framework.replace("net", "").split(".")[0]
    return {"name": "Microsoft.AspNetCore.App", "version": f"{major}.0.{random.randint(0, 30)}"}


def derive_framework(dep_name: str, dep_version: str) -> str | None:
    """Regra de derivação da versão .NET a partir da dependência de runtime.

    Mesma regra que a query-herói A expressa em estágios de agregação. Documentada
    para o cliente: "lemos suas linhas de CodeProjectDependency e inferimos o alvo
    .NET do pacote de runtime + versão — nenhuma coluna nova".
    """
    if dep_name == "Microsoft.AspNetCore.App":
        return f"net{dep_version.split('.')[0]}.0"
    if dep_name.startswith("Microsoft.AspNet."):
        return "net48"
    return None


def gen_dependencies(repos: list[dict], frameworks: list[str]) -> list[dict]:
    deps: list[dict] = []
    counter = 0
    for repo, framework in zip(repos, frameworks):
        rt = _runtime_dependency(framework)
        deps.append({
            "_id": f"dep-{counter:06d}", "repositoryId": repo["_id"],
            "name": rt["name"], "version": rt["version"], "type": "framework",
            "conformityStatus": random.choice(CONFORMITY),               # CodeProjectDependency.ConformityStatus
            "codeProjectPath": f"src/{repo['name']}/{repo['name']}.csproj",  # CodeProjectDependency.CodeProjectPath
        })
        counter += 1
        for pkg in random.sample(NUGET_PACKAGES, random.randint(3, 11)):
            deps.append({
                "_id": f"dep-{counter:06d}", "repositoryId": repo["_id"],
                "name": pkg,
                "version": f"{random.randint(1, 13)}.{random.randint(0, 9)}.{random.randint(0, 9)}",
                "type": "nuget",
                "conformityStatus": random.choice(CONFORMITY),
                "codeProjectPath": f"src/{repo['name']}/{repo['name']}.csproj",
            })
            counter += 1
    return deps


def attach_top_dependencies(repos: list[dict], deps: list[dict]) -> None:
    by_repo: dict[str, list[dict]] = {}
    for d in deps:
        by_repo.setdefault(d["repositoryId"], []).append(d)
    for repo in repos:
        repo_deps = by_repo.get(repo["_id"], [])
        repo_deps_sorted = sorted(repo_deps, key=lambda d: (d["type"] != "framework", d["name"]))
        repo["topDependencies"] = [
            {"name": d["name"], "version": d["version"], "type": d["type"]}
            for d in repo_deps_sorted[:5]
        ]


# --------------------------------------------------------------------------- #
# vulnerabilities  (CodeVulnerability)  — cve->sourceVulnerabilityId, packageName->artifactDetails
# --------------------------------------------------------------------------- #
SEVERITIES = ["low", "medium", "high", "critical"]
VULN_SOURCES = ["SCA", "SCA", "SAST", "DAST"]


def _source_vuln_id() -> str:
    if random.random() < 0.7:
        return f"CVE-2024-9{random.randint(1000, 9999)}"
    return f"GHSA-{random.randint(1000,9999)}-{random.randint(1000,9999)}"


def gen_vulnerabilities(repos: list[dict], deps: list[dict], n: int = 350) -> list[dict]:
    vulns: list[dict] = []
    by_repo: dict[str, list[dict]] = {}
    for d in deps:
        by_repo.setdefault(d["repositoryId"], []).append(d)

    for i in range(n):
        repo = random.choice(repos)
        repo_deps = by_repo.get(repo["_id"], [])
        artifact = random.choice(repo_deps)["name"] if repo_deps else random.choice(NUGET_PACKAGES)
        vulns.append(
            {
                "_id": f"vuln-{i:05d}",
                "repositoryId": repo["_id"],
                "repositoryName": repo["name"],                 # CodeVulnerability.RepositoryName (denormalizado)
                "artifactDetails": artifact,                    # CodeVulnerability.ArtifactDetails
                "severity": random.choices(SEVERITIES, weights=[3, 4, 2, 1])[0],  # SeverityLevel
                "sourceVulnerabilityId": _source_vuln_id(),     # CodeVulnerability.SourceVulnerabilityId
                "source": random.choice(VULN_SOURCES),          # CodeVulnerability.Source
                "status": random.choices(["open", "resolved"], weights=[6, 4])[0],  # State
                "detectedAt": _date_between(400, 5),            # FirstTimeFound
            }
        )
    return vulns


# --------------------------------------------------------------------------- #
# archComponents  (ArchComponent + EAV -> attributes; ArchComponentRelation -> relations)
# GRAFO ISOLADO: arestas NÃO-tipadas, apenas componente->componente.
# --------------------------------------------------------------------------- #
# Atributos HETEROGÊNEOS por tipo — o ponto da query-herói C (era EAV). Sem pciScope
# (adicionado ao vivo na demo, SPEC §6.3).
_ATTR_POOLS: dict[str, list] = {
    "system": [
        ("criticality", lambda: random.choice(["high", "medium", "low"])),
        ("businessDomain", lambda: random.choice(DOMAIN_NOUNS).lower()),
        ("slaTier", lambda: random.choice(["gold", "silver", "bronze"])),
        ("exposure", lambda: random.choice(["internal", "external", "partner"])),
    ],
    "application": [
        ("exposure", lambda: random.choice(["internal", "external", "partner"])),
        ("environment", lambda: random.choice(["production", "staging"])),
        ("slaTier", lambda: random.choice(["gold", "silver", "bronze"])),
        ("techStack", lambda: random.choice(["dotnet", "dotnet", "node", "java"])),
    ],
    "platform": [
        ("criticality", lambda: random.choice(["high", "medium"])),
        ("hostingModel", lambda: random.choice(["cloud", "hybrid", "on-prem"])),
        ("multiTenant", lambda: random.choice([True, False])),
    ],
    "database": [
        ("dataClassification", lambda: random.choice(["confidential", "restricted", "internal"])),
        ("encryptionAtRest", lambda: random.choice([True, False])),
        ("engine", lambda: random.choice(["sqlserver", "postgres", "mongodb", "redis"])),
    ],
    "queue": [
        ("deliveryGuarantee", lambda: random.choice(["at-least-once", "exactly-once"])),
        ("throughputTier", lambda: random.choice(["high", "standard"])),
    ],
    "integration": [
        ("protocol", lambda: random.choice(["rest", "soap", "grpc", "file"])),
        ("partnerFacing", lambda: random.choice([True, False])),
    ],
}


def _attributes_for(ctype: str) -> dict:
    pool = _ATTR_POOLS.get(ctype, [])
    if not pool:
        return {}
    k = random.randint(2, len(pool))
    return {key: fn() for key, fn in random.sample(pool, k)}


# Frases de responsabilidade por domínio (enriquecimento de demo). O vocabulário
# VARIADO é proposital: description é o corpus da busca híbrida, e 150 textos
# quase iguais degradariam tanto o full-text quanto a busca semântica (Fase 4).
_DOMAIN_PHRASES: dict[str, list[str]] = {
    "Pagamentos": ["autorização e liquidação de transações", "fluxos de pagamento instantâneo", "trilhas de auditoria de transações"],
    "Crédito": ["análise e concessão de crédito", "avaliação de risco do tomador", "esteiras de aprovação de propostas"],
    "Cobrança": ["réguas de cobrança e notificações", "negociação de dívidas em atraso", "baixa automática de títulos"],
    "Antifraude": ["detecção de transações suspeitas", "regras e escores de risco", "bloqueio preventivo de operações"],
    "Onboarding": ["abertura de contas e cadastro digital", "validação de documentos e identidade", "jornadas de ativação de clientes"],
    "Conciliação": ["batimento contábil entre sistemas", "fechamento diário de posições", "tratamento de divergências financeiras"],
    "Investimentos": ["ordens e custódia de ativos", "posições e rentabilidade de carteiras", "integração com corretoras e bolsas"],
    "Cartões": ["emissão e ciclo de vida de cartões", "processamento de faturas", "controles de limite e bloqueio"],
    "Câmbio": ["contratação de operações de câmbio", "cotações e fechamento de taxas", "remessas internacionais"],
    "Seguros": ["emissão e gestão de apólices", "processamento de sinistros", "cálculo de prêmios e coberturas"],
    "Empréstimos": ["simulação e contratação de empréstimos", "gestão de contratos e parcelas", "renegociação de saldos devedores"],
    "Faturas": ["geração e fechamento de faturas", "cálculo de encargos e juros", "distribuição de extratos"],
    "Boletos": ["registro e liquidação de boletos", "integração com a rede bancária", "instruções de cobrança registrada"],
    "Transferências": ["transferências entre contas", "liquidação em tempo real", "prevenção a lançamentos duplicados"],
    "Recebíveis": ["antecipação de recebíveis", "gestão da agenda de recebíveis", "conciliação de repasses a lojistas"],
    "Garantias": ["registro e avaliação de garantias", "monitoramento de colaterais", "execução de garantias vencidas"],
    "Cadastro": ["dados cadastrais de clientes", "atualização e enriquecimento cadastral", "gestão de consentimentos e privacidade"],
    "Limites": ["definição e revisão de limites", "consumo de limite em tempo real", "políticas de limite por produto"],
    "Liquidação": ["liquidação financeira de operações", "janelas de compensação", "reconciliação com câmaras de liquidação"],
    "Compliance": ["monitoramento de exigências regulatórias", "relatórios para órgãos supervisores", "trilhas de conformidade e auditoria"],
}

# Moldes de description por tipo de componente (2-3 frases; {p1}/{p2} vêm do domínio)
_TYPE_TEMPLATES: dict[str, list[str]] = {
    "system": [
        "Sistema central de {noun}. Concentra {p1} e coordena {p2}, expondo APIs internas para os times de produto.",
        "Núcleo de negócio para {noun}. Responsável por {p1}, com regras de {p2} e SLAs acompanhados pela engenharia.",
        "Sistema transacional de {noun}. Processa {p1} em alto volume e mantém {p2} sob trilha de auditoria.",
    ],
    "application": [
        "Aplicação de {noun} usada pelas squads no dia a dia. Implementa {p1} e consome serviços de {p2}.",
        "Serviço de apoio a {noun}. Automatiza {p1} e publica eventos de {p2} para os sistemas vizinhos.",
        "Aplicação que operacionaliza {noun}. Orquestra {p1} e acompanha {p2} em tempo quase real.",
    ],
    "platform": [
        "Plataforma corporativa que sustenta {noun} em escala. Padroniza {p1} e oferece {p2} como serviço às demais áreas.",
        "Fundação técnica compartilhada para {noun}. Centraliza {p1} e garante a resiliência de {p2}.",
    ],
    "database": [
        "Base de dados do domínio de {noun}. Armazena {p1} com histórico para consultas analíticas e auditoria.",
        "Repositório de dados de {noun}. Mantém {p1} com retenção controlada e acesso segregado por perfil.",
    ],
    "queue": [
        "Fila de mensageria do domínio de {noun}. Transporta eventos de {p1} entre produtores e consumidores, absorvendo picos de volume.",
        "Barramento assíncrono para {noun}. Garante a entrega de mensagens de {p1} com reprocessamento controlado.",
    ],
    "integration": [
        "Integração que conecta {noun} a parceiros e sistemas externos. Traduz protocolos e normaliza dados de {p1}.",
        "Conector de {noun} com o legado e provedores externos. Sincroniza {p1} e monitora falhas de comunicação.",
    ],
}
_GENERIC_PHRASES = ["operações do dia a dia", "rotinas de retaguarda", "controles operacionais"]


def _description(name: str, ctype: str, noun: str) -> str:
    phrases = _DOMAIN_PHRASES.get(noun, _GENERIC_PHRASES)
    p1, p2 = random.sample(phrases, 2)
    template = random.choice(_TYPE_TEMPLATES[ctype])
    return template.format(noun=noun.lower(), p1=p1, p2=p2)


def gen_arch_components() -> list[dict]:
    """150 componentes formando grafo conexo componente->componente (arestas não-tipadas).

    Estrutura de dependência (aresta = "relaciona-se com / depende de", fiel a
    ArchComponentRelation, que é só pai/filho SEM tipo):
        platform -> system -> application -> (database|queue|integration)
    E >=3 systems -> "Motor de Crédito" (pergunta de referência 2).
    """
    components: list[dict] = []
    used_slugs: set[str] = set()

    def mk(name):
        base = f"comp-{slugify(name)}"
        slug = base
        k = 2
        while slug in used_slugs:
            slug = f"{base}-{k}"
            k += 1
        used_slugs.add(slug)
        return slug

    def new_component(name, ctype, noun):
        comp = {
            "_id": mk(name), "name": name, "type": ctype,
            "description": _description(name, ctype, noun),   # enriquecimento (não vem da fonte)
            "attributes": _attributes_for(ctype),             # era EAV
            "relations": [],                                  # ArchComponentRelation (pai/filho, sem tipo)
            "createdAt": _date_between(1200, 400),
            "updatedAt": _date_between(400, 3),
        }
        components.append(comp)
        return comp

    databases, queues, integrations, applications, systems, platforms = [], [], [], [], [], []
    # âncoras das perguntas de referência do agente; noun = domínio das descriptions
    anchors = {
        "Motor de Crédito": "Crédito",
        "Conciliação de Pagamentos": "Conciliação",
        "Antifraude": "Antifraude",
        "Pagamentos Core": "Pagamentos",
    }

    for i in range(20):
        noun = random.choice(DOMAIN_NOUNS)
        databases.append(new_component(f"Base de {noun} {i+1}", "database", noun))
    for i in range(10):
        noun = random.choice(DOMAIN_NOUNS)
        queues.append(new_component(f"Fila de {noun} {i+1}", "queue", noun))
    for i in range(20):
        noun = random.choice(DOMAIN_NOUNS)
        integrations.append(new_component(f"Integração de {noun} {i+1}", "integration", noun))
    for i in range(50):
        noun = random.choice(DOMAIN_NOUNS)
        applications.append(new_component(f"{random.choice(APP_PREFIXES)} {noun} {i+1}", "application", noun))
    for name, noun in anchors.items():
        systems.append(new_component(name, "system", noun))
    for i in range(36):
        noun = random.choice(DOMAIN_NOUNS)
        systems.append(new_component(f"{random.choice(SYSTEM_PREFIXES)} {noun} {i+1}", "system", noun))
    for i in range(10):
        noun = random.choice(DOMAIN_NOUNS)
        platforms.append(new_component(f"Plataforma de {noun} {i+1}", "platform", noun))

    def edge(target_id):
        return {"targetId": target_id}  # aresta não-tipada componente->componente

    support = databases + queues + integrations
    for app in applications:
        for s in random.sample(support, random.randint(1, 2)):
            app["relations"].append(edge(s["_id"]))
    for sys in systems:
        for app in random.sample(applications, random.randint(1, 3)):
            sys["relations"].append(edge(app["_id"]))
    for plat in platforms:
        for sys in random.sample(systems, random.randint(1, 3)):
            plat["relations"].append(edge(sys["_id"]))

    # Infra também depende de infra (realista, mantém a semântica "depende de" e
    # evita nós de saída vazios): integração -> base/fila; base -> fila (outbox/CDC).
    for integ in integrations:
        for s in random.sample(databases + queues, random.randint(1, 2)):
            integ["relations"].append(edge(s["_id"]))
    for db in databases:
        if random.random() < 0.5 and queues:
            db["relations"].append(edge(random.choice(queues)["_id"]))
    # (filas permanecem folhas — são endpoints puros de infraestrutura)

    # >=3 sistemas dependem do "Motor de Crédito" (pergunta de referência 2)
    motor = next(c for c in systems if c["name"] == "Motor de Crédito")
    for sys in random.sample([s for s in systems if s is not motor], 3):
        sys["relations"].append(edge(motor["_id"]))

    return components
