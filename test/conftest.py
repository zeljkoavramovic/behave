"""Shared fixtures for the install.py test suite (plan section 9).

Every test isolates via tmp dirs and a fake HOME/USERPROFILE; the suite
never touches the real user home and never hits the network (the bundled
BEHAVE.md next to install.py is found via install.py's own directory, or
tests pass --source explicitly).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
INSTALL_PY = REPO / "install.py"

OVERRIDE_VARS = [
    "CLAUDE_CONFIG_DIR", "CODEX_HOME", "VIBE_HOME", "HERMES_HOME",
    "AUTOHAND_HOME", "GROK_HOME", "XDG_CONFIG_HOME",
    "FLATPAK_XDG_CONFIG_HOME",
]


def base_env(fake_home, **extra):
    env = dict(os.environ)
    for name in OVERRIDE_VARS:
        env.pop(name, None)
    home = str(Path(fake_home))
    env["HOME"] = home
    env["USERPROFILE"] = home
    env["APPDATA"] = str(Path(home) / "AppData" / "Roaming")
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    for key, value in extra.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = str(value)
    return env


def run_installer(args, env=None, cwd=None, input_text=None, timeout=120):
    return subprocess.run(
        [sys.executable, str(INSTALL_PY)] + [str(a) for a in args],
        env=env,
        cwd=str(cwd) if cwd else None,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


@pytest.fixture
def fake_home(tmp_path):
    home = tmp_path / "fakehome"
    home.mkdir()
    return home


@pytest.fixture
def proj(tmp_path):
    p = tmp_path / "proj"
    p.mkdir()
    return p


@pytest.fixture
def run():
    return run_installer


@pytest.fixture
def env_for():
    return base_env


@pytest.fixture
def src_file(tmp_path):
    src = tmp_path / "rules.md"
    src.write_bytes(b"# RULES\nrules body line\n")
    return src


@pytest.fixture
def git_available():
    import shutil
    return shutil.which("git") is not None
