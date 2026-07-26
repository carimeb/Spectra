/* Módulo Repositórios & Dependências — computed pattern: as métricas de cada
   repositório vivem prontas no objeto analysis{} do documento (o fim da function
   SQL de ~300 linhas). Tabela filtrável + drilldown com o documento cru e as
   consultas reais que a tela executa. */
(function () {
  const S = window.Spectra;

  async function render(view) {
    view.innerHTML = `
      <div class="view-head"><h2>Dashboard <span class="tag ok">computed pattern</span></h2>
        <div class="desc">A visão de BI do portfólio: cada repositório carrega as próprias métricas já calculadas
          dentro do documento, no objeto <code>analysis{}</code>, e esta tela (como o Power BI) apenas lê o campo
          pronto. Filtre e clique em uma linha para ver o documento exatamente como ele é lido.
          <span class="was">Era: function SQL de ~300 linhas com 6 CTEs, recalculada a cada consulta.</span></div></div>
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
      <div style="padding:0 28px">
        <div class="q-toggle"><a id="repo-q-link">⟨⟩ ver a consulta desta lista</a>
          <a id="repo-sql-link" style="margin-left:16px">⟨⟩ ver como o BI consulta via Atlas SQL</a></div>
        <div id="repo-q" class="hidden"></div>
        <div id="repo-sql" class="hidden">
          <div class="query-lead">o Atlas SQL expõe a collection como "tabela"; o Power BI lê pelo conector oficial
            (passo a passo completo em <a href="https://github.com/carimeb/Spectra/blob/main/docs/powerbi.md"
            target="_blank" rel="noopener" style="color:var(--info)">docs/powerbi.md</a>):</div>
          <div class="query-code" style="margin-bottom:6px">SELECT name, projectName, location, analysis.commitTotal
FROM repositories
WHERE analysis.isDeprecated = false
ORDER BY name LIMIT 40</div>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:18px;padding:6px 28px 28px">
        <div><div id="repo-total" class="muted" style="font-size:12px;margin-bottom:6px"></div><div id="repo-table"></div></div>
        <div id="repo-side">${donutPlaceholder()}</div>
      </div>`;

    document.getElementById("f-go").addEventListener("click", loadTable);
    document.getElementById("f-q").addEventListener("keydown", (e) => { if (e.key === "Enter") loadTable(); });
    document.getElementById("repo-q-link").addEventListener("click", () => {
      const open = document.getElementById("repo-q").classList.toggle("hidden");
      document.getElementById("repo-q-link").textContent =
        open ? "⟨⟩ ver a consulta desta lista" : "⟨⟩ ocultar a consulta";
    });
    document.getElementById("repo-sql-link").addEventListener("click", () => {
      const open = document.getElementById("repo-sql").classList.toggle("hidden");
      document.getElementById("repo-sql-link").textContent =
        open ? "⟨⟩ ver como o BI consulta via Atlas SQL" : "⟨⟩ ocultar o SQL";
    });
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

  // espelha, em notação de shell, a consulta que o backend executa para a lista
  function listQueryCode() {
    const fw = document.getElementById("f-fw").value;
    const dep = document.getElementById("f-dep").value;
    const q = document.getElementById("f-q").value.trim();
    const filter = [];
    let pre = "";
    if (fw) {
      const match = fw === "net48"
        ? '{ name: "Microsoft.AspNet.WebApi.Core" }'
        : `{ name: "Microsoft.AspNetCore.App", version: /^${fw.replace("net", "").split(".")[0]}\\./ }`;
      pre = "// o framework é DERIVADO da dependência de runtime (não há coluna):\n"
        + `const ids = db.dependencies.distinct("repositoryId", ${match})\n\n`;
      filter.push("_id: { $in: ids }");
    }
    if (dep) filter.push(`"analysis.isDeprecated": ${dep}`);
    if (q) filter.push(`name: /${q}/i`);
    return `${pre}db.repositories.find({ ${filter.join(", ")} })\n  .sort({ name: 1 }).limit(40)`;
  }

  async function loadTable() {
    const box = document.getElementById("repo-table");
    if (!box) return;
    box.innerHTML = `<div class="spinner">carregando…</div>`;
    document.getElementById("repo-q").innerHTML =
      `<div class="query-code" style="margin-bottom:6px">${S.highlightCode(listQueryCode())}</div>`;
    try {
      const data = await S.api(`/repositories?${qs()}`);
      const total = document.getElementById("repo-total");
      if (!total) return; // usuário já navegou para outro módulo
      total.textContent = `${data.total} repositórios (mostrando ${data.items.length})`;
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

  // o que cada métrica materializada significa (tooltips do drilldown)
  const ANALYSIS_HINTS = {
    isDeprecated: "descontinuado: não recebe mais evolução",
    isDeployable: "pode ser implantado (não é biblioteca)",
    isLib: "é biblioteca compartilhada, consumida por outros repositórios",
    isDeleted: "marcado como excluído na origem",
    repositoryType: "tipo do projeto (ex.: csproj)",
    hasLastCommit: "tem data de último commit registrada",
    commitTotal: "total de commits na história do repositório",
    hasSucceededDeploy: "já teve ao menos um deploy bem-sucedido",
    isOnCloudActive: "ativo em ambiente de nuvem",
    isOnServerActive: "ativo em servidor on-premises",
    isOnCloudActiveWithDeploy: "ativo na nuvem e com deploy bem-sucedido",
  };

  async function drill(id) {
    const side = document.getElementById("repo-side");
    if (!side) return;
    side.innerHTML = `<div class="spinner">carregando…</div>`;
    try {
      const { repository: r, vulnerabilities: v } = await S.api(`/repositories/${id}`);
      const a = r.analysis;
      const analysisRows = Object.entries(a).map(([k, val]) =>
        `<div style="display:flex;justify-content:space-between;font-size:12px;padding:3px 0;border-bottom:1px solid var(--border)">
          <span class="muted hint" title="${S.esc(ANALYSIS_HINTS[k] || "")}">${S.esc(k)}</span><b>${typeof val === "boolean" ? (val ? "✔" : "—") : val}</b></div>`).join("");
      const deps = (r.topDependencies || []).map((d) =>
        `<div style="font-size:12px;padding:2px 0"><span class="tag ${d.type === "framework" ? "info" : "neutral"}">${S.esc(d.type)}</span> ${S.esc(d.name)} <span class="muted">${S.esc(d.version)}</span></div>`).join("");
      const vulns = v.length
        ? v.slice(0, 8).map((x) => `<div style="font-size:12px;padding:2px 0"><span class="tag ${x.severity}">${S.esc(x.severity)}</span> ${S.esc(x.artifactDetails)} <span class="muted">${S.esc(x.status)}</span></div>`).join("")
        : `<div class="muted" style="font-size:12px">sem vulnerabilidades</div>`;
      side.innerHTML = `
        <div class="kpi-card" style="--rail:var(--primary)">
          <h3>${S.esc(r.name)}</h3>
          <div class="muted" style="font-size:12px;margin-bottom:8px">${S.esc(r.projectName)} · branch ${S.esc(r.defaultBranch || "—")}</div>
          <div class="label sec" style="margin-bottom:4px">analysis (computed pattern)</div>
          <div class="muted" style="font-size:11.5px;line-height:1.5;margin-bottom:8px">Resultado pré-calculado
            da antiga function de análise, gravado no documento durante a ingestão. A atualização acontece na
            <b>escrita</b>: quando um commit, deploy ou depreciação muda o estado, o processo que ingere o dado
            regrava estes campos. O banco não os recalcula sozinho. Passe o mouse em cada campo para ver o significado.</div>
          ${analysisRows}
        </div>
        <div class="kpi-card" style="--rail:var(--ok);margin-top:14px">
          <div class="label sec" style="margin-bottom:8px">Documento cru (como o BI lê)</div>
          <div class="query-lead" style="margin-top:0">db.repositories.findOne({ _id: ${S.esc(JSON.stringify(r._id))} })</div>
          <pre class="side-json">${S.highlightDoc(r, ["analysis"])}</pre>
        </div>
        <div class="kpi-card" style="--rail:var(--info);margin-top:14px"><div class="label sec" style="margin-bottom:8px">Top dependências</div>${deps || '<div class="muted">—</div>'}</div>
        <div class="kpi-card" style="--rail:var(--danger);margin-top:14px"><div class="label sec" style="margin-bottom:8px">Vulnerabilidades (${v.length})</div>${vulns}</div>`;
    } catch (e) {
      side.innerHTML = `<div class="spinner">erro ao abrir o repositório.</div>`;
    }
  }

  // donut simples de frameworks (SVG)
  function donutPlaceholder() { return `<div id="fw-donut" class="kpi-card" style="--rail:var(--warn)"><h3>Distribuição .NET</h3><div class="spinner">…</div></div>`; }
  async function loadDonut() {
    try {
      const s = await S.api("/stats");
      const box = document.getElementById("fw-donut");
      if (!box) return; // usuário já navegou para outro módulo
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
      box.innerHTML = `<h3>Distribuição .NET</h3>
        <svg viewBox="0 0 36 36" width="120" height="120" style="display:block;margin:0 auto 10px">${segs}</svg>${legend}`;
    } catch { /* */ }
  }

  S.register("repositories", { render });
})();
