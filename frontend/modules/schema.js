/* Módulo Esquema Flexível — adicionar atributo/relação a um componente e ver o
   documento mudar SEM migração (query-herói C). Tema claro. */
(function () {
  const S = window.Spectra;
  let current = null;

  async function render(view) {
    view.innerHTML = `
      <div class="view-head"><h2>Esquema Flexível</h2>
        <div class="desc">Cada componente pode ter atributos diferentes, porque o esquema pertence ao documento e não a uma tabela rígida. Adicione um atributo ou uma relação e veja o documento mudar na hora, sem <code>ALTER TABLE</code>, sem migração e sem deploy.</div></div>
      ${S.callout(
        "Adicionar um atributo novo significava criar linhas no padrão EAV (tabelas genéricas de atributo) e ainda um projeto de migração de banco.",
        "O atributo é apenas mais um campo no documento. Cada componente pode ter os seus, sem alterar nenhuma tabela e sem downtime."
      )}
      <div class="filters">
        <label>Componente
          <input id="sc-search" list="sc-list" placeholder="Buscar componente…" style="min-width:280px" />
          <datalist id="sc-list"></datalist>
        </label>
      </div>
      <div id="sc-body" style="padding:0 28px 28px"><div class="muted">Selecione um componente para começar (ex.: Motor de Crédito).</div></div>`;

    try {
      const list = await S.api("/graph/components");
      document.getElementById("sc-list").innerHTML = list
        .map((c) => `<option data-id="${c.id}" value="${S.esc(c.name)}">${c.type}</option>`).join("");
    } catch { /* */ }

    const search = document.getElementById("sc-search");
    if (!search) return; // usuário já navegou para outro módulo durante o carregamento
    search.addEventListener("change", (e) => {
      const opt = [...document.querySelectorAll("#sc-list option")].find((o) => o.value === e.target.value);
      if (opt) {
        load(opt.dataset.id);
        // limpa o campo: o datalist filtra pelo texto digitado, então sem limpar
        // o próximo clique na setinha só mostraria a opção já selecionada
        e.target.value = "";
      }
    });
    search.addEventListener("focus", (e) => e.target.select());
    // atalho: já carrega o Motor de Crédito
    load("comp-motor-de-credito");
  }

  async function load(id) {
    current = id;
    const body = document.getElementById("sc-body");
    if (!body) return; // usuário já navegou para outro módulo
    body.innerHTML = `<div class="spinner">carregando documento…</div>`;
    try {
      const c = await S.api(`/schema/components/${id}`);
      body.innerHTML = `
        <div style="display:grid;grid-template-columns:1fr 340px;gap:20px">
          <div>
            <h3 style="margin:0 0 8px">${S.esc(c.name)} <span class="tag info">${S.esc(c.type)}</span></h3>
            <div class="muted" style="font-size:12px;margin-bottom:8px">Documento cru (observe que <code>attributes</code> varia de um componente para outro):</div>
            <pre id="sc-json" style="background:#0B1020;color:#b9c4dd;padding:14px;border-radius:8px;overflow:auto;max-height:520px">${S.highlightDoc(c, ["attributes", "relations"])}</pre>
          </div>
          <div>
            <div class="kpi-card" style="--rail:var(--saas)">
              <h3>Adicionar atributo</h3>
              <label class="muted" style="font-size:12px">chave</label>
              <input id="attr-key" placeholder="pciScope" style="width:100%;margin:4px 0 10px;padding:8px;border:1px solid var(--border);border-radius:8px" />
              <label class="muted" style="font-size:12px">valor</label>
              <input id="attr-val" placeholder="true" style="width:100%;margin:4px 0 12px;padding:8px;border:1px solid var(--border);border-radius:8px" />
              <button class="btn-primary" id="attr-add" style="width:100%">$set attributes.&lt;chave&gt;</button>
            </div>
            <div class="kpi-card" style="--rail:var(--primary);margin-top:14px">
              <h3>Adicionar relação</h3>
              <label class="muted" style="font-size:12px">targetId (outro componente)</label>
              <input id="rel-target" list="sc-list" placeholder="comp-…" style="width:100%;margin:4px 0 12px;padding:8px;border:1px solid var(--border);border-radius:8px" />
              <button class="btn-primary" id="rel-add" style="width:100%">$addToSet relations</button>
            </div>
            <div id="sc-msg" class="muted" style="font-size:13px;margin-top:12px"></div>
          </div>
        </div>`;
      document.getElementById("attr-add").addEventListener("click", addAttr);
      document.getElementById("rel-add").addEventListener("click", addRel);
    } catch (e) {
      body.innerHTML = `<div class="spinner">componente não encontrado.</div>`;
    }
  }

  function parseVal(raw) {
    if (raw === "true") return true;
    if (raw === "false") return false;
    if (raw !== "" && !isNaN(Number(raw))) return Number(raw);
    return raw;
  }

  async function addAttr() {
    const key = document.getElementById("attr-key").value.trim();
    const val = parseVal(document.getElementById("attr-val").value.trim());
    const msg = document.getElementById("sc-msg");
    if (!key) { msg.textContent = "informe a chave."; return; }
    try {
      const updated = await S.apiPost(`/schema/components/${current}/attributes`, { key, value: val });
      flash(updated, `✔ atributo "${key}" adicionado, sem migração.`);
    } catch (e) { msg.textContent = "erro: " + e.message; }
  }

  async function addRel() {
    const targetName = document.getElementById("rel-target").value.trim();
    const opt = [...document.querySelectorAll("#sc-list option")].find((o) => o.value === targetName);
    const targetId = opt ? opt.dataset.id : targetName;
    const msg = document.getElementById("sc-msg");
    try {
      const updated = await S.apiPost(`/schema/components/${current}/relations`, { targetId });
      flash(updated, `✔ relação → ${targetId} adicionada.`);
    } catch (e) { msg.textContent = "erro: " + e.message; }
  }

  function flash(updated, text) {
    document.getElementById("sc-json").innerHTML = S.highlightDoc(updated, ["attributes", "relations"]);
    const msg = document.getElementById("sc-msg");
    msg.style.color = "var(--ok)";
    msg.textContent = text + " O grafo e a análise de impacto continuam funcionando.";
  }

  S.register("schema", { render });
})();
