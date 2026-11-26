"""Core logic: find Claude Code settings files, read and write their "env"
blocks, and work out which value of each variable Claude will actually see.

Nothing in this module prints, logs or sends a value anywhere. Values only
leave this module through the explicit functions that return them
(`reveal_value`, `export_dotenv`), and the callers decide what to do.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SECRET_HINT_RE = re.compile(
    r"(KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD|CREDENTIAL|AUTH|PRIVATE|SESSION|COOKIE)",
    re.I,
)

# Highest precedence first. This mirrors the order in the Claude Code
# settings docs: managed > (command line) > local > project > user.
# Shell / process environment is the base layer that settings "env" sits on.
SCOPE_ORDER = ["managed", "local", "project", "user", "shell"]


class SettingsError(Exception):
    pass


@dataclass
class Scope:
    id: str
    label: str
    path: Optional[Path]
    writable: bool
    description: str
    warning: Optional[str] = None
    exists: bool = False
    error: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)


def claude_config_dir() -> Path:
    """User-level Claude config dir. Honours CLAUDE_CONFIG_DIR like Claude Code."""
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".claude"


def managed_settings_paths() -> List[Path]:
    """Places an administrator can put managed-settings.json (read-only here)."""
    if sys.platform == "darwin":
        return [Path("/Library/Application Support/ClaudeCode/managed-settings.json")]
    if sys.platform.startswith("win"):
        return [Path(r"C:\Program Files\ClaudeCode\managed-settings.json")]
    return [Path("/etc/claude-code/managed-settings.json")]


# Documented as ignored when set in project or local settings "env".
IGNORED_IN_PROJECT_ENV = {
    "CLAUDE_CODE_ENABLE_TELEMETRY",
    "CLAUDE_CONFIG_DIR",
    "CLAUDE_CODE_PROCESS_WRAPPER",
    "CLAUDE_CODE_RESTRICTED",
}
# Documented as only read from the shell that launches Claude, not from "env".
SHELL_ONLY = {
    "CLAUDE_CODE_DISABLE_DANGEROUS_RM_TIMEOUT",
    "CLAUDE_CODE_DISABLE_ULTRAREVIEW_TRUST_CHECK",
    "CLAUDE_CODE_DISABLE_POWERSHELL_CMD_RM_DENY",
}
# Set by Claude Code itself.
RESERVED = {"CLAUDECODE", "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN"}


def name_notes(name: str, scope_id: Optional[str] = None) -> List[str]:
    """Plain-language caveats about a variable name, from the Claude Code docs."""
    notes = []
    if name in RESERVED:
        notes.append("Claude Code sets this itself; your value will be replaced.")
    if name in SHELL_ONLY:
        notes.append("Claude only reads this from the shell that launches it, not from settings files.")
    if scope_id in ("project", "local") and (name in IGNORED_IN_PROJECT_ENV or name.startswith("OTEL_")):
        notes.append("Ignored in project settings. Put it in User scope or your shell instead.")
    return notes


def is_secret_name(name: str) -> bool:
    return bool(SECRET_HINT_RE.search(name))


def mask(value: str) -> str:
    """Never shows any character of the value, only that it exists and its size."""
    if value == "":
        return "(empty)"
    return "•" * min(len(value), 12)


def _read_json(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        # Do not echo file content: it may hold secrets.
        raise SettingsError(
            f"{path} is not valid JSON (line {exc.lineno}, column {exc.colno}). "
            "Fix it by hand before editing here."
        ) from None
    if not isinstance(data, dict):
        raise SettingsError(f"{path} must contain a JSON object at the top level.")
    return data


def _env_block(data: dict, path: Path) -> Dict[str, str]:
    env = data.get("env", {})
    if env is None:
        return {}
    if not isinstance(env, dict):
        raise SettingsError(f'"env" in {path} must be an object of name: value pairs.')
    return {str(k): ("" if v is None else str(v)) for k, v in env.items()}


def _git(project: Path, *args: str) -> Optional[subprocess.CompletedProcess]:
    try:
        return subprocess.run(
            ["git", "-C", str(project), *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def git_status_for(project: Path, rel: str) -> str:
    """'tracked', 'ignored', 'untracked' or 'no-git' for a path inside project."""
    inside = _git(project, "rev-parse", "--is-inside-work-tree")
    if not inside or inside.returncode != 0 or inside.stdout.strip() != "true":
        return "no-git"
    tracked = _git(project, "ls-files", "--error-unmatch", rel)
    if tracked and tracked.returncode == 0:
        return "tracked"
    ignored = _git(project, "check-ignore", "-q", rel)
    if ignored and ignored.returncode == 0:
        return "ignored"
    return "untracked"


def build_scopes(project: Optional[Path], process_env: Optional[Dict[str, str]] = None) -> List[Scope]:
    """Read every scope. Errors are recorded on the scope, never raised."""
    process_env = dict(os.environ if process_env is None else process_env)
    scopes: List[Scope] = []

    managed_path = next((p for p in managed_settings_paths() if p.exists()), managed_settings_paths()[0])
    scopes.append(
        Scope(
            id="managed",
            label="Managed (admin)",
            path=managed_path,
            writable=False,
            description="Set by an administrator. Wins over everything. Read-only here.",
        )
    )

    if project is not None:
        local_path = project / ".claude" / "settings.local.json"
        project_path = project / ".claude" / "settings.json"
        local_git = git_status_for(project, ".claude/settings.local.json")
        project_git = git_status_for(project, ".claude/settings.json")
        local_warn = None
        if local_git == "tracked":
            local_warn = "This file is tracked by git, so these values may be committed. Untrack it and add it to .gitignore."
        elif local_git == "untracked":
            local_warn = "This file is not in .gitignore yet, so a commit could include it. Add .claude/settings.local.json to .gitignore."
        project_warn = "Shared with everyone who clones the repo. Don't put secrets here."
        if project_git == "tracked":
            project_warn = "Tracked by git and shared with everyone who clones the repo. Don't put secrets here."
        scopes.append(
            Scope(
                id="local",
                label="Project, just me (local)",
                path=local_path,
                writable=True,
                description="This project only, on this machine. Best place for a project's secret keys. Cloud sessions never read it.",
                warning=local_warn,
            )
        )
        scopes.append(
            Scope(
                id="project",
                label="Project, shared",
                path=project_path,
                writable=True,
                description="This project, for everyone who uses the repo. Cloud sessions read it only for a single repo outside a Claude project.",
                warning=project_warn,
            )
        )

    scopes.append(
        Scope(
            id="user",
            label="User (all projects)",
            path=claude_config_dir() / "settings.json",
            writable=True,
            description="Every project on this machine. Cloud sessions never read it.",
        )
    )

    for scope in scopes:
        if scope.path is None:
            continue
        scope.exists = scope.path.exists()
        try:
            if scope.exists:
                scope.env = _env_block(_read_json(scope.path), scope.path)
            if scope.id == "managed":
                dropins = scope.path.parent / "managed-settings.d"
                if dropins.is_dir():
                    for f in sorted(dropins.glob("*.json")):
                        scope.env.update(_env_block(_read_json(f), f))
                        scope.exists = True
        except (SettingsError, OSError) as exc:
            scope.error = str(exc)

    scopes.append(
        Scope(
            id="shell",
            label="Shell environment",
            path=None,
            writable=False,
            description=(
                "Variables in the terminal that launched this manager. Claude inherits these "
                "only when it is started from the same kind of shell."
            ),
            exists=True,
            env=process_env,
        )
    )
    return scopes


@dataclass
class Resolution:
    name: str
    present: bool
    source: Optional[str]
    length: int
    shadowed: List[str]
    secret: bool


def resolve(scopes: List[Scope], name: str) -> Resolution:
    by_id = {s.id: s for s in scopes}
    hits = [sid for sid in SCOPE_ORDER if sid in by_id and name in by_id[sid].env]
    if not hits:
        return Resolution(name, False, None, 0, [], is_secret_name(name))
    winner = hits[0]
    value = by_id[winner].env[name]
    return Resolution(name, True, winner, len(value), hits[1:], is_secret_name(name))


def effective(scopes: List[Scope], include_shell: bool = False) -> List[Resolution]:
    """Every variable Claude would see from settings files (plus shell if asked)."""
    names = set()
    for s in scopes:
        if s.id == "shell" and not include_shell:
            continue
        names.update(s.env.keys())
    return [resolve(scopes, n) for n in sorted(names, key=str.lower)]


def validate_name(name: str) -> None:
    if not NAME_RE.match(name or ""):
        raise SettingsError(
            "Use letters, digits and underscores only, not starting with a digit (for example FAL_KEY)."
        )


def _scope_path(scope_id: str, project: Optional[Path]) -> Path:
    if scope_id == "user":
        return claude_config_dir() / "settings.json"
    if scope_id in ("project", "local"):
        if project is None:
            raise SettingsError("Pick a project folder first.")
        name = "settings.json" if scope_id == "project" else "settings.local.json"
        return project / ".claude" / name
    raise SettingsError("That scope can't be changed from here.")


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = None
    if path.exists():
        mode = path.stat().st_mode & 0o777
    fd, tmp = tempfile.mkstemp(prefix=".cem-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        # New files hold secrets: owner read/write only.
        os.chmod(tmp, mode if mode is not None else 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def set_var(scope_id: str, name: str, value: str, project: Optional[Path]) -> Path:
    validate_name(name)
    if not isinstance(value, str):
        raise SettingsError("Value must be text.")
    path = _scope_path(scope_id, project)
    data = _read_json(path)
    env = data.get("env")
    if env is None:
        env = {}
    if not isinstance(env, dict):
        raise SettingsError(f'"env" in {path} must be an object; fix it by hand first.')
    env[name] = value
    data["env"] = env
    _atomic_write_json(path, data)
    return path


def delete_var(scope_id: str, name: str, project: Optional[Path]) -> Path:
    validate_name(name)
    path = _scope_path(scope_id, project)
    data = _read_json(path)
    env = data.get("env")
    if not isinstance(env, dict) or name not in env:
        raise SettingsError(f"{name} isn't set in that scope.")
    del env[name]
    if env:
        data["env"] = env
    else:
        data.pop("env", None)
    _atomic_write_json(path, data)
    return path


def reveal_value(scopes: List[Scope], scope_id: str, name: str) -> str:
    for s in scopes:
        if s.id == scope_id:
            if name not in s.env:
                raise SettingsError(f"{name} isn't set in that scope.")
            return s.env[name]
    raise SettingsError("Unknown scope.")


def dotenv_quote(value: str) -> str:
    if value and re.fullmatch(r"[A-Za-z0-9_./:@+\-,=]*", value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def export_dotenv(scopes: List[Scope], names: List[str]) -> str:
    """KEY=value lines for the cloud environment settings box. Uses the winning value."""
    by_id = {s.id: s for s in scopes}
    lines = []
    for n in names:
        validate_name(n)
        r = resolve(scopes, n)
        if not r.present:
            raise SettingsError(f"{n} isn't set anywhere yet.")
        lines.append(f"{n}={dotenv_quote(by_id[r.source].env[n])}")
    return "\n".join(lines) + "\n"


def check_snippet(name: str) -> str:
    """A one-liner to paste in any session to see if a variable arrived, without printing it."""
    validate_name(name)
    return (
        "python3 -c \"import os;v=os.environ.get('" + name + "');"
        "print('" + name + ": present, ' + str(len(v)) + ' characters' if v is not None else '" + name + ": MISSING')\""
    )
