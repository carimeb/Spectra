/* Módulo Repositórios & Dependências — tabela filtrável (estilo Power BI) +
   drilldown com o objeto analysis{} em destaque ("o fim da function de 300 linhas"). */
(function () {
  const S = window.Spectra;

  async function render(view) {
    view.innerHTML = `
      <div class="view-head"><h2>Repositórios &amp; Dependências</h2>
        <div class="desc">Cada repositório traz suas próprias métricas já calculadas dentro do documento (o objeto <code>analysis{}</code>). O que antes exigia uma função SQL de centenas de linhas agora é leitura direta. Filtre e clique em uma linha para ver os detalhes.</div></div>
      ${S.callout(
        "As métricas de cada repositório saíam de uma função SQL de centenas de linhas com vários CTEs, difícil de manter e de evoluir.",
        "Cada repositório já carrega as métricas prontas no objeto analysis, e o BI lê direto do documento, sem depender da função."
      )}
      <div class="filters">
        <label>Framework .NET
          <select id="f-fw"><option value="">todos</option><option>net48</option><option>net6.0</option><option>net8.0</option></select>
        </label>
        <label>Depreciado
          <select id="f-dep"><option value="">todos</option><option value="true">só depreciados</option><option value="false">só ativos</option></select>
        </label>
        <label>Busca<input id="f-q" placeholder="nome do repo" /></label>
        <button class="btn-primary" id="f-go" style="height:36px">Filtrar</button>
      </div>
      <div style="display:grid;grid-template-columns:1fr 320px;gap:18px;padding:0 28px 28px">
        <div><div id="repo-total" class="muted" style="font-size:12px;margin-bottom:6px"></div><div id="repo-table"></div></div>
        <div id="repo-side">${donutPlaceholder()}</div>
      </div>`;

    ["f-go"].forEach((id) => document.getElementById(id).addEventListener("click", loadTable));
    document.getElementById("f-q").addEventListener("keydown", (e) => { if (e.key === "Enter") loadTable(); });
    loadDonut();
    loadTable();
  }

  function qs() {
    const fw = document.getElementById("f-fw").value;
    const dep = document.getElementById("f-dep").value;
    const q = document.getElementById("f-q").value.trim();
    const p = new URLSearchParams({ limit: "40" });
    if (fw) p.set("framework", fw);
    if (dep) p.set("deprecated", dep);
    if (q) p.set("q", q);
    return p.toString();
  }

  async function loadTable() {
    const box = document.getElementById("repo-table");
    box.innerHTML = `<div class="spinner">carregando…</div>`;
    try {
      const data = await S.api(`/repositories?${qs()}`);
      document.getElementById("repo-total").textContent = `${data.total} repositórios (mostrando ${data.items.length})`;
      const rows = data.items.map((r) => `
        <tr data-id="${r._id}">
          <td>${S.esc(r.name)}</td>
          <td>${S.esc(r.projectName)}</td>
          <td><span class="tag ${r.location === "cloud" ? "ok" : r.location === "server" ? "warn" : "neutral"}">${S.esc(r.location)}</span></td>
          <td>${r.analysis.commitTotal}</td>
          <td>${r.analysis.isDeprecated ? '<span class="tag danger">sim</span>' : '<span class="tag ok">não</span>'}</td>
        </tr>`).join("");
      box.innerHTML = `<table class="grid"><thead><tr>
        <th>Repositório</th><th>Projeto</th><th>Location</th><th>Commits</th><th>Deprecado</th>
        </tr></thead><tbody>${rows}</tbody></table>`;
      box.querySelectorAll("tr[data-id]").forEach((tr) =>
        tr.addEventListener("click", () => drill(tr.dataset.id)));
    } catch (e) {
      box.innerHTML = `<div class="spinner">erro ao carregar. Servidor no ar e seed rodado?</div>`;
    }
  }

  async function drill(id) {
    const side = document.getElementById("repo-side");
    side.innerHTML = `<div class="spinner">carregando…</div>`;
    try {
      const { repository: r, vulnerabilities: v } = await S.api(`/repositories/${id}`);
      const a = r.analysis;
      const analysisRows = Object.entries(a).map(([k, val]) =>
        `<div style="display:flex;justify-content:space-between;font-size:12px;padding:3px 0;border-bottom:1px solid var(--border)">
          <span class="muted">${S.esc(k)}</span><b>${typeof val === "boolean" ? (val ? "✔" : "—") : val}</b></div>`).join("");
      const deps = (r.topDependencies || []).map((d) =>
        `<div style="font-size:12px;padding:2px 0"><span class="tag ${d.type === "framework" ? "info" : "neutral"}">${S.esc(d.type)}</span> ${S.esc(d.name)} <span class="muted">${S.esc(d.version)}</span></div>`).join("");
      const vulns = v.length
        ? v.slice(0, 8).map((x) => `<div style="font-size:12px;padding:2px 0"><span class="tag ${x.severity}">${S.esc(x.severity)}</span> ${S.esc(x.artifactDetails)} <span class="muted">${S.esc(x.status)}</span></div>`).join("")
        : `<div class="muted" style="font-size:12px">sem vulnerabilidades</div>`;
      side.innerHTML = `
        <div class="kpi-card" style="--rail:var(--primary)">
          <h3>${S.esc(r.name)}</h3>
          <div class="muted" style="font-size:12px;margin-bottom:8px">${S.esc(r.projectName)} · branch ${S.esc(r.defaultBranch || "—")}</div>
          <div class="label" style="text-transform:uppercase;font-size:11px;color:var(--muted);margin-bottom:4px">analysis (computed pattern)</div>
          ${analysisRows}
        </div>
        <div class="kpi-card" style="--rail:var(--info);margin-top:14px"><h3>Top dependências</h3>${deps || '<div class="muted">—</div>'}</div>
        <div class="kpi-card" style="--rail:var(--danger);margin-top:14px"><h3>Vulnerabilidades (${v.length})</h3>${vulns}</div>`;
    } catch (e) {
      side.innerHTML = `<div class="spinner">erro ao abrir o repositório.</div>`;
    }
  }

  // donut simples de frameworks (SVG)
  function donutPlaceholder() { return `<div id="fw-donut" class="kpi-card" style="--rail:var(--warn)"><h3>Distribuição .NET</h3><div class="spinner">…</div></div>`; }
  async function loadDonut() {
    try {
      const s = await S.api("/stats");
      const fw = s.repositories.byFramework;
      const total = Object.values(fw).reduce((a, b) => a + b, 0) || 1;
      const colors = { net48: "#EF4444", "net6.0": "#F59E0B", "net8.0": "#22C55E" };
      let acc = 0, segs = "";
      for (const [k, val] of Object.entries(fw)) {
        const frac = val / total, dash = frac * 100;
        segs += `<circle r="15.9155" cx="18" cy="18" fill="transparent" stroke="${colors[k] || "#94A3B8"}"
          stroke-width="5" stroke-dasharray="${dash} ${100 - dash}" stroke-dashoffset="${25 - acc}"></circle>`;
        acc += dash;
      }
      const legend = Object.entries(fw).map(([k, val]) =>
        `<div style="font-size:12px;display:flex;align-items:center;gap:6px"><span class="cdot" style="width:10px;height:10px;border-radius:50%;background:${colors[k]||"#94A3B8"};display:inline-block"></span>${k} <b style="margin-left:auto">${val}</b></div>`).join("");
      document.getElementById("fw-donut").innerHTML = `<h3>Distribuição .NET</h3>
        <svg viewBox="0 0 36 36" width="120" height="120" style="display:block;margin:0 auto 10px">${segs}</svg>${legend}`;
    } catch { /* */ }
  }

  S.register("repositories", { render });
})();
