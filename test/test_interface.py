"""Plan section 9, tests 17-22: interface (CLI, TUI, json, exit codes)."""

import hashlib
import http.server
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

INSTALL_PY = Path(__file__).resolve().parent.parent / "install.py"

B = b"<!-- BEGIN behave - installed by install.py; --remove uninstalls -->\n"
MARKER = (b"<!-- installed by install.py (behave); "
          b"--remove deletes this file -->\n")

URL_RULES_BODY = b"# RULES\nrules fetched over localhost http\n"


@pytest.fixture
def url_rules(tmp_path):
    """P5.1: localhost HTTP server serving one rules file, so URL-source
    pin tests never touch the real network."""
    rules = tmp_path / "rules.md"
    rules.write_bytes(URL_RULES_BODY)

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.lstrip("/") == "rules.md":
                body = rules.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/markdown")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # keep access-log noise out of pytest output

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield "http://127.0.0.1:%d/rules.md" % server.server_address[1]
    server.shutdown()
    server.server_close()


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


# Test 23: TUI plain copy over a drifted BEHAVE.md -> y overwrites after
#          confirm, n keeps the file (headless guard is test 22)
def test_23_tui_copy_confirm(run, env_for, fake_home, proj, src_file):
    (proj / "BEHAVE.md").write_bytes(b"CUSTOM LOCAL RULES\n")
    r = run(["--interactive", "--source", str(src_file)],
            env=env_for(fake_home), cwd=proj, input_text="p\nj\ny\ny\n")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "differs from the source" in r.stdout
    assert "overwrite? [y/N]" in r.stdout
    assert (proj / "BEHAVE.md").read_bytes() == src_file.read_bytes()

    (proj / "BEHAVE.md").write_bytes(b"CUSTOM LOCAL RULES\n")
    r2 = run(["--interactive", "--source", str(src_file)],
             env=env_for(fake_home), cwd=proj, input_text="p\nj\ny\nn\n")
    assert r2.returncode == 4, r2.stdout + r2.stderr
    assert "kept" in (r2.stdout + r2.stderr)
    assert (proj / "BEHAVE.md").read_bytes() == b"CUSTOM LOCAL RULES\n"


# Test 24: q at the agent picker quits cleanly (exit 0, nothing written)
def test_24_q_quits_agent_picker(run, env_for, fake_home, src_file):
    r = run(["--interactive", "--agent", "codex", "--source", str(src_file)],
            env=env_for(fake_home), cwd=fake_home, input_text="u\nq\n")
    combined = r.stdout + r.stderr
    assert r.returncode == 0, combined
    assert "q = quit" in r.stdout
    assert "quit; nothing written" in combined
    assert "Traceback" not in combined
    assert not (fake_home / ".codex").exists()


# Test 25: q works at every prompt (scope menu here); quit exits whole TUI
def test_25_q_quits_scope_prompt(run, env_for, fake_home, src_file):
    r = run(["--interactive", "--source", str(src_file)],
            env=env_for(fake_home), cwd=fake_home, input_text="q\n")
    combined = r.stdout + r.stderr
    assert r.returncode == 0, combined
    assert "(q)uit" in r.stdout
    assert "quit; nothing written" in combined
    assert "Traceback" not in combined


# Test 26: every menu/confirm advertises q; q quits from each of them
def test_26_q_advertised_everywhere(run, env_for, fake_home, proj, src_file):
    r = run(["--interactive", "--source", str(src_file)],
            env=env_for(fake_home), cwd=proj, input_text="p\nq\n")
    combined = r.stdout + r.stderr
    assert r.returncode == 0, combined
    assert r.stdout.count("(q)uit") >= 2  # scope menu AND family menu
    assert "quit; nothing written" in combined

    r2 = run(["--interactive", "--source", str(src_file)],
             env=env_for(fake_home), cwd=proj, input_text="p\nc\nq\n")
    combined2 = r2.stdout + r2.stderr
    assert r2.returncode == 0, combined2
    assert "(1) CLAUDE.md" in r2.stdout
    assert "- inline; project-wide" in r2.stdout
    assert "(q) quit" in r2.stdout
    assert "- exit without changing anything" in r2.stdout
    assert "quit; nothing written" in combined2

    r3 = run(["--interactive", "--source", str(src_file)],
             env=env_for(fake_home), cwd=proj, input_text="p\nj\nq\n")
    combined3 = r3.stdout + r3.stderr
    assert r3.returncode == 0, combined3
    assert "Proceed? [y/N] (q quits)" in r3.stdout
    assert "quit; nothing written" in combined3


# P5.1: matching --sha256 pin on a URL source -> install proceeds normally
def test_sha256_matching_pin_installs(run, env_for, fake_home, proj,
                                      url_rules):
    url = url_rules
    pin = hashlib.sha256(URL_RULES_BODY).hexdigest()
    r = run(["--source", url, "--sha256", pin, "--agent", "codex",
             "--scope", "user", "--yes", "--project-dir", str(proj)],
            env=env_for(fake_home))
    combined = r.stdout + r.stderr
    assert r.returncode == 0, combined
    target = fake_home / ".codex" / "AGENTS.md"
    assert target.is_file()
    assert URL_RULES_BODY in target.read_bytes()


