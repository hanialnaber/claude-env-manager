"use strict";
// Offline demo backend: an in-memory copy of the real server's API with
// made-up example data. Used only by demo.html; the real app never loads it.
(() => {
  const ORDER = ["managed", "local", "project", "user", "shell"];
  const SECRET = /(KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD|CREDENTIAL|AUTH|PRIVATE|SESSION|COOKIE)/i;
  const P = "/Users/demo/projects/reels-studio";
  const scopes = [
    { id: "managed", label: "Managed (admin)", path: "/Library/Application Support/ClaudeCode/managed-settings.json", writable: false, exists: false,
      description: "Set by an administrator. Wins over everything. Read-only here.", env: {} },
    { id: "local", label: "Project, just me (local)", path: P + "/.claude/settings.local.json", writable: true, exists: true,
      description: "This project only, on this machine. Best place for a project's secret keys. Cloud sessions never read it.",
      env: { FAL_KEY: "example-fal-0000-1111-2222-demo", REPLICATE_API_TOKEN: "r8_exampleexampleexample" } },
    { id: "project", label: "Project, shared", path: P + "/.claude/settings.json", writable: true, exists: true,
      warning: "Tracked by git and shared with everyone who clones the repo. Don't put secrets here.",
      description: "This project, for everyone who uses the repo. Cloud sessions read it only for a single repo outside a Claude project.",
      env: { RENDER_FPS: "30", OUTPUT_DIR: "./renders" } },
    { id: "user", label: "User (all projects)", path: "/Users/demo/.claude/settings.json", writable: true, exists: true,
      description: "Every project on this machine. Cloud sessions never read it.",
      env: { FAL_KEY: "example-old-key", BASH_DEFAULT_TIMEOUT_MS: "300000" } },
    { id: "shell", label: "Shell environment", path: null, writable: false, exists: true,
      description: "Variables in the terminal that launched this manager. Claude inherits these only when it is started from the same kind of shell.",
      env: { HOME: "/Users/demo", LANG: "en_US.UTF-8", PATH: "/usr/local/bin:/usr/bin:/bin", SHELL: "/bin/zsh", OPENAI_API_KEY: "sk-example-demo-only" } },
  ];
  const by = (id) => scopes.find((s) => s.id === id);
  const mask = (v) => (v === "" ? "(empty)" : "•".repeat(Math.min(v.length, 12)));
  const fail = (m) => { throw new Error(m); };
  const validName = (n) => /^[A-Za-z_][A-Za-z0-9_]*$/.test(n) || fail("Use letters, digits and underscores only, not starting with a digit (for example FAL_KEY).");
  function notes(name, sid) {
    const out = [];
    if (["CLAUDECODE", "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN"].includes(name)) out.push("Claude Code sets this itself; your value will be replaced.");
    if ((sid === "project" || sid === "local") && (name.startsWith("OTEL_") || ["CLAUDE_CODE_ENABLE_TELEMETRY", "CLAUDE_CONFIG_DIR", "CLAUDE_CODE_PROCESS_WRAPPER", "CLAUDE_CODE_RESTRICTED"].includes(name)))
      out.push("Ignored in project settings. Put it in User scope or your shell instead.");
    return out;
  }
  function resolve(name) {
    const hits = ORDER.filter((id) => name in by(id).env);
    if (!hits.length) return { name, present: false, source: null, length: 0, shadowed: [], secret: SECRET.test(name) };
    return { name, present: true, source: hits[0], length: by(hits[0]).env[name].length, shadowed: hits.slice(1), secret: SECRET.test(name) };
  }
  const snippet = (n) => `python3 -c "import os;v=os.environ.get('${n}');print('${n}: present, ' + str(len(v)) + ' characters' if v is not None else '${n}: MISSING')"`;
  const q = (v) => (/^[A-Za-z0-9_./:@+\-,=]+$/.test(v) ? v : '"' + v.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, "\\n") + '"');

  window.__CEM_MOCK__ = async (route, body) => {
    await new Promise((r) => setTimeout(r, 60));
    switch (route) {
      case "state":
        return {
          version: "0.1.1 (demo, example data)", project: P,
          scopes: scopes.map((s) => ({ ...s, env: undefined, vars: Object.keys(s.env).sort((a, b) => a.localeCompare(b)).map((n) => ({
            name: n, masked: mask(s.env[n]), length: s.env[n].length, secret: SECRET.test(n), notes: s.id === "shell" ? [] : notes(n, s.id) })) })),
          effective: [],
        };
      case "set": {
        validName(body.name);
        const s = by(body.scope); if (!s || !s.writable) fail("That scope can't be changed from here.");
        s.env[body.name] = String(body.value ?? ""); s.exists = true;
        return { ok: true, path: s.path, notes: notes(body.name, s.id) };
      }
      case "delete": {
        const s = by(body.scope); if (!s || !(body.name in s.env)) fail(`${body.name} isn't set in that scope.`);
        delete s.env[body.name]; return { ok: true, path: s.path };
      }
      case "reveal": {
        const s = by(body.scope); if (!s || !(body.name in s.env)) fail(`${body.name} isn't set in that scope.`);
        return { value: s.env[body.name] };
      }
      case "check": validName(body.name); { const r = resolve(body.name); return { ...r, notes: notes(body.name, r.source), snippet: snippet(body.name) }; }
      case "export":
        return { dotenv: body.names.map((n) => { const r = resolve(n); if (!r.present) fail(`${n} isn't set anywhere yet.`); return `${n}=${q(by(r.source).env[n])}`; }).join("\n") + "\n" };
      case "quit": return { ok: true };
      case "snippet": validName(body.name); return { snippet: snippet(body.name) };
      default: fail("Unknown action.");
    }
  };
})();
