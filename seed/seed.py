"""Ponto de entrada do seed: python seed/seed.py

Fluxo:
  1. conecta no Atlas (ping)
  2. gera as 6 collections de forma determinística (seed=42)
  3. (opcional) embute embeddings das descriptions se EMBEDDINGS_API_KEY existir
  4. dropa e reinsere tudo (idempotente)
  5. checa coerência referencial (nenhum targetId/repositoryId órfão)
  6. cria índices (regulares + Atlas Search; Vector Search só com embeddings)
  7. imprime resumo por collection

Rodar duas vezes seguidas deve produzir exatamente o mesmo resultado.
"""
from __future__ import annotations

import os
import sys

# permitir "python seed/seed.py" a partir da raiz do repo
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.db import COLLECTIONS, get_db, ping  # noqa: E402
from backend.embeddings import EXPECTED_DIMS, get_embeddings  # noqa: E402
from seed import generators as g  # noqa: E402
from seed import indexes as ix  # noqa: E402


def _log(msg: str) -> None:
    print(f"[seed] {msg}")


def _warn(msg: str) -> None:
    print(f"[seed][aviso] {msg}")


def maybe_embed(components: list[dict]) -> bool:
    """Embute embeddings nas descriptions se houver serviço configurado.

    Retorna True se embeddings foram gerados (=> criar índice vetorial).
    Nunca levanta erro por ausência de configuração — apenas degrada.
    """
    client = get_embeddings()
    if client is None:
        _warn("EMBEDDINGS_API_KEY ausente — pulando embeddings; busca híbrida cairá para full-text.")
        return False

    _log(f"gerando embeddings para {len(components)} componentes...")
    texts = [c["description"] for c in components]
    vectors = client.embed_documents(texts)

    dims = len(vectors[0]) if vectors else 0
    if dims != EXPECTED_DIMS:
        raise SystemExit(
            f"[seed][erro] serviço de embeddings devolveu {dims} dims, esperado {EXPECTED_DIMS}. "
            f"Verifique EMBEDDINGS_MODEL — o índice vetorial é fixo em {EXPECTED_DIMS}/cosine."
        )
    for comp, vec in zip(components, vectors):
        comp["embedding"] = list(vec)
    _log(f"embeddings OK ({dims} dims).")
    return True


def check_integrity(data: dict) -> None:
    """Falha se houver referência órfã — parte do critério de aceite da Fase 1."""
    ids = {name: {doc["_id"] for doc in docs} for name, docs in data.items()}
    errors: list[str] = []

    # relations de archComponents: grafo ISOLADO, targetId aponta só p/ archComponents
    for comp in data["archComponents"]:
        for r in comp["relations"]:
            if r["targetId"] not in ids["archComponents"]:
                errors.append(f"{comp['_id']}: relation -> {r['targetId']} órfã (archComponents)")

    # areas.parentId deve existir (exceto raiz)
    for area in data["areas"]:
        if area["parentId"] and area["parentId"] not in ids["areas"]:
            errors.append(f"{area['_id']}: parentId {area['parentId']} órfão")

    # repositoryId em dependencies/vulnerabilities deve existir
    for coll in ("dependencies", "vulnerabilities"):
        for doc in data[coll]:
            if doc["repositoryId"] not in ids["repositories"]:
                errors.append(f"{doc['_id']}: repositoryId {doc['repositoryId']} órfão")

    # repositories.areaId deve existir
    for repo in data["repositories"]:
        if repo["areaId"] not in ids["areas"]:
            errors.append(f"{repo['_id']}: areaId {repo['areaId']} órfão")

    if errors:
        for e in errors[:20]:
            print(f"[seed][erro] {e}")
        raise SystemExit(f"[seed][erro] coerência referencial falhou: {len(errors)} problema(s).")
    _log("coerência referencial OK (nenhuma referência órfã).")


def build_dataset() -> dict:
    g.reset_seed()
    users = g.gen_users(80)
    user_ids = [u["_id"] for u in users]

    areas, directorate_ids, bu_ids, squad_ids = g.gen_areas(user_ids)

    repos, frameworks = g.gen_repositories(bu_ids, squad_ids, 300)
    deps = g.gen_dependencies(repos, frameworks)
    g.attach_top_dependencies(repos, deps)
    vulns = g.gen_vulnerabilities(repos, deps, 350)

    # grafo de arquitetura é isolado (não referencia repos/áreas/users) — fiel à fonte
    components = g.gen_arch_components()

    return {
        "users": users,
        "areas": areas,
        "archComponents": components,
        "repositories": repos,
        "dependencies": deps,
        "vulnerabilities": vulns,
    }


def main() -> None:
    _log("conectando ao Atlas...")
    ping()
    db = get_db()

    _log("gerando dataset determinístico (seed=42)...")
    data = build_dataset()

    with_vector = maybe_embed(data["archComponents"])

    check_integrity(data)

    _log("dropando e reinserindo collections...")
    for name in COLLECTIONS:
        db[name].drop()
        db[name].insert_many(data[name])

    _log("criando índices...")
    search_indexes = ix.create_all(db, with_vector=with_vector)
    _log(f"índices de busca solicitados: {', '.join(search_indexes)} (Atlas os constrói de forma assíncrona).")

    # resumo
    print("\n===== RESUMO =====")
    expected = {
        "users": 80, "areas": 41, "archComponents": 150,
        "repositories": 300, "vulnerabilities": 350,
    }
    for name in COLLECTIONS:
        count = db[name].count_documents({})
        exp = expected.get(name)
        flag = "" if exp is None or count == exp else f"  (esperado {exp}!)"
        print(f"  {name:16} {count:6d}{flag}")
    # net6.0 é DERIVADO da dependência de runtime (não há campo targetFramework)
    net6 = db.dependencies.count_documents(
        {"name": "Microsoft.AspNetCore.App", "version": {"$regex": r"^6\."}}
    )
    print(f"  {'repos net6.0 (derivado)':24} {net6:6d}")
    print("==================\n")
    _log("seed concluído.")


if __name__ == "__main__":
    main()
