**New in 0.1.1**
- A new look: a dark glass interface in navy and gold, with bundled fonts, so nothing loads from the web.
- A new **How it works** page: the two kinds of Claude (on your computer and in the cloud), the order Claude reads settings files, a checklist for "Claude can't see my key", and how to keep keys safe.
- The green badge now reads "Claude on this computer uses this", with a link to the Cloud sessions tab. Settings on your computer don't reach Claude Code cloud sessions, and the old "Claude uses this" made it look like they did.

Claude Env Manager is a small app that shows every environment variable Claude Code will see, where each one comes from, and lets you add, edit and delete them with values hidden. It runs only on your computer.

**Downloads**
- **Windows:** `ClaudeEnvManager-windows-x64.exe`
- **Mac with Apple silicon (M1 and later):** `ClaudeEnvManager-macos-apple-silicon.zip`
- **Mac with Intel:** `ClaudeEnvManager-macos-intel.zip`
- Each file has a `.sha256` checksum next to it.

**What's in it**
- Variables for each Claude Code scope: Managed (read-only), Project local, Project shared and User, plus your shell.
- Monitor: check whether a variable is visible to Claude, from which scope, and what it overrides, without printing it.
- Cloud sessions: guided setup for Claude Code on the web, a copy-as-.env button, and a one-line check to run inside a session.
- Warnings for secrets in the shared project file, for git-tracked local settings, and for variables Claude ignores in project settings.
- `claude-env check` and `claude-env list` on the command line.

**First open**
The apps aren't code-signed yet, so your computer will warn you the first time.
- Windows: click **More info**, then **Run anyway**.
- Mac: right-click the app, choose **Open**, then **Open** again. Or go to System Settings, Privacy & Security, and click **Open Anyway**.

No telemetry. Nothing leaves your computer. Not affiliated with Anthropic.
