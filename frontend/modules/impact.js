/* Módulo Análise de Impacto — query-herói A sobre o grafo OPERACIONAL:
   dependencies (versão .NET derivada) → repositories (analysis{} pronto) →
   $graphLookup subindo a hierarquia de áreas até a BU → responsáveis.
   Separado do Mapa & Grafo de propósito: são dois grafos independentes na fonte. */
(function () {
  const S = window.Spectra;
  const FRAMEWORKS = [
    { id: "net6.0", label: ".NET 6 (fim de suporte)" },
    { id: "net48", label: ".NET Framework 4.8 (legado)" },
    { id: "net8.0", label: ".NET 8 (atual)" },
  ];

  function flowStep(coll, text) {
    return `<div class="flow-step"><b>${coll}</b><small>${text}</small></div>`;
  }

  async function render(view) {
    view.innerHTML = `
      <div class="view-head"><h2>Análise de Impacto <span class="tag info">grafo operacional</span></h2>
        <div class="desc">A pergunta-norte da plataforma: aplicações em uma versão do .NET precisam migrar.
          Quais áreas de negócio são afetadas, quantas aplicações e quem são os responsáveis?
          A resposta inteira sai de um único pipeline de agregação (a query A).</div></div>
      ${S.callout(
        "A resposta dependia da função de análise (~300 linhas, 6 CTEs), de JOINs entre dependências, repositórios e áreas, e de uma CTE recursiva para subir a hierarquia organizacional.",
        "Um único pipeline: $match deriva a versão .NET da dependência de runtime, $lookup junta o repositório com as métricas prontas em analysis{} e $graphLookup sobe a hierarquia de áreas até a BU."
      )}
      <div class="flow-strip">
        ${flowStep("dependencies", "ponto de partida: a versão .NET é derivada da dependência de runtime (nome + versão), sem coluna nova")}
        <span class="flow-arrow">→</span>
        ${flowStep("repositories", "$lookup junta o repositório; as métricas já estão prontas no objeto analysis{}")}
        <span class="flow-arrow">→</span>
        ${flowStep("areas", "$graphLookup sobe a hierarquia organizacional (parentId) até a BU")}
        <span class="flow-arrow">→</span>
        ${flowStep("users", "$lookup traz os responsáveis da BU (manager e tech lead)")}
      </div>
      <div class="filters">
        <label>Versão .NET de origem
          <select id="imp-fw">
            ${FRAMEWORKS.map((f) => `<option value="${f.id}">${f.id} · ${f.label}</option>`).join("")}
          </select>
        </label>
        <button class="btn-primary" id="imp-run" style="height:36px">Analisar impacto</button>
        <span class="muted" id="imp-summary" style="font-size:13px;padding-bottom:9px"></span>
      </div>
      <div style="padding:0 28px">
        <div class="q-toggle hidden" id="imp-q-toggle"><a id="imp-q-link">⟨⟩ ver o pipeline que roda no MongoDB</a></div>
        <div id="imp-q" class="hidden"></div>
        <div class="muted hidden" id="imp-legend" style="font-size:12px;margin:6px 0 2px">
          O esforço soma, por repositório, pontos de tamanho (commits) e de risco (vulnerabilidade aberta
          high/critical), tudo lido de campos já materializados no documento. O detalhamento em cada cartão explica o número.
        </div>
      </div>
      <div id="imp-body" class="impact-grid"></div>`;

    document.getElementById("imp-run").addEventListener("click", run);
    document.getElementById("imp-fw").addEventListener("change", run);
    document.getElementById("imp-q-link").addEventListener("click", () => {
      const open = document.getElementById("imp-q").classList.toggle("hidden");
      document.getElementById("imp-q-link").textContent =
        open ? "⟨⟩ ver o pipeline que roda no MongoDB" : "⟨⟩ ocultar o pipeline";
    });
    run();
  }

  async function run() {
    const fw = document.getElementById("imp-fw").value;
    const body = document.getElementById("imp-body");
    const summary = document.getElementById("imp-summary");
    body.innerHTML = `<div class="spinner">rodando a query A para ${S.esc(fw)}…</div>`;
    summary.textContent = "";
    try {
      const [bus, q] = await Promise.all([
        S.api(`/graph/impact?framework=${encodeURIComponent(fw)}`),
        S.api(`/graph/impact/query?framework=${encodeURIComponent(fw)}`),
      ]);

      document.getElementById("imp-q-toggle").classList.remove("hidden");
      document.getElementById("imp-q").innerHTML = `
        <div class="query-lead">db.${q.collection}.aggregate( … )</div>
        <div class="query-code">${S.highlightJSON(q.pipeline)}</div>`;

      if (!bus.length) {
        body.innerHTML = `<div class="spinner">nenhum repositório em ${S.esc(fw)} foi encontrado.</div>`;
        document.getElementById("imp-legend").classList.add("hidden");
        return;
      }

      const totalRepos = bus.reduce((a, b) => a + b.repoCount, 0);
      const totalApps = bus.reduce((a, b) => a + b.appCount, 0);
      summary.textContent = `${bus.length} BUs afetadas · ${totalApps} aplicações · ${totalRepos} repositórios`;
      document.getElementById("imp-legend").classList.remove("hidden");

      const maxE = Math.max(...bus.map((b) => b.effortScore), 1);
      body.innerHTML = bus.map((b) => {
        const rail = b.effortScore > maxE * 0.66 ? "danger" : b.effortScore > maxE * 0.33 ? "warn" : "ok";
        const eb = b.effortBreakdown;
        return `<div class="bu-card" style="--rail:var(--${rail})">
          <div class="bu-name">${S.esc(b.bu.name)}</div>
          <div class="bu-meta">${b.appCount} aplicações · ${b.repoCount} repositórios · esforço <b>${b.effortScore}</b></div>
          <div class="bu-meta">repos: ${eb.smallRepos} pequenos · ${eb.mediumRepos} médios · ${eb.largeRepos} grandes · ${eb.reposWithOpenVulns} com vulns abertas</div>
          <div class="bu-meta">responsáveis: ${(b.managers || []).map((m) => S.esc(m.name)).join(", ") || "—"}</div>
          <div class="bar" style="width:${Math.round((b.effortScore / maxE) * 100)}%"></div>
        </div>`;
      }).join("");
    } catch (e) {
      body.innerHTML = `<div class="spinner">falhou ao rodar a análise. Servidor no ar e seed rodado?</div>`;
    }
  }

  S.register("impact", { render });
})();
