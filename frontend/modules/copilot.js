/* Módulo Copilot — chat em pt-BR sobre /api/copilot/chat + painel "por baixo dos
   panos" na coluna direita: as ferramentas do agente (acendem quando usadas) e a
   memória persistida no Atlas (lida DE VOLTA de agent_checkpoints a cada turno).
   Mostra o MongoDB como banco de memória/plataforma para agentes. */
(function () {
  const S = window.Spectra;
  const SUGGESTIONS = [
    "Quais BUs são afetadas se migrarmos as apps de net6.0 para net8.0?",
    "Quais sistemas dependem do Motor de Crédito?",
    "Existe algum sistema relacionado a conciliação de pagamentos?",
    "Quem é o responsável técnico da área Cartões?",
  ];
  // as 4 ferramentas curadas do agente (mesmas consultas das outras telas)
  const TOOLS_META = [
    { id: "hybrid_search", graph: "arquitetura", cls: "saas",
      desc: "busca componentes por texto via Atlas Search (name + description)" },
    { id: "graph_traversal", graph: "arquitetura", cls: "saas",
      desc: "$graphLookup em relations[]: quem depende dele / do que ele depende" },
    { id: "impact_analysis", graph: "operacional", cls: "info",
      desc: "pipeline do impacto .NET: dependências → repositórios → áreas → responsáveis" },
    { id: "area_info", graph: "operacional", cls: "info",
      desc: "área organizacional: gestor, tech lead, repositórios e cadeia hierárquica" },
  ];
  const ROLE_LABEL = { human: "pergunta", ai: "resposta", tool: "ferramenta" };
  const sessionId = (crypto.randomUUID && crypto.randomUUID()) || String(Date.now());
  let history = []; // [{role, text, toolCalls}]
  let busy = false;

  async function render(view) {
    view.innerHTML = `
      <div class="chat-wrap">
        <div class="view-head"><h2>Copilot <span class="tag saas">agente sobre os dados</span></h2>
          <div class="desc">Pergunte em português sobre o portfólio. O agente consulta o MongoDB com as
            mesmas travessias das outras telas, e o painel ao lado mostra, ao vivo, o que acontece por
            baixo dos panos: as ferramentas usadas e a memória da conversa persistida no Atlas.</div></div>
        <div class="copilot-grid">
          <div class="chat-main">
            <div id="chat-log" class="chat-log"></div>
            <div class="chat-suggestions" id="chat-suggestions">
              ${SUGGESTIONS.map((s) => `<button class="chip-suggestion">${S.esc(s)}</button>`).join("")}
            </div>
            <div class="chat-bar">
              <input id="chat-input" placeholder="Pergunte sobre o portfólio de engenharia…" maxlength="2000" />
              <button class="btn-primary" id="chat-send">Enviar</button>
            </div>
          </div>
          <div class="copilot-side">
            <div class="kpi-card" style="--rail:var(--saas)">
              <div class="label sec" style="margin-bottom:6px">Ferramentas do agente</div>
              <div class="muted" style="font-size:11.5px;margin-bottom:8px">Cada ferramenta é uma consulta
                curada no MongoDB (as mesmas das outras telas). As usadas na última resposta acendem.</div>
              ${TOOLS_META.map((t) => `
                <div class="tool-item" data-tool="${t.id}">
                  <div><code>${t.id}</code> <span class="tag ${t.cls}">${t.graph}</span>
                    <span class="tag ok hidden used-badge">usada agora</span></div>
                  <div class="muted" style="font-size:11.5px">${t.desc}</div>
                </div>`).join("")}
            </div>
            <div class="kpi-card" style="--rail:var(--ok)">
              <div class="label sec" style="margin-bottom:6px">Memória no Atlas</div>
              <div class="muted" style="font-size:11.5px;margin-bottom:8px">A cada turno, o checkpointer grava
                a conversa na collection <code>agent_checkpoints</code>. O que está abaixo foi <b>lido de volta
                do banco</b> agora, não da tela.</div>
              <div id="mem-body" class="muted" style="font-size:12px">nada gravado ainda nesta sessão.</div>
            </div>
            <div class="kpi-card" style="--rail:var(--info)">
              <div class="label sec" style="margin-bottom:6px">Aberto a outros agentes</div>
              <div class="muted" style="font-size:11.5px;line-height:1.55">Memória e consultas são documentos
                e pipelines comuns no Atlas: outros agentes e sistemas (em qualquer linguagem) leem esta mesma
                memória e executam as mesmas travessias pelo driver oficial ou pelo MCP Server do MongoDB.
                O Copilot é o primeiro consumidor, não o único.</div>
            </div>
          </div>
        </div>
      </div>`;

    document.getElementById("chat-send").addEventListener("click", send);
    document.getElementById("chat-input").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) send();
    });
    view.querySelectorAll(".chip-suggestion").forEach((b) =>
      b.addEventListener("click", () => {
        document.getElementById("chat-input").value = b.textContent;
        send();
      }));
    paint();
    refreshMemory();
  }

  function toolBlock(toolCalls, idx) {
    if (!toolCalls || !toolCalls.length) return "";
    const rows = toolCalls.map((t) => `
      <div class="tool-call">
        <div><span class="tag info">${S.esc(t.tool)}</span>
          <code>${S.esc(JSON.stringify(t.input))}</code></div>
        ${t.summary ? `<div class="tool-summary">${S.esc(t.summary)}</div>` : ""}
      </div>`).join("");
    return `
      <div class="q-toggle"><a data-tools="${idx}">⟨⟩ ${toolCalls.length} ferramenta(s) usada(s)</a></div>
      <div class="tool-block hidden" id="tools-${idx}">${rows}</div>`;
  }

  function paint() {
    const log = document.getElementById("chat-log");
    if (!log) return;
    log.innerHTML = history.map((m, i) => {
      if (m.role === "user") return `<div class="msg user">${S.esc(m.text)}</div>`;
      if (m.role === "wait") return `<div class="msg assistant wait">pensando e consultando o banco…</div>`;
      // markdown mínimo: **negrito** e `código`; o resto é texto escapado
      const body = S.esc(m.text)
        .replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>")
        .replace(/`([^`\n]+)`/g, "<code>$1</code>")
        .replace(/\n/g, "<br>");
      return `<div class="msg assistant">${body}${toolBlock(m.toolCalls, i)}</div>`;
    }).join("");
    log.querySelectorAll("[data-tools]").forEach((a) =>
      a.addEventListener("click", () => {
        document.getElementById(`tools-${a.dataset.tools}`).classList.toggle("hidden");
      }));
    log.scrollTop = log.scrollHeight;
    const sug = document.getElementById("chat-suggestions");
    if (sug) sug.classList.toggle("hidden", history.length > 0);
  }

  // acende no card lateral as ferramentas usadas na última resposta
  function highlightTools(toolCalls) {
    const used = new Set((toolCalls || []).map((t) => t.tool));
    document.querySelectorAll(".tool-item").forEach((el) => {
      const on = used.has(el.dataset.tool);
      el.classList.toggle("used", on);
      const badge = el.querySelector(".used-badge");
      if (badge) badge.classList.toggle("hidden", !on);
    });
  }

  // relê do Atlas o que o checkpointer gravou para esta sessão
  async function refreshMemory() {
    const box = document.getElementById("mem-body");
    if (!box) return;
    try {
      const m = await S.api(`/copilot/memory?sessionId=${encodeURIComponent(sessionId)}`);
      if (!m.checkpoints) {
        box.innerHTML = "nada gravado ainda nesta sessão.";
        return;
      }
      box.innerHTML = `
        <div style="margin-bottom:6px"><code>db.agent_checkpoints</code> ·
          <b>${m.checkpoints}</b> checkpoints · sessão <code>${S.esc(String(m.sessionId).slice(0, 8))}…</code></div>
        ${m.messages.map((x) => `
          <div class="mem-line"><span class="tag ${x.role === "human" ? "info" : x.role === "tool" ? "warn" : "ok"}">${ROLE_LABEL[x.role] || x.role}</span>
            <span>${S.esc(x.text)}</span></div>`).join("")}`;
    } catch { /* painel nunca derruba o chat */ }
  }

  async function send() {
    if (busy) return;
    const input = document.getElementById("chat-input");
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    busy = true;
    history.push({ role: "user", text });
    history.push({ role: "wait" });
    paint();
    try {
      const r = await S.apiPost("/copilot/chat", { message: text, sessionId });
      history.pop();
      history.push({ role: "assistant", text: r.reply, toolCalls: r.toolCalls || [] });
      highlightTools(r.toolCalls);
    } catch (e) {
      history.pop();
      history.push({ role: "assistant", text: "Não consegui falar com o servidor agora. Ele está no ar?" });
    }
    busy = false;
    paint();
    refreshMemory();
    const inp = document.getElementById("chat-input");
    if (inp) inp.focus();
  }

  S.register("copilot", { render });
})();
