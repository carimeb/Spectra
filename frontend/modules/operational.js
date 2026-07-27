/* Módulo Grafo Operacional — as duas consultas centrais do grafo operacional numa tela só:
   query B (estrutura): $graphLookup DESCE Area.ParentId e devolve a árvore pronta;
   query A (impacto): pipeline parte das dependências e SOBE a mesma hierarquia até a
   BU, pintando o resultado na própria árvore + ranking no painel lateral. */
(function () {
  const S = window.Spectra;
  const LEVEL = {
    company: { label: "empresa", cls: "saas" },
    directorate: { label: "diretoria", cls: "info" },
    bu: { label: "BU", cls: "ok" },
    squad: { label: "squad", cls: "neutral" },
  };
  const FRAMEWORKS = [
    { id: "net6.0", label: ".NET 6 (fim de suporte)" },
    { id: "net48", label: ".NET Framework 4.8 (legado)" },
    { id: "net8.0", label: ".NET 8 (atual)" },
  ];

  async function render(view) {
    view.innerHTML = `
      <div class="view-head"><h2>Hierarquia e Análise de Esforço <span class="tag info">grafo operacional</span></h2>
        <div class="desc">Repositórios ligados a áreas, hierarquia de áreas e responsáveis.
          Uma estrutura, duas perguntas:</div></div>

      <div class="dual-q">
        <div class="qcard">
          <div class="qcard-head"><span class="tag ok">query</span>
            <h3>Como a organização se estrutura?</h3>
            <span class="dir ok">↓ desce a hierarquia</span></div>
          <p>O <code>$graphLookup</code> parte da raiz e desce a adjacência <code>parentId</code>:
            a árvore abaixo chega pronta do banco, com os repositórios agregados por área.
            <span class="was">Era: CTE recursiva.</span></p>
          <div class="qcard-actions">
            <button class="btn-ghost" id="tree-expand">expandir tudo</button>
            <button class="btn-ghost" id="tree-collapse">recolher squads</button>
            <a id="tree-q-link" class="qlink">⟨⟩ ver a consulta</a>
          </div>
        </div>
        <div class="qcard">
          <div class="qcard-head"><span class="tag warn">query</span>
            <h3>Quem é afetado pela migração .NET?</h3>
            <span class="dir warn">↑ sobe até a BU</span></div>
          <p>O pipeline parte das <b>dependências</b> (a versão .NET é derivada do runtime) e sobe
            esta mesma hierarquia até a BU, com esforço e responsáveis.
            <span class="was">Era: function de ~300 linhas + JOINs.</span></p>
          <div class="qcard-actions">
            <select id="imp-fw">
              ${FRAMEWORKS.map((f) => `<option value="${f.id}">${f.id} · ${f.label}</option>`).join("")}
            </select>
            <button class="btn-primary" id="imp-run">Analisar impacto</button>
            <a id="imp-q-link" class="qlink hidden">⟨⟩ ver o pipeline</a>
          </div>
        </div>
      </div>

      <div class="op-queries">
        <div id="tree-q" class="hidden"></div>
        <div id="imp-q" class="hidden"></div>
      </div>

      <div class="op-body" id="op-body">
        <div>
          <div id="tree-summary" class="muted" style="font-size:12px;margin-bottom:6px"></div>
          <div id="tree-body"><div class="spinner">carregando hierarquia…</div></div>
        </div>
        <div id="impact-side" class="impact-side hidden"></div>
      </div>`;

    document.getElementById("tree-q-link").addEventListener("click", () => toggleQuery("tree-q", "tree-q-link", "⟨⟩ ver a consulta"));
    document.getElementById("imp-q-link").addEventListener("click", () => toggleQuery("imp-q", "imp-q-link", "⟨⟩ ver o pipeline"));
    document.getElementById("tree-expand").addEventListener("click", () =>
      document.querySelectorAll(".tree-node.collapsed").forEach((n) => n.classList.remove("collapsed")));
    document.getElementById("tree-collapse").addEventListener("click", () =>
      document.querySelectorAll(".tree-node.level-bu.has-kids").forEach((n) => n.classList.add("collapsed")));
    document.getElementById("imp-run").addEventListener("click", runImpact);
    document.getElementById("imp-fw").addEventListener("change", runImpact);

    try {
      const [tree, q, stats] = await Promise.all([
        S.api("/areas/tree"), S.api("/areas/tree/query"), S.api("/stats").catch(() => null),
      ]);
      const body = document.getElementById("tree-body");
      if (!body) return; // usuário já navegou para outro módulo

      // opções de .NET montadas a partir do que EXISTE na collection (não hardcoded)
      const byFw = (stats && stats.repositories && stats.repositories.byFramework) || {};
      const fwEntries = Object.entries(byFw).filter(([, n]) => n > 0).sort(([a], [b]) => a.localeCompare(b));
      if (fwEntries.length) {
        const label = { "net48": ".NET Framework 4.8", "net6.0": ".NET 6", "net8.0": ".NET 8" };
        document.getElementById("imp-fw").innerHTML = fwEntries.map(([id, n]) =>
          `<option value="${id}"${id === "net6.0" ? " selected" : ""}>${id} · ${label[id] || "runtime"} · ${n} repos</option>`).join("");
      }

      document.getElementById("tree-summary").textContent =
        `${countAreas(tree)} áreas · 4 níveis · ${subtreeRepos(tree)} repositórios`;
      document.getElementById("tree-q").innerHTML = q.steps.map((s) => `
        <div class="query-lead">${S.esc(s.title)} — db.${s.collection}.aggregate( … )</div>
        <div class="query-code" style="margin-bottom:12px">${S.highlightJSON(s.pipeline)}</div>`).join("");

      body.innerHTML = `<div class="area-tree">${nodeHtml(tree)}</div>`;
      body.querySelectorAll(".tree-node.level-bu.has-kids").forEach((n) => n.classList.add("collapsed"));
      body.querySelectorAll(".tree-node.has-kids > .tree-row").forEach((row) =>
        row.addEventListener("click", () => row.parentElement.classList.toggle("collapsed")));
    } catch (e) {
      const body = document.getElementById("tree-body");
      if (body) body.innerHTML = `<div class="spinner">erro ao carregar a hierarquia. Servidor no ar e seed rodado?</div>`;
    }
  }

  function toggleQuery(boxId, linkId, showText) {
    const open = document.getElementById(boxId).classList.toggle("hidden");
    document.getElementById(linkId).textContent = open ? showText : "⟨⟩ ocultar";
  }

  function countAreas(n) { return 1 + n.children.reduce((a, c) => a + countAreas(c), 0); }
  function subtreeRepos(n) { return n.repoCount + n.children.reduce((a, c) => a + subtreeRepos(c), 0); }

  function nodeHtml(n) {
    const lv = LEVEL[n.level] || { label: n.level, cls: "neutral" };
    const hasKids = n.children.length > 0;
    const kids = hasKids ? `<div class="tree-children">${n.children.map(nodeHtml).join("")}</div>` : "";
    return `<div class="tree-node level-${n.level}${hasKids ? " has-kids" : ""}">
      <div class="tree-row" data-id="${n.id}">
        <span class="tw">${hasKids ? "▾" : ""}</span>
        <span class="tag ${lv.cls}">${lv.label}</span>
        <span class="tree-name">${S.esc(n.name)}</span>
        <span class="tree-repos" title="repositórios na subárvore (diretos neste nó: ${n.repoCount})">${subtreeRepos(n)} repos</span>
      </div>
      ${kids}
    </div>`;
  }

  // ---- query A: pinta a árvore e monta o ranking lateral ----
  function clearImpact() {
    document.querySelectorAll(".tree-row.hit").forEach((r) => {
      r.classList.remove("hit");
      r.style.removeProperty("--rail");
      const chip = r.querySelector(".tree-hit");
      if (chip) chip.remove();
    });
  }

  async function runImpact() {
    const fw = document.getElementById("imp-fw").value;
    const side = document.getElementById("impact-side");
    side.classList.remove("hidden");
    document.getElementById("op-body").classList.add("with-side");
    side.innerHTML = `<div class="spinner">rodando a query A para ${S.esc(fw)}…</div>`;
    try {
      const [bus, q] = await Promise.all([
        S.api(`/graph/impact?framework=${encodeURIComponent(fw)}`),
        S.api(`/graph/impact/query?framework=${encodeURIComponent(fw)}`),
      ]);
      if (!document.getElementById("impact-side")) return;

      const qlink = document.getElementById("imp-q-link");
      qlink.classList.remove("hidden");
      document.getElementById("imp-q").innerHTML = `
        <div class="query-lead">db.${q.collection}.aggregate( … )</div>
        <div class="query-code" style="margin-bottom:12px">${S.highlightJSON(q.pipeline)}</div>`;

      clearImpact();
      // recolhe as squads para as BUs pintadas ficarem visíveis de uma vez
      document.querySelectorAll(".tree-node.level-bu.has-kids").forEach((n) => n.classList.add("collapsed"));

      const maxE = Math.max(...bus.map((b) => b.effortScore), 1);
      const railOf = (b) => b.effortScore > maxE * 0.66 ? "var(--danger)" : b.effortScore > maxE * 0.33 ? "var(--warn)" : "var(--ok)";
      bus.forEach((b) => {
        const row = document.querySelector(`.tree-row[data-id="${b.bu.id}"]`);
        if (!row) return;
        row.classList.add("hit");
        row.style.setProperty("--rail", railOf(b));
        row.querySelector(".tree-name").insertAdjacentHTML("afterend",
          `<span class="tree-hit">${b.appCount} apps · esforço ${b.effortScore}</span>`);
      });

      const totalRepos = bus.reduce((a, b) => a + b.repoCount, 0);
      const totalApps = bus.reduce((a, b) => a + b.appCount, 0);
      side.innerHTML = `
        <h3 style="margin:0 0 2px;font-size:15px;display:flex;justify-content:space-between;align-items:center">
          Impacto · ${S.esc(fw)} <span style="cursor:pointer;color:var(--muted)" id="imp-x">✕</span></h3>
        <div class="muted" style="font-size:12px;margin-bottom:8px">${bus.length} BUs · ${totalApps} aplicações · ${totalRepos} repositórios.
          As BUs destacadas na árvore são estas, ordenadas por esforço:</div>
        ${bus.slice().sort((a, b2) => b2.effortScore - a.effortScore).map((b) => {
          const eb = b.effortBreakdown;
          return `<div class="bu-card" data-bu="${b.bu.id}" style="--rail:${railOf(b)};cursor:pointer" title="localizar na árvore">
            <div class="bu-name">${S.esc(b.bu.name)}</div>
            <div class="bu-meta">${b.appCount} aplicações · ${b.repoCount} repositórios · esforço <b>${b.effortScore}</b></div>
            <div class="bu-meta">repos: ${eb.smallRepos} pequenos · ${eb.mediumRepos} médios · ${eb.largeRepos} grandes · ${eb.reposWithOpenVulns} com vulns</div>
            <div class="bu-meta">resp.: ${(b.managers || []).map((m) => S.esc(m.name)).join(", ") || "—"}</div>
            <div class="bar" style="width:${Math.round((b.effortScore / maxE) * 100)}%"></div>
          </div>`;
        }).join("")}
        <div class="muted" style="font-size:11.5px;margin-top:10px;padding:8px 10px;border:1px dashed var(--border);border-radius:8px">
          <b style="color:var(--text)">Como o esforço é calculado:</b> por repositório, 1, 2 ou 3 pontos pelo
          tamanho (até 200, até 1.000 ou mais de 1.000 commits) e +1 ponto se houver vulnerabilidade aberta
          high/critical. Tudo lido de campos já materializados (<code>analysis.commitTotal</code> +
          <code>vulnerabilities</code>), sem nenhuma CTE. A linha "repos:" de cada cartão mostra a composição.</div>`;

      document.getElementById("imp-x").addEventListener("click", () => {
        clearImpact();
        side.classList.add("hidden");
        document.getElementById("op-body").classList.remove("with-side");
      });
      side.querySelectorAll(".bu-card[data-bu]").forEach((card) =>
        card.addEventListener("click", () => {
          const row = document.querySelector(`.tree-row[data-id="${card.dataset.bu}"]`);
          if (!row) return;
          row.scrollIntoView({ behavior: "smooth", block: "center" });
          row.classList.add("flash");
          setTimeout(() => row.classList.remove("flash"), 1200);
        }));
    } catch (e) {
      side.innerHTML = `<div class="spinner">falhou ao rodar a análise. Servidor no ar e seed rodado?</div>`;
    }
  }

  S.register("operational", { render });
})();
