/* Módulo Mapa & Grafo — tela dedicada ao grafo de ARQUITETURA (componente ↔
   componente, arestas não-tipadas). A Análise de Impacto (query A) mora em módulo
   próprio: ela percorre o grafo OPERACIONAL (repositórios → áreas), que na fonte
   é independente deste mapa. */
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
          <div>
            <div class="map-title">Mapa &amp; Grafo <span class="tag saas">grafo de arquitetura</span></div>
            <div class="map-caption">as ligações moram dentro de cada documento (<code>relations[]</code>) e o <code>$graphLookup</code> percorre o grafo em um único comando: sem tabela de arestas, sem JOINs recursivos</div>
          </div>
          <div class="search">
            <input id="comp-search" list="comp-list" placeholder="Buscar componente…" />
            <datalist id="comp-list"></datalist>
          </div>
          <button class="btn-ghost" id="btn-fit" title="Reenquadrar o grafo na tela">⤢ ajustar</button>
        </div>
        <div class="map-sub">Cada nó é um componente da arquitetura e as setas mostram do que ele depende.
          Clique em um nó para expandir a vizinhança e abrir os detalhes.
          Procurando o impacto da migração .NET? Ele fica em
          <a id="go-impact" style="color:var(--info)">Hierarquia e Análise de Esforço</a>: aquela consulta
          percorre o grafo operacional (repositórios e áreas), que na fonte é independente deste mapa.</div>
        <div class="ribbon-row">
          <div class="stats-inline" id="ribbon"><span class="muted">carregando…</span></div>
          <div class="chip-bar inline">
            <span class="chip arrow-hint"><b>A&nbsp;→&nbsp;B</b>&nbsp;A depende de B</span>
            ${Object.entries(TYPE_COLOR).map(([t, c]) =>
              `<span class="chip"><span class="cdot" style="background:${c}"></span>${t}</span>`).join("")}
          </div>
        </div>
        <div class="map-body" style="position:relative">
          <div id="graph-canvas"></div>
          <div id="drawer" class="drawer hidden"></div>
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

    // listeners estáticos ANTES de qualquer await, para a tela responder de imediato
    const search = document.getElementById("comp-search");
    search.addEventListener("change", (e) => {
      const opt = [...document.querySelectorAll("#comp-list option")].find((o) => o.value === e.target.value);
      if (opt) {
        expand(opt.dataset.id, true);
        // limpa o campo: o datalist filtra pelo texto digitado, então sem limpar
        // o próximo clique na setinha só mostraria a opção já selecionada
        e.target.value = "";
      }
    });
    search.addEventListener("focus", (e) => e.target.select());
    document.getElementById("btn-fit").addEventListener("click", () => network.fit({ animation: true }));
    document.getElementById("go-impact").addEventListener("click", () => S.showView("operational"));

    loadStats();
    loadSearch();
    await expand(START);
    network.once("stabilized", () => network.fit());
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
      const [c, q, hood] = await Promise.all([
        S.api(`/schema/components/${id}`),
        S.api(`/graph/component/${id}/query?depth=2`),
        S.api(`/graph/component/${id}?depth=1`), // vizinhos diretos, nos dois sentidos
      ]);
      const labels = {};
      hood.nodes.forEach((n) => { labels[n.id] = n.label; });
      // seta A -> B = "A depende de B": saindo do nó = dependências; chegando = dependentes
      const dependsOn = hood.edges.filter((e) => e.from === id)
        .map((e) => ({ id: e.to, name: labels[e.to] || e.to }));
      const dependedBy = hood.edges.filter((e) => e.to === id)
        .map((e) => ({ id: e.from, name: labels[e.from] || e.from }));
      const depList = (list) => list.length
        ? `<div class="dep-list">${list.map((x) =>
            `<a class="dep-link" data-id="${x.id}">${S.esc(x.name)}</a>`).join("")}</div>`
        : `<div class="value muted">nenhum</div>`;
      const attrs = Object.entries(c.attributes || {})
        .map(([k, v]) => `<div class="field"><div class="label">${S.esc(k)}</div><div class="value">${badge(k, v)}</div></div>`)
        .join("") || `<div class="muted">sem atributos</div>`;
      d.innerHTML = `
        <h3><span>★ ${S.esc(c.name)}</span><span style="cursor:pointer" id="drawer-x">✕</span></h3>
        <div class="field"><div class="label sec">Tipo</div><div class="value"><span class="tag info">${S.esc(c.type)}</span></div></div>
        <div class="field"><div class="label sec">Descrição</div><div class="value muted">${S.esc(c.description || "—")}</div></div>
        <div class="field"><div class="label sec">Depende de (setas saindo) · ${dependsOn.length}</div>${depList(dependsOn)}</div>
        <div class="field"><div class="label sec">Dependentes (setas chegando) · ${dependedBy.length}</div>${depList(dependedBy)}</div>
        <div class="label sec big-gap">Atributos (esquema flexível)</div>
        ${attrs}
        <div class="label sec big-gap">Documento cru</div>
        <pre>${S.highlightDoc(c, ["relations"])}</pre>
        <div class="q-toggle"><a id="drawer-q-link">⟨⟩ ver o $graphLookup desta vizinhança</a></div>
        <div id="drawer-q" class="hidden">
          <div class="query-lead">db.${q.collection}.aggregate( … )</div>
          <div class="query-code">${S.highlightJSON(q.pipeline)}</div>
        </div>`;
      d.classList.remove("hidden");
      document.getElementById("drawer-x").addEventListener("click", () => d.classList.add("hidden"));
      d.querySelectorAll(".dep-link").forEach((a) =>
        a.addEventListener("click", () => expand(a.dataset.id, true)));
      const link = document.getElementById("drawer-q-link");
      link.addEventListener("click", () => {
        const open = document.getElementById("drawer-q").classList.toggle("hidden");
        link.textContent = open ? "⟨⟩ ver o $graphLookup desta vizinhança" : "⟨⟩ ocultar a consulta";
      });
    } catch { /* ignore */ }
  }

  function badge(key, v) {
    if (typeof v === "boolean") return `<span class="tag ${v ? "ok" : "neutral"}">${v}</span>`;
    if (key === "criticality") return `<span class="tag ${S.critClass(v)}">${S.esc(v)}</span>`;
    return `<span class="tag neutral">${S.esc(v)}</span>`;
  }

  S.register("graph", { render });
})();
