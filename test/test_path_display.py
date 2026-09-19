"""Path-display policy guards.

Prose output (menus, help, warnings) renders home-relative paths via
home_disp(): native separators per OS, "~" on POSIX, "%USERPROFILE%"
on Windows - never a "~" on Windows and never mixed separators in one
rendered path. Copy-paste-exact output (errors, JSON, previews,
resolved paths) intentionally stays absolute str(Path) and is outside
this policy.
"""

import ast
import os
import subprocess
import sys
from pathlib import Path

INSTALL_PY = Path(__file__).resolve().parent.parent / "install.py"


def _docstring_ids(tree):
    """ids of Constant nodes that are docstrings (excluded from the
    scan: maintainer prose may keep POSIX-style paths)."""
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)):
                ids.add(id(first.value))
    return ids


def test_no_tilde_path_literals_in_strings():
    """A "~/" or "~<sep>" inside any string constant is a policy
    regression: prose paths must be built by home_disp()."""
    tree = ast.parse(INSTALL_PY.read_text(encoding="utf-8"))
    skip = _docstring_ids(tree)
    bad = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in skip):
            v = node.value
            if "~/" in v or "~\\" in v:
                bad.append("line %d: %r" % (node.lineno, v[:60]))
    assert not bad, ("tilde path literals (use home_disp()):\n"
                     + "\n".join(bad))


def _home_disp_render():
    code = ("import install as I; "
            "print(I.home_disp('.claude', 'CLAUDE.md'))")
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(INSTALL_PY.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout.strip()


def test_home_disp_native_and_unmixed():
    got = _home_disp_render()
    if os.name == "nt":
        assert got == "%USERPROFILE%\\.claude\\CLAUDE.md"
        assert "~" not in got
        assert "/" not in got
    else:
        assert got == "~/.claude/CLAUDE.md"


def test_mode_help_renders_home_shorthand():
    r = subprocess.run(
        [sys.executable, str(INSTALL_PY), "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    want = ("~/.claude/CLAUDE.md" if os.name != "nt"
            else "%USERPROFILE%\\.claude\\CLAUDE.md")
    assert want in r.stdout
