/* Módulo Mapa & Grafo (tema escuro) — grafo de arquitetura via vis-network,
   drawer de detalhe, e "Análise de impacto" (query A) pintando as BUs. */
(function () {
  const S = window.Spectra;
  const TYPE_COLOR = {
    system: "#2E5BFF", application: "#38BDF8", platform: "#8B5CF6",
    database: "#94A3B8", queue: "#F59E0B", integration: "#22C55E",
  };
  const START = "comp-motor-de-credito"; // âncora inicial
  let network, nodes, edges, seen;

  async function render(view) {
    view.innerHTML = `
      <div class="map-wrap">
        <div class="map-topbar">
          <div class="brand"><span class="prism"></span> Mapa &amp; Grafo</div>
          <div class="search">
            <input id="comp-search" list="comp-list" placeholder="Buscar componente…" />
            <datalist id="comp-list"></datalist>
          </div>
          <button class="btn-primary" id="btn-impact">Análise de impacto (net6.0)</button>
        </div>
        <div class="map-sub">Cada nó é um componente da arquitetura e as ligações mostram do que ele depende.
          Clique em um nó para explorar a vizinhança e ver seus detalhes; use a busca para ir direto a um componente.</div>
        <div class="stats-ribbon" id="ribbon"><span class="muted">carregando…</span></div>
        <div class="map-body" style="position:relative">
          <div id="graph-canvas"></div>
          <div id="drawer" class="drawer hidden"></div>
          <div id="impact" class="impact-panel hidden"></div>
        </div>
        <div class="chip-bar">
          ${Object.entries(TYPE_COLOR).map(([t, c]) =>
            `<span class="chip"><span class="cdot" style="background:${c}"></span>${t}</span>`).join("")}
        </div>
      </div>`;

    nodes = new vis.DataSet();
    edges = new vis.DataSet();
    seen = new Set();
    network = new vis.Network(document.getElementById("graph-canvas"), { nodes, edges }, {
      nodes: { shape: "dot", size: 14, font: { color: "#E8ECF5", size: 13 }, borderWidth: 2 },
      edges: { color: { color: "#26304F", highlight: "#2E5BFF" }, arrows: { to: { enabled: true, scaleFactor: 0.5 } }, smooth: { type: "continuous" } },
      physics: { stabilization: true, barnesHut: { gravitationalConstant: -6000, springLength: 120 } },
      interaction: { hover: true },
    });
    network.on("click", (p) => { if (p.nodes.length) onNodeClick(p.nodes[0]); });

    loadStats();
    loadSearch();
    await expand(START);
    network.once("stabilized", () => network.fit());

    document.getElementById("comp-search").addEventListener("change", (e) => {
      const opt = [...document.querySelectorAll("#comp-list option")].find((o) => o.value === e.target.value);
      if (opt) expand(opt.dataset.id, true);
    });
    document.getElementById("btn-impact").addEventListener("click", showImpact);
  }

  async function loadStats() {
    try {
      const s = await S.api("/stats");
      const t = s.components.byType;
      document.getElementById("ribbon").innerHTML = `
        <span class="stat"><b>${s.components.total}</b> <span>componentes</span></span>
        <span class="stat"><b>${t.system || 0}</b> <span>sistemas</span></span>
        <span class="stat"><b>${t.application || 0}</b> <span>aplicações</span></span>
        <span class="stat"><b>${t.platform || 0}</b> <span>plataformas</span></span>
        <span class="stat"><b>${(t.database||0)+(t.queue||0)+(t.integration||0)}</b> <span>infra</span></span>`;
    } catch { /* silencioso */ }
  }

  async function loadSearch() {
    try {
      const list = await S.api("/graph/components");
      document.getElementById("comp-list").innerHTML = list
        .map((c) => `<option data-id="${c.id}" value="${S.esc(c.name)}">${c.type}</option>`).join("");
    } catch { /* silencioso */ }
  }

  async function expand(id, focus) {
    try {
      const { nodes: ns, edges: es } = await S.api(`/graph/component/${id}?depth=2`);
      ns.forEach((n) => {
        if (!seen.has(n.id)) {
          seen.add(n.id);
          nodes.add({ id: n.id, label: n.label, color: { background: TYPE_COLOR[n.type] || "#94A3B8", border: "#0B1020" } });
        }
      });
      es.forEach((e) => {
        const key = e.from + "->" + e.to;
        if (!seen.has(key)) { seen.add(key); edges.add({ id: key, from: e.from, to: e.to }); }
      });
      if (focus) { network.selectNodes([id]); network.focus(id, { scale: 1.0, animation: true }); onNodeClick(id); }
    } catch (e) { /* nó inexistente */ }
  }

  async function onNodeClick(id) {
    await expand(id); // clicar expande a vizinhança
    const d = document.getElementById("drawer");
    try {
      const c = await S.api(`/schema/components/${id}`);
      const attrs = Object.entries(c.attributes || {})
        .map(([k, v]) => `<div class="field"><div class="label">${S.esc(k)}</div><div class="value">${badge(k, v)}</div></div>`)
        .join("") || `<div class="muted">sem atributos</div>`;
      d.innerHTML = `
        <h3><span>★ ${S.esc(c.name)}</span><span style="cursor:pointer" id="drawer-x">✕</span></h3>
        <div class="field"><div class="label">Tipo</div><div class="value"><span class="tag info">${S.esc(c.type)}</span></div></div>
        <div class="field"><div class="label">Descrição</div><div class="value muted">${S.esc(c.description || "—")}</div></div>
        <div class="field"><div class="label">Relações (depende de)</div><div class="value">${(c.relations || []).length}</div></div>
        <div class="label" style="margin-top:14px">Atributos (esquema flexível)</div>
        ${attrs}
        <div class="label" style="margin-top:14px">Documento cru</div>
        <pre>${S.esc(JSON.stringify(c, null, 2))}</pre>`;
      d.classList.remove("hidden");
      document.getElementById("drawer-x").addEventListener("click", () => d.classList.add("hidden"));
    } catch { /* ignore */ }
  }

  function badge(key, v) {
    if (typeof v === "boolean") return `<span class="tag ${v ? "ok" : "neutral"}">${v}</span>`;
    if (key === "criticality") return `<span class="tag ${S.critClass(v)}">${S.esc(v)}</span>`;
    return `<span class="tag neutral">${S.esc(v)}</span>`;
  }

  async function showImpact() {
    const panel = document.getElementById("impact");
    panel.classList.remove("hidden");
    panel.innerHTML = `<h3 style="display:flex;justify-content:space-between">Impacto · net6.0
      <span style="cursor:pointer" id="imp-x">✕</span></h3><div class="spinner">rodando query A…</div>`;
    document.getElementById("imp-x").addEventListener("click", () => panel.classList.add("hidden"));
    try {
      const [bus, q] = await Promise.all([
        S.api("/graph/impact?framework=net6.0"),
        S.api("/graph/impact/query?framework=net6.0"),
      ]);
      const maxE = Math.max(...bus.map((b) => b.effortScore), 1);
      const body = bus.map((b) => {
        const rail = b.effortScore > maxE * 0.66 ? "danger" : b.effortScore > maxE * 0.33 ? "warn" : "ok";
        const eb = b.effortBreakdown;
        return `<div class="bu-card" style="--rail:var(--${rail})">
          <div class="bu-name">${S.esc(b.bu.name)}</div>
          <div class="bu-meta">${b.appCount} apps · ${b.repoCount} repos · esforço <b>${b.effortScore}</b></div>
          <div class="bu-meta">P/M/G: ${eb.smallRepos}/${eb.mediumRepos}/${eb.largeRepos} · vulns: ${eb.reposWithOpenVulns}</div>
          <div class="bu-meta">resp.: ${(b.managers || []).map((m) => S.esc(m.name)).join(", ") || "—"}</div>
          <div class="bar" style="width:${Math.round((b.effortScore / maxE) * 100)}%"></div>
        </div>`;
      }).join("");
      panel.innerHTML = `<h3 style="display:flex;justify-content:space-between">Impacto · net6.0 · ${bus.length} BUs
        <span style="cursor:pointer" id="imp-x2">✕</span></h3>
        <div class="muted" style="font-size:12px;margin-bottom:8px">No modelo relacional, esta resposta dependia da função de análise e de JOINs recursivos entre repositórios, dependências e áreas. Aqui é um único pipeline de agregação.</div>
        <div class="q-toggle"><a id="q-link">⟨⟩ ver o pipeline que roda no MongoDB</a></div>
        <div id="q-wrap" class="hidden">
          <div class="query-lead">db.${q.collection}.aggregate( … )</div>
          <div class="query-code">${S.highlightJSON(q.pipeline)}</div>
        </div>
        <div class="muted" style="font-size:12px;margin:10px 0 6px">Aplicações .NET 6 afetadas por BU:</div>${body}`;
      document.getElementById("imp-x2").addEventListener("click", () => panel.classList.add("hidden"));
      const link = document.getElementById("q-link");
      link.addEventListener("click", () => {
        const w = document.getElementById("q-wrap");
        const open = w.classList.toggle("hidden");
        link.textContent = open ? "⟨⟩ ver o pipeline que roda no MongoDB" : "⟨⟩ ocultar o pipeline";
      });
    } catch (e) {
      panel.innerHTML += `<div class="spinner">falhou ao rodar a análise.</div>`;
    }
  }

  S.register("graph", { render });
})();
