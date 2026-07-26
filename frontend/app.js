/* Spectra — núcleo do frontend: roteamento de módulos, fetch, saúde, Visão Geral. */
window.Spectra = (function () {
  const API = "/api";
  const modules = {};

  // ---- fetch helpers ----
  async function api(path) {
    const r = await fetch(API + path);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }
  async function apiPost(path, body) {
    const r = await fetch(API + path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error((await r.json()).detail || "erro");
    return r.json();
  }

  // ---- DOM helpers ----
  function el(html) {
    const t = document.createElement("template");
    t.innerHTML = html.trim();
    return t.content.firstElementChild;
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }
  // mapeia criticality/roadmap -> classe de cor (verde/âmbar/vermelho)
  function critClass(v) {
    return { high: "danger", critical: "danger", medium: "warn", low: "ok" }[v] || "neutral";
  }
  // syntax highlight simples de JSON (para o painel de query e o documento cru)
  function highlightJSON(obj) {
    let h = esc(JSON.stringify(obj, null, 2));
    h = h.replace(/(&quot;(?:[^&]|&(?!quot;))*?&quot;)(\s*:)/g, '<span class="jk">$1</span>$2');
    h = h.replace(/(:\s*)(&quot;(?:[^&]|&(?!quot;))*?&quot;)/g, '$1<span class="js">$2</span>');
    h = h.replace(/(:\s*)(-?\d+(?:\.\d+)?)/g, '$1<span class="jn">$2</span>');
    h = h.replace(/(:\s*)(true|false|null)/g, '$1<span class="jb">$2</span>');
    return h;
  }
  // highlight leve para comandos no estilo shell do MongoDB (db.coll.aggregate(...))
  function highlightCode(str) {
    let h = esc(str);
    h = h.replace(/(&quot;(?:[^&]|&(?!quot;))*?&quot;)/g, '<span class="js">$1</span>'); // strings
    h = h.replace(/(\$[a-zA-Z]+)/g, '<span class="jk">$1</span>'); // operadores $
    h = h.replace(/\b(true|false|null)\b/g, '<span class="jb">$1</span>');
    return h;
  }
  function register(name, mod) { modules[name] = mod; }

  // contraste "Antes (SQL Server) -> Agora (MongoDB)" — o argumento de venda de cada tela
  function callout(before, after) {
    return `<div class="value-callout">
      <div class="vc before"><span class="vc-tag">Antes · SQL Server</span><p>${esc(before)}</p></div>
      <div class="vc after"><span class="vc-tag">Agora · Spectra em MongoDB</span><p>${esc(after)}</p></div>
    </div>`;
  }

  // ---- roteamento de views ----
  function showView(name) {
    document.querySelectorAll(".nav-item").forEach((a) =>
      a.classList.toggle("active", a.dataset.view === name));
    const view = document.getElementById("view");
    view.innerHTML = "";
    if (name === "overview") renderOverview(view);
    else if (modules[name]) modules[name].render(view);
  }

  // ---- Visão Geral (KPIs) ----
  function kpiCard(title, rail, desc, nums) {
    const inner = nums
      .map((n) => `<div class="kpi-num ${n.cls || ""}"><b>${esc(n.value)}</b><small>${esc(n.label)}</small></div>`)
      .join("");
    return `<div class="kpi-card" style="--rail:var(--${rail})"><h3>${esc(title)}</h3>
      <div class="kpi-desc">${esc(desc)}</div><div class="kpi-nums">${inner}</div></div>`;
  }

  async function renderOverview(view) {
    view.appendChild(el(`<div class="view-head"><h2>Visão Geral</h2>
      <div class="desc">Um panorama de todo o portfólio de engenharia em um só lugar: repositórios,
      arquitetura, áreas, frameworks e vulnerabilidades. Use como ponto de partida e navegue para
      os módulos ao lado.</div></div>`));
    view.appendChild(el(`<div class="kpi-grid" id="kpis"><div class="spinner">carregando KPIs…</div></div>`));
    try {
      const s = await api("/stats");
      const loc = s.repositories.byLocation || {};
      const fw = s.repositories.byFramework || {};
      const sev = s.vulnerabilities.openBySeverity || {};
      const cloudPct = Math.round(((loc.cloud || 0) / s.repositories.total) * 100);
      const grid = document.getElementById("kpis");
      grid.innerHTML =
        kpiCard("Repositórios", "primary",
          "Todo o código-fonte catalogado. 'Libs' são bibliotecas compartilhadas e 'deprecados' são repositórios que não evoluem mais.", [
          { value: s.repositories.total, label: "total", cls: "info" },
          { value: s.repositories.deprecated, label: "deprecados", cls: "danger" },
          { value: s.repositories.libs, label: "libs", cls: "" },
        ]) +
        kpiCard("Cloud vs On-Prem", "ok",
          "Onde cada repositório roda hoje. Ajuda a enxergar o quanto a jornada para a nuvem já avançou.", [
          { value: cloudPct + "%", label: "na cloud", cls: "ok" },
          { value: loc.cloud || 0, label: "cloud (qtd)", cls: "ok" },
          { value: loc.server || 0, label: "on-prem", cls: "warn" },
        ]) +
        kpiCard("Frameworks .NET", "warn",
          "A versão do .NET de cada aplicação, deduzida das dependências. É a base para planejar migrações.", [
          { value: fw["net48"] || 0, label: "net48", cls: "danger" },
          { value: fw["net6.0"] || 0, label: "net6.0", cls: "warn" },
          { value: fw["net8.0"] || 0, label: "net8.0", cls: "ok" },
        ]) +
        kpiCard("Componentes de arquitetura", "saas",
          "Os blocos que formam a arquitetura (sistemas, aplicações, plataformas e infraestrutura) e como se conectam entre si.", [
          { value: s.components.total, label: "total", cls: "saas" },
          { value: s.components.byType.system || 0, label: "sistemas", cls: "info" },
          { value: s.components.byType.application || 0, label: "aplicações", cls: "" },
        ]) +
        kpiCard("Vulnerabilidades abertas", "danger",
          "Falhas de segurança ainda não resolvidas, separadas por gravidade. São o foco de prioridade dos times.", [
          { value: s.vulnerabilities.open, label: "abertas", cls: "danger" },
          { value: sev.critical || 0, label: "críticas", cls: "danger" },
          { value: sev.high || 0, label: "altas", cls: "warn" },
        ]) +
        kpiCard("Áreas & pessoas", "info",
          "A estrutura organizacional (das diretorias às squads) e quem responde por cada área, incluindo terceiros.", [
          { value: s.areas.total, label: "áreas", cls: "info" },
          { value: s.users.total, label: "pessoas", cls: "" },
          { value: s.users.terceiros, label: "terceiros", cls: "warn" },
        ]);
    } catch (e) {
      document.getElementById("kpis").innerHTML =
        `<div class="spinner">não foi possível carregar os KPIs. O servidor está no ar e o seed rodou?</div>`;
    }
    loadOverviewQueries(view);
  }

  // painel "ver as consultas" — mostra as agregações reais que alimentam os KPIs
  async function loadOverviewQueries(view) {
    view.appendChild(el(`<div style="padding:0 28px 28px">
      <div class="q-toggle"><a id="ov-q-link">⟨⟩ ver as consultas que alimentam estes números</a></div>
      <div id="ov-q" class="hidden"></div></div>`));
    const link = document.getElementById("ov-q-link");
    const box = document.getElementById("ov-q");
    link.addEventListener("click", () => {
      const open = box.classList.toggle("hidden");
      link.textContent = open
        ? "⟨⟩ ver as consultas que alimentam estes números"
        : "⟨⟩ ocultar as consultas";
    });
    try {
      const blocks = await api("/stats/query");
      box.innerHTML = blocks
        .map((b) => `<div class="query-lead">${esc(b.title)}</div>
          <div class="query-code" style="margin-bottom:12px">${highlightCode(b.code)}</div>`)
        .join("");
    } catch {
      box.innerHTML = `<div class="muted">não foi possível carregar as consultas.</div>`;
    }
  }

  // ---- indicador de conexão ----
  async function refreshHealth() {
    const c = document.getElementById("conn");
    try {
      const h = await api("/health");
      if (h.status === "ok") {
        c.className = "conn ok";
        c.innerHTML = `<span class="dot"></span> Atlas conectado`;
      } else throw new Error();
    } catch {
      c.className = "conn bad";
      c.innerHTML = `<span class="dot"></span> sem conexão`;
    }
  }

  function openDemo() {
    document.getElementById("landing").classList.add("hidden");
    document.getElementById("app").classList.remove("hidden");
    showView("overview");
    refreshHealth();
  }

  function goHome() {
    document.getElementById("app").classList.add("hidden");
    document.getElementById("landing").classList.remove("hidden");
    window.scrollTo(0, 0);
  }

  function init() {
    document.getElementById("open-demo").addEventListener("click", openDemo);
    document.getElementById("open-demo-top").addEventListener("click", openDemo);
    document.getElementById("go-home").addEventListener("click", goHome);
    document.querySelectorAll(".nav-item[data-view]").forEach((a) =>
      a.addEventListener("click", () => showView(a.dataset.view)));
  }

  return { init, register, api, apiPost, el, esc, critClass, highlightJSON, callout, showView };
})();
