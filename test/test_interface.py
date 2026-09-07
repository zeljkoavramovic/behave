"""Plan section 9, tests 17-22: interface (CLI, TUI, json, exit codes)."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

INSTALL_PY = Path(__file__).resolve().parent.parent / "install.py"

B = b"<!-- BEGIN behave - installed by install.py; --remove uninstalls -->\n"
MARKER = (b"<!-- installed by install.py (behave); "
          b"--remove deletes this file -->\n")


# Test 17: zero args + EOF stdin -> clean exit 1, no traceback, no hang
def test_17_zero_args_eof_stdin(tmp_path):
    r = subprocess.run(
        [sys.executable, str(INSTALL_PY)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(tmp_path),
        timeout=60,
    )
    assert r.returncode == 1
    combined = r.stdout + r.stderr
    assert "no interactive terminal" in combined
    assert "Traceback" not in combined


# Test 18: --help alone -> exit 0; --help --list -> usage error exit 1
def test_18_help_singleton(run):
    r = run(["--help"])
    assert r.returncode == 0
    assert "usage" in r.stdout.lower()
    r2 = run(["--help", "--list"])
    assert r2.returncode == 1
    assert "cannot combine --help" in (r2.stdout + r2.stderr)


# Test 19: --interactive --agent claude-code with scripted stdin -> TUI
#          completes a rules drop (project branch, variant 4)
def test_19_interactive_tui_rules_drop(run, env_for, fake_home, proj,
                                       src_file):
    r = run(["--interactive", "--agent", "claude-code", "--source",
             str(src_file)],
            env=env_for(fake_home), cwd=proj, input_text="p\n4\ny\n")
    assert r.returncode == 0, r.stdout + r.stderr
    f = proj / ".claude" / "rules" / "behave.md"
    assert f.is_file()
    assert f.read_bytes().startswith(MARKER)
    assert "What will change" in r.stdout
    assert "Proceed?" in r.stdout


# Regression: zero-args TUI user branch (scope u, Enter = all detected,
# confirm y) with project_dir=None must not crash in the stale-block scan
def test_tui_user_branch_stale_scan_no_traceback(run, env_for, fake_home,
                                                 src_file):
    (fake_home / ".claude").mkdir()
    r = run([], env=env_for(fake_home), cwd=fake_home,
            input_text="u\n\ny\n", timeout=120)
    combined = r.stdout + r.stderr
    assert r.returncode == 0, combined
    assert "Traceback" not in combined
    drop = fake_home / ".claude" / "rules" / "behave.md"
    assert drop.is_file()
    assert drop.read_bytes().startswith(MARKER)


# Test 20: --json output shape stable (incl. warning field, no version)
def test_20_json_shape(run, env_for, fake_home, tmp_path, src_file):
    r = run(["--agent", "codex", "--scope", "user", "--yes", "--json",
             "--source", str(src_file)], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    assert set(payload.keys()) == {"block", "targets", "copies"}
    blk = payload["block"]
    assert blk["id"] == "behave"
    assert "version" not in blk
    assert len(blk["sha256"]) == 64
    assert blk["sha256_short"] == blk["sha256"][:7]
    assert blk["sha256"] == hashlib.sha256(src_file.read_bytes()).hexdigest()
    t = payload["targets"][0]
    for key in ("agent", "target", "mode", "status", "warning", "error"):
        assert key in t
    assert t["agent"] == "codex"
    assert t["mode"] == "inline"
    assert t["status"] == "created"
    assert t["error"] is None
    assert payload["copies"] == []

    big = tmp_path / "big.md"
    big.write_bytes(b"# BIG\n" + b"y" * 32000 + b"\n")
    h2 = tmp_path / "h2"
    h2.mkdir()
    r2 = run(["--agent", "codex", "--scope", "user", "--yes", "--json",
              "--source", str(big)], env=env_for(h2))
    assert r2.returncode == 0, r2.stdout + r2.stderr
    payload2 = json.loads(r2.stdout)
    assert payload2["targets"][0]["warning"]


# Test 21: URL fetch failure -> exit 3, no partial writes
def test_21_url_fetch_failure(run, env_for, fake_home, proj):
    r = run(["--source", "http://127.0.0.1:1/x.md", "--agent", "codex",
             "--scope", "user", "--yes", "--project-dir", str(proj)],
            env=env_for(fake_home), timeout=120)
    assert r.returncode == 3
    assert not (fake_home / ".codex").exists()
    assert "127.0.0.1" in (r.stdout + r.stderr)


# Test 22: provenance guard: existing BEHAVE.md with different content +
#          --copy-only -> exit 4, file untouched
def test_22_provenance_guard(run, env_for, proj, src_file, tmp_path):
    (proj / "BEHAVE.md").write_bytes(b"CUSTOM LOCAL RULES\n")
    h = tmp_path / "h1"
    h.mkdir()
    r = run(["--copy-only", "--project-dir", str(proj), "--source",
             str(src_file)], env=env_for(h))
    assert r.returncode == 4
    assert "does not match" in (r.stdout + r.stderr)
    assert (proj / "BEHAVE.md").read_bytes() == b"CUSTOM LOCAL RULES\n"

    (proj / "BEHAVE.md").write_bytes(src_file.read_bytes())
    h2 = tmp_path / "h2"
    h2.mkdir()
    r2 = run(["--copy-only", "--project-dir", str(proj), "--source",
              str(src_file)], env=env_for(h2))
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert (proj / "BEHAVE.md").read_bytes() == src_file.read_bytes()
