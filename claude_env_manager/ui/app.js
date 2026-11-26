"use strict";
// Claude Env Manager UI. Talks only to the local server that served it.
// Values are never stored in the page; a revealed value lives in the DOM
// until you hide it or reload.

(() => {
  // ---- session token (from URL fragment, never sent to any server) ----
  const TOKEN_KEY = "cem-token";
  const m = location.hash.match(/token=([A-Za-z0-9_\-]+)/);
  if (m) {
    try { sessionStorage.setItem(TOKEN_KEY, m[1]); } catch (_) {}
    history.replaceState(null, "", location.pathname);
  }
  let token = m ? m[1] : null;
  if (!token) { try { token = sessionStorage.getItem(TOKEN_KEY); } catch (_) {} }
  const MOCK = window.__CEM_MOCK__ || null; // only set by the offline demo build
  if (MOCK) token = "demo";

  const ORDER = ["managed", "local", "project", "user", "shell"];
  const SHORT = { managed: "Managed", local: "Project local", project: "Project shared", user: "User", shell: "Shell" };
  let state = null;
  let projectPath = null; // null = let server use its default

  const $ = (id) => document.getElementById(id);
  function el(tag, attrs = {}, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") n.className = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? "" : v);
    }
    for (const k of kids.flat()) if (k != null) n.append(k.nodeType ? k : document.createTextNode(String(k)));
    return n;
  }

  async function api(route, body = {}) {
    if (!token) throw new Error("No session token. Open the link printed in your terminal.");
    if (projectPath !== null && !("project" in body)) body.project = projectPath;
    if (MOCK) return MOCK(route, body);
    const res = await fetch("/api/" + route, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CEM-Token": token },
      body: JSON.stringify(body),
      cache: "no-store",
      credentials: "omit",
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "Request failed.");
    return data;
  }

  // In-page confirm (browser confirm() is blocked in some embeds).
  function ask(message, yesLabel = "OK") {
    return new Promise((resolve) => {
      const d = $("askDlg");
      $("askMsg").textContent = message;
      $("askYes").textContent = yesLabel;
      const done = (v) => { d.close(); $("askYes").onclick = $("askNo").onclick = null; resolve(v); };
      $("askYes").onclick = () => done(true);
      $("askNo").onclick = () => done(false);
      d.oncancel = () => done(false);
      d.showModal();
    });
  }

  let bannerTimer;
  function banner(msg, kind = "ok") {
    const b = $("banner");
    b.textContent = msg;
    b.className = "banner " + kind;
    clearTimeout(bannerTimer);
    bannerTimer = setTimeout(() => b.classList.add("hidden"), kind === "ok" ? 3500 : 8000);
  }

  // ---- load ----
  async function load() {
    try {
      state = await api("state");
      $("project").value = state.project;
      $("ver").textContent = "v" + state.version;
      renderScopes();
      renderEffective();
      renderCloudPick();
    } catch (e) {
      banner(e.message, "bad");
    }
  }

  function scopeById(id) { return state.scopes.find((s) => s.id === id); }

  function resolve(name, includeShell) {
    const hits = ORDER.filter((id) => {
      if (id === "shell" && !includeShell) return false;
      const s = scopeById(id);
      return s && s.vars.some((v) => v.name === name);
    });
    if (!hits.length) return null;
    const v = scopeById(hits[0]).vars.find((x) => x.name === name);
    return { source: hits[0], shadowed: hits.slice(1), v };
  }

  // ---- Variables tab ----
  function renderScopes() {
    const wrap = $("scopes");
    wrap.replaceChildren();
    const settingsScopes = state.scopes.filter((s) => s.id !== "shell");
    settingsScopes.forEach((s) => wrap.append(scopeCard(s, ORDER.indexOf(s.id) + 1)));
    const shell = scopeById("shell");
    if (shell) {
      const det = el("details", { class: "shell" }, el("summary", {}, `Shell environment (${shell.vars.length} variables, read-only)`));
      const card = scopeCard(shell, 5, true);
      det.append(card);
      wrap.append(el("div", { class: "scope" }, el("p", { class: "hint" }, shell.description), det));
    }
  }

  function scopeCard(s, rank, bare = false) {
    const head = el("div", { class: "scope-head" },
      el("div", {},
        el("h2", {}, el("span", { class: "rank", title: "Priority: 1 wins" }, rank), s.label,
          s.writable ? null : el("span", { class: "badge ro" }, "read-only"),
          s.exists ? null : el("span", { class: "badge" }, "file not created yet")),
        s.path ? el("div", { class: "path" }, s.path) : null,
        bare ? null : el("p", { class: "hint" }, s.description)),
      s.writable ? el("button", { class: "btn small", onclick: () => openDialog({ scope: s.id }) }, "+ Add here") : null);
    const body = [];
    if (s.warning) body.push(el("p", { class: "warn" }, s.warning));
    if (s.error) body.push(el("p", { class: "err" }, s.error));
    if (!s.vars.length) {
      body.push(el("p", { class: "empty" }, "Nothing set here."));
    } else {
      const tb = el("tbody");
      s.vars.forEach((v) => tb.append(varRow(s, v)));
      body.push(el("table", { class: "grid" },
        el("thead", {}, el("tr", {}, el("th", {}, "Name"), el("th", {}, "Value"), el("th", {}, "Status"), el("th", {}))), tb));
    }
    const card = el("div", { class: bare ? "" : "scope" }, bare ? null : head, ...body);
    return card;
  }

  function varRow(s, v) {
    const r = resolve(v.name, true);
    const wins = r && r.source === s.id;
    const valCell = el("td", { class: "val" }, v.masked, el("span", { class: "muted" }, `  ${v.length} chars`));
    const status = el("td", {},
      wins ? el("span", { class: "badge win" }, "Claude uses this") : el("span", { class: "badge lose", title: "A higher-priority scope sets the same name" }, "overridden by " + SHORT[r.source]),
      v.secret ? el("span", { class: "badge secret" }, "secret") : null);
    const acts = el("td", { class: "acts" });
    const revealBtn = el("button", { class: "btn small ghost" }, "Reveal");
    revealBtn.addEventListener("click", async () => {
      if (valCell.classList.contains("shown")) {
        valCell.classList.remove("shown");
        valCell.replaceChildren(v.masked, el("span", { class: "muted" }, `  ${v.length} chars`));
        revealBtn.textContent = "Reveal";
        return;
      }
      try {
        const { value } = await api("reveal", { scope: s.id, name: v.name });
        valCell.classList.add("shown");
        valCell.replaceChildren(value === "" ? "(empty)" : value);
        revealBtn.textContent = "Hide";
        setTimeout(() => { if (valCell.classList.contains("shown")) revealBtn.click(); }, 30000);
      } catch (e) { banner(e.message, "bad"); }
    });
    acts.append(revealBtn);
    if (s.writable) {
      acts.append(el("button", { class: "btn small", onclick: () => openDialog({ scope: s.id, name: v.name, edit: true }) }, "Edit"));
      acts.append(el("button", { class: "btn small danger", onclick: () => removeVar(s, v.name) }, "Delete"));
    }
    const nameCell = el("td", { class: "name" }, v.name, ...(v.notes || []).map((n) => el("span", { class: "subnote" }, n)));
    return el("tr", {}, nameCell, valCell, status, acts);
  }

  async function removeVar(s, name) {
    if (!(await ask(`Delete ${name} from ${s.label}? (${s.path})`, "Delete"))) return;
    try {
      await api("delete", { scope: s.id, name });
      banner(`Deleted ${name} from ${s.label}. Running Claude sessions drop it on their next launch.`);
      await load();
    } catch (e) { banner(e.message, "bad"); }
  }

  // ---- dialog ----
  let dlgCtx = null;
  function openDialog({ scope, name = "", edit = false }) {
    dlgCtx = { edit, originalName: name, originalScope: scope };
    $("dlgTitle").textContent = edit ? `Edit ${name}` : "Add variable";
    $("fName").value = name;
    $("fName").readOnly = edit;
    $("fValue").value = "";
    $("fValue").type = "password";
    $("fShow").textContent = "Show";
    $("fValue").placeholder = edit ? "Type a new value (current value isn't shown)" : "Value";
    const sel = $("fScope");
    sel.replaceChildren();
    state.scopes.filter((s) => s.writable).forEach((s) => sel.append(el("option", { value: s.id }, s.label)));
    sel.value = scope || (scopeById("local") ? "local" : "user");
    sel.disabled = edit;
    updateDialogHelp();
    $("dlg").showModal();
    (edit ? $("fValue") : $("fName")).focus();
  }

  function updateDialogHelp() {
    const s = scopeById($("fScope").value);
    $("fScopeHelp").textContent = s ? `${s.description}  File: ${s.path}` : "";
    const name = $("fName").value.trim();
    const secretish = /(KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH|PRIVATE)/i.test(name);
    const w = $("fWarn");
    if (s && s.id === "project" && secretish) {
      w.textContent = "This looks like a secret, and the shared project file is usually committed to git. Use Project local or User instead.";
      w.classList.remove("hidden");
    } else if (s && s.warning && s.id === "local") {
      w.textContent = s.warning;
      w.classList.remove("hidden");
    } else {
      w.classList.add("hidden");
    }
  }

  $("fScope").addEventListener("change", updateDialogHelp);
  $("fName").addEventListener("input", updateDialogHelp);
  $("fShow").addEventListener("click", () => {
    const f = $("fValue");
    f.type = f.type === "password" ? "text" : "password";
    $("fShow").textContent = f.type === "password" ? "Show" : "Hide";
  });
  $("dlgCancel").addEventListener("click", () => { $("fValue").value = ""; $("dlg").close(); });
  $("dlg").addEventListener("close", () => { $("fValue").value = ""; });
  $("dlgForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const name = $("fName").value.trim();
    const scope = $("fScope").value;
    const value = $("fValue").value;
    const exists = scopeById(scope).vars.some((v) => v.name === name);
    if (dlgCtx.edit && value === "" && !(await ask(`Set ${name} to an empty value?`, "Set empty"))) return;
    if (!dlgCtx.edit && exists && !(await ask(`${name} is already set in this scope. Replace it?`, "Replace"))) return;
    try {
      const res = await api("set", { scope, name, value });
      $("fValue").value = "";
      $("dlg").close();
      const notes = (res.notes || []).join(" ");
      banner(`Saved ${name}. Claude picks it up on save. ${notes}`, notes ? "bad" : "ok");
      await load();
    } catch (e) { banner(e.message, "bad"); }
  });

  $("addBtn").addEventListener("click", () => openDialog({}));

  // ---- Monitor tab ----
  function renderEffective() {
    const inc = $("incShell").checked;
    const q = $("filter").value.trim().toLowerCase();
    const names = new Set();
    state.scopes.forEach((s) => { if (s.id !== "shell" || inc) s.vars.forEach((v) => names.add(v.name)); });
    const tb = $("effective");
    tb.replaceChildren();
    const sorted = [...names].filter((n) => n.toLowerCase().includes(q)).sort((a, b) => a.localeCompare(b));
    if (!sorted.length) {
      tb.append(el("tr", {}, el("td", { colspan: 4, class: "empty" }, q ? "No matches." : "No variables in any settings file yet.")));
      return;
    }
    sorted.forEach((n) => {
      const r = resolve(n, inc);
      tb.append(el("tr", {},
        el("td", { class: "name" }, n),
        el("td", { class: "val" }, r.v.masked, el("span", { class: "muted" }, `  ${r.v.length} chars`)),
        el("td", {}, el("span", { class: "badge win" }, SHORT[r.source])),
        el("td", {}, r.shadowed.length ? r.shadowed.map((x) => el("span", { class: "badge lose" }, SHORT[x])) : el("span", { class: "muted" }, "none"))));
    });
  }
  $("incShell").addEventListener("change", renderEffective);
  $("filter").addEventListener("input", renderEffective);

  $("checkForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const name = $("checkName").value.trim();
    const out = $("checkResult");
    out.replaceChildren();
    if (!name) return;
    try {
      const r = await api("check", { name });
      const items = [];
      if (r.present) {
        items.push(el("li", {}, `${r.length} characters long (value not shown).`));
        if (r.source === "shell") items.push(el("li", {}, "Only in your shell. Claude sees it only when started from a shell that has it. Add it to a settings file to make it stick."));
        if (r.shadowed.length) items.push(el("li", {}, "Also set in " + r.shadowed.map((x) => SHORT[x]).join(", ") + ", but those values are ignored."));
      } else {
        items.push(el("li", {}, "Not in any Claude settings file on this machine, and not in this shell."));
        items.push(el("li", {}, "Add it in the Variables tab. For cloud sessions, see the Cloud sessions tab."));
      }
      (r.notes || []).forEach((n) => items.push(el("li", {}, n)));
      items.push(el("li", {}, "Cloud sessions don't read this machine's settings. Check those with the command in the Cloud sessions tab."));
      out.append(el("div", { class: "result " + (r.present ? "ok" : "bad") },
        el("h3", {}, r.present ? `${r.name} is visible to Claude, from ${SHORT[r.source]}` : `${r.name} is missing`),
        el("ul", {}, items)));
    } catch (e) { banner(e.message, "bad"); }
  });

  // ---- Cloud tab ----
  function renderCloudPick() {
    const wrap = $("cloudPick");
    wrap.replaceChildren();
    const names = new Set();
    state.scopes.forEach((s) => { if (s.id !== "shell") s.vars.forEach((v) => names.add(v.name)); });
    if (!names.size) {
      wrap.append(el("p", { class: "empty" }, "Add variables first, or type lines straight into the cloud environment settings."));
      return;
    }
    [...names].sort().forEach((n) => wrap.append(el("label", {}, el("input", { type: "checkbox", value: n }), n)));
    updatePreview();
  }

  function picked() { return [...$("cloudPick").querySelectorAll("input:checked")].map((i) => i.value); }
  function updatePreview() {
    const p = picked();
    $("envPreview").textContent = p.length ? p.map((n) => `${n}=${resolve(n, false).v.masked}`).join("\n") : "Nothing picked yet.";
  }
  $("cloudPick").addEventListener("change", updatePreview);

  $("copyEnv").addEventListener("click", async () => {
    const names = picked();
    if (!names.length) return banner("Pick at least one variable.", "bad");
    try {
      const { dotenv } = await api("export", { names });
      await navigator.clipboard.writeText(dotenv);
      $("copyMsg").textContent = `Copied ${names.length} line(s). Paste into the environment's Environment variables box.`;
      setTimeout(() => { $("copyMsg").textContent = ""; }, 8000);
    } catch (e) { banner(e.message || "Couldn't copy. Allow clipboard access and try again.", "bad"); }
  });

  async function updateSnippet() {
    const name = $("snipName").value.trim();
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) { $("snippet").textContent = "Enter a valid name, like FAL_KEY."; return; }
    try { $("snippet").textContent = (await api("snippet", { name })).snippet; } catch (e) { $("snippet").textContent = e.message; }
  }
  $("snipName").addEventListener("input", updateSnippet);
  $("copySnip").addEventListener("click", async () => {
    try { await navigator.clipboard.writeText($("snippet").textContent); banner("Command copied."); }
    catch (_) { banner("Couldn't copy. Select the command and copy it.", "bad"); }
  });

  // ---- tabs & project ----
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === t));
    ["vars", "monitor", "cloud"].forEach((id) => $("tab-" + id).classList.toggle("hidden", id !== t.dataset.tab));
  }));
  $("loadProject").addEventListener("click", () => { projectPath = $("project").value.trim(); load(); });
  $("project").addEventListener("keydown", (e) => { if (e.key === "Enter") $("loadProject").click(); });
  $("refresh").addEventListener("click", load);
  $("quitBtn").addEventListener("click", async () => {
    if (!(await ask("Quit Claude Env Manager? You can open it again any time.", "Quit"))) return;
    try { await api("quit"); } catch (_) {}
    document.body.replaceChildren(el("main", {}, el("h1", {}, "Claude Env Manager has stopped."), el("p", { class: "hint" }, "You can close this tab.")));
  });

  load();
  updateSnippet();
})();