# P5.1: wrong --sha256 pin -> exit 3 with expected/got, zero files written
def test_sha256_wrong_pin_aborts_writes_nothing(run, env_for, fake_home,
                                                proj, url_rules):
    url = url_rules
    wrong = "0" * 64
    r = run(["--source", url, "--sha256", wrong, "--agent", "codex",
             "--scope", "user", "--yes", "--project-dir", str(proj)],
            env=env_for(fake_home))
    combined = r.stdout + r.stderr
    assert r.returncode == 3
    assert "sha256 mismatch" in combined
    assert "expected" in combined and "got" in combined
    assert not (fake_home / ".codex").exists()
    assert not (proj / "AGENTS.md").exists()
    assert not (proj / "BEHAVE.md").exists()


# P5.1: --sha256 with a non-URL --source -> loud error (exit 3), no writes
def test_sha256_with_local_source_errors(run, env_for, fake_home, proj,
                                         src_file):
    pin = hashlib.sha256(src_file.read_bytes()).hexdigest()
    r = run(["--source", str(src_file), "--sha256", pin, "--agent", "codex",
             "--scope", "user", "--yes", "--project-dir", str(proj)],
            env=env_for(fake_home))
    combined = r.stdout + r.stderr
    assert r.returncode == 3
    assert "only to URL sources" in combined
    assert not (fake_home / ".codex").exists()
    assert not (proj / "AGENTS.md").exists()


# P5.2: piped stdin -> the arrow-key widget never engages; a scripted
# session through THREE prompts (scope, agent picker, confirm) behaves
# exactly like the numbered menu always did: numbered wording present,
# zero ANSI escapes, typed answers accepted at every prompt
def test_piped_stdin_widget_not_engaged(run, env_for, fake_home, src_file):
    r = run(["--interactive", "--source", str(src_file)],
            env=env_for(fake_home), cwd=fake_home, input_text="u\n1\ny\n")
    combined = r.stdout + r.stderr
    assert r.returncode == 0, combined
    # the three prompts, numbered wording intact
    assert "Where should the rules apply?" in r.stdout
    assert "answer u, p or q" not in r.stdout  # first answer was valid
    assert "Install into which agents? [1-10]" in r.stdout
    assert "Enter = all detected" in r.stdout
    assert "Proceed? [y/N] (q quits)" in r.stdout
    # widget-only strings must not appear on the pipe path
    assert "Space toggles" not in r.stdout
    assert "typed numbers / a / l / q still work" not in r.stdout
    # no ANSI escape sequences anywhere (widget redraw is the only emitter)
    assert "\x1b[" not in r.stdout
    assert "Traceback" not in combined
    # the typed "1" went through the numbered grammar: claude-code drop
    drop = fake_home / ".claude" / "rules" / "behave.md"
    assert drop.is_file()
    assert drop.read_bytes().startswith(MARKER)


# P5.2: the pure key decoders (ANSI escape bytes -> key names;
# msvcrt.getwch char -> key name) exercised via a subprocess that
# imports install.py - process isolation preserved, no test backdoors
def test_widget_key_decoders_pure():
    code = (
        "import install as I\n"
        "assert I._decode_key_bytes(b'\\x1b[A\\x1b[B') == (['up', 'down'], b'')\n"
        "assert I._decode_key_bytes(b'\\x1b[1~x') == (['home', 'x'], b'')\n"
        "assert I._decode_key_bytes(b'\\x1b[4~\\x1b[3~') == "
        "(['end', 'delete'], b'')\n"
        "assert I._decode_key_bytes(b'\\x1b[1;5A') == (['up'], b'')\n"
        "assert I._decode_key_bytes(b'\\x1bx') == (['esc', 'x'], b'')\n"
        "assert I._decode_key_bytes(b'\\x1b') == ([], b'\\x1b')\n"
        "assert I._decode_key_bytes(b'\\x1b[') == ([], b'\\x1b[')\n"
        "assert I._decode_key_bytes(b'\\r\\x7f \\x04') == "
        "(['enter', 'backspace', 'space', 'eof'], b'')\n"
        "assert I._wch_key('\\r') == 'enter'\n"
        "assert I._wch_key(' ') == 'space'\n"
        "assert I._wch_key('\\b') == 'backspace'\n"
        "assert I._wch_key('\\x1b') == 'esc'\n"
        "assert I._wch_key('\\x03') == 'interrupt'\n"
        "assert I._wch_key('q') == 'q'\n"
        "print('decoders-ok')\n"
    )
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
    assert "decoders-ok" in r.stdout


# Phase 3.1 (roo): promoted agent - --list shows roo detected without
# the "(no install support)" note
def test_roo_list_install_support(run, env_for, fake_home):
    (fake_home / ".roo").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [ln for ln in r.stdout.splitlines()
             if ln.strip().split() and ln.strip().split()[0] == "roo"]
    assert lines, r.stdout
    assert "(no install support)" not in lines[0]
