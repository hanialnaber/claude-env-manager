# Claude Env Manager

A small local app to add, check and manage the environment variables that
[Claude Code](https://code.claude.com/docs) uses, and to see exactly which value
Claude will get and where it comes from.

It exists because the question "why can't Claude see my `FAL_KEY`?" usually has
one of five answers: it's in the wrong file, a higher-priority file overrides it,
it's only in a terminal Claude wasn't started from, it's a variable Claude ignores
in project settings, or it's a cloud session, which never reads your computer's
settings at all. This app shows you which one.

- **Variables:** add, edit and delete variables in each Claude settings scope.
  Values are hidden until you reveal one, and hide again after 30 seconds.
- **Monitor:** type a name and see if Claude will see it, from which scope, how
  long it is and what it overrides, without ever printing the value. Plus a
  table of everything Claude will see.
- **Cloud sessions:** step-by-step setup for Claude Code on the web, a "copy as
  .env lines" button for the environment settings box, and a one-line command
  that checks a variable inside a session without printing it.
- **How it works:** a plain-language guide to where Claude reads variables,
  local versus cloud sessions, and a checklist for "Claude can't see my key".

Runs on Windows, macOS and Linux. Not affiliated with Anthropic.

## Download

Get the app from the [latest release](../../releases/latest):

| Computer | File |
|----------|------|
| Windows | `ClaudeEnvManager-windows-x64.exe` |
| Mac with Apple silicon (M1 and later) | `ClaudeEnvManager-macos-apple-silicon.zip` |
| Mac with Intel | `ClaudeEnvManager-macos-intel.zip` |

Open it and the app appears in your browser. Use **Quit** in the top corner to stop it.

The apps aren't code-signed yet, so the first open shows a warning:

- **Windows:** click **More info**, then **Run anyway**. A small window shows the app's link; closing it stops the app.
- **Mac:** unzip, move the app to Applications, right-click it and choose **Open**, then **Open** again. Or open System Settings, Privacy & Security, and click **Open Anyway**.

Each download has a `.sha256` file so you can check it wasn't changed.
The desktop app starts with User settings only; type your project folder at the top to manage a project.

## Run from source

Python 3.9+, no dependencies, no build step.

```bash
git clone <this repo> claude-env-manager
cd claude-env-manager
python3 -m claude_env_manager serve --project /path/to/your/repo
```

Or install the `claude-env` command:

```bash
pipx install .          # or: pip install --user .
claude-env serve        # uses the current folder as the project
```

Your browser opens `http://127.0.0.1:<port>/#token=...`. Use that exact link;
the token is what lets the page talk to the app. Press Ctrl+C in the terminal
to stop.

Options: `--port 8765` for a fixed port, `--no-browser` to just print the link,
`--project none` to manage user settings only.

### Command line (no UI)

```bash
claude-env check FAL_KEY OPENAI_API_KEY   # present/missing, source and length; exit 1 if any missing
claude-env list                           # every scope, values masked
claude-env list --shell                   # also your shell variables, masked
```

Neither command ever prints a value.

## Where Claude Code reads variables

From the official docs ([settings](https://code.claude.com/docs/en/settings),
[environment variables](https://code.claude.com/docs/en/env-vars),
[managed settings](https://code.claude.com/docs/en/managed-settings)), highest
priority first:

| # | Scope | File | Notes |
|---|-------|------|-------|
| 1 | Managed | macOS `/Library/Application Support/ClaudeCode/managed-settings.json`, Linux `/etc/claude-code/managed-settings.json`, Windows `C:\Program Files\ClaudeCode\managed-settings.json`, plus `managed-settings.d/*.json` | Set by an admin. Read-only in this app. |
| 2 | Project local | `<repo>/.claude/settings.local.json` | Just you, this project. Best home for a project's keys. Keep it out of git. |
| 3 | Project shared | `<repo>/.claude/settings.json` | Committed and shared. Never put secrets here. |
| 4 | User | `~/.claude/settings.json` (or `$CLAUDE_CONFIG_DIR/settings.json`) | Every project on your machine. |
| 5 | Shell | the terminal that starts `claude` | A settings file value replaces the same name from the shell. |

Things the docs call out, which the app flags for you:

- Editing `env` in a settings file applies to a running session on save. Removing
  a variable takes effect on the next launch.
- Some variables are ignored in project or local `env` (for example `OTEL_*`,
  `CLAUDE_CODE_ENABLE_TELEMETRY`, `CLAUDE_CONFIG_DIR`), and some are only read
  from the launching shell. A few are set by Claude Code itself.
- Values are copied as written: `~` and `$HOME` are not expanded.
- The docs don't describe Claude Code loading `.env` files, so use a settings file.

### Cloud sessions (Claude Code on the web)

Cloud sessions run on Anthropic's machines, so they never read your User or
Project local settings. A repo's shared `.claude/settings.json` is only read for
a single-repo session outside a Claude project. The reliable place is the cloud
environment's **Environment variables** setting (`.env` format, one `KEY=value`
per line). There's no public API for it, so the app gives you guided steps and a
copy button instead. Start a new session after saving; running sessions keep
old values until their machine is rebuilt. See
[cloud environments](https://code.claude.com/docs/en/cloud-environments).

Anyone who can use a cloud environment can read its variables. For an API key
that only needs to reach one service, the docs suggest a network secret instead.

## Security model

Your keys never leave your machine because of this app.

- **Local only.** The server listens on `127.0.0.1`, never on your network.
- **Per-run token.** Each run makes a random token. It reaches the page in the
  URL fragment, which browsers never send to a server, and the page removes it
  from the address bar. Every API call must send it in a custom header, which
  other websites can't do without a CORS preflight that this app never answers.
- **DNS rebinding blocked.** Requests whose `Host` isn't `127.0.0.1` or
  `localhost` on the app's port are refused.
- **Strict page policy.** No external scripts, fonts or images; a
  Content-Security-Policy allows only the app itself. No frames.
- **No telemetry, no logs.** The app makes no outbound network calls and
  doesn't log requests. API responses are `Cache-Control: no-store`.
- **Values only on request.** The page gets names, a dot mask and the length.
  A value is sent to the page only when you press Reveal or Copy .env lines.
  Error messages never include file contents.
- **Safe writes.** Edits keep every other setting in the file, are written
  atomically, and new files are created readable by you only (`0600`). A file
  with broken JSON is left alone and you're told where the error is.
- **Git warnings.** The app warns when the shared project file is where you're
  putting something that looks like a secret, and when `settings.local.json`
  is tracked by git or not ignored.

Anything already on your computer that can read your home folder can read these
settings files too; that's how Claude Code stores them, and this app doesn't
change it.

## Develop

```bash
python3 -m unittest discover -s tests     # 16 tests, fake values only
python3 demo/build_demo.py                # rebuilds demo/demo.html
```

Releases: in the Actions tab, run **Release** and type a version like
`v0.1.0` (or push that tag). The workflow runs the tests,
builds the apps with PyInstaller on Windows and macOS, attaches them with
checksums to a draft release, and publishes it once every build is in.
Release notes come from `RELEASE_NOTES.md`. macOS runners can queue for
a while; leave the run going.

`demo/demo.html` is the real interface running on made-up example data, in a
single file you can open in any browser. It doesn't touch your computer.

Layout:

```
claude_env_manager/
  core.py      scopes, precedence, safe reads and writes
  server.py    local web server and its security checks
  cli.py       claude-env serve | list | check
  ui/          index.html, style.css, app.js (no frameworks), fonts/
tests/         unit and server tests
demo/          offline demo build
packaging/     desktop app entry point
.github/       test and release workflows
```

## License

MIT. The bundled fonts in `claude_env_manager/ui/fonts/` (Archivo, Figtree,
JetBrains Mono) are under the SIL Open Font License; their license files sit
next to them.
