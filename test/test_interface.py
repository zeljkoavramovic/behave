"""Plan section 9, tests 17-22: interface (CLI, TUI, json, exit codes)."""

import hashlib
import http.server
import json
import os
import re
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
    # zero detections in this fixture: the menu falls back to the full
    # supported list; both count strings must agree with the menu range
    # (derived from len(TIER1_ORDER) - a promotion can never ship a
    # stale literal, and neither can this test)
    m = re.search(r"Install into which agents\? \[1-(\d+)\]", r.stdout)
    assert m, "numbered agent prompt not found"
    full = int(m.group(1))
    assert ("no supported agents detected; showing all %d" % full) \
        in r.stdout
    assert ("a = all %d" % full) in r.stdout
    assert "Enter = checked/detected" in r.stdout
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


# Detected-first menu: the FIRST numbered prompt covers only detected
# agents ([1-2] here); typing l expands the SAME menu to the full
# supported list and the re-prompt reads [1-N] (N = len(TIER1_ORDER),
# derived - never a stale literal) with non-detected rows showing "-"
def test_agent_menu_detected_first_l_expands(run, env_for, fake_home,
                                             src_file):
    (fake_home / ".claude").mkdir()
    (fake_home / ".codex").mkdir()
    r = run(["--interactive", "--source", str(src_file)],
            env=env_for(fake_home), cwd=fake_home, input_text="u\nl\nq\n")
    combined = r.stdout + r.stderr
    assert r.returncode == 0, combined
    assert "Install into which agents? [1-2]" in r.stdout
    assert "no supported agents detected" not in r.stdout
    ranges = re.findall(r"Install into which agents\? \[1-(\d+)\]",
                        r.stdout)
    full = int(ranges[-1])
    assert full > 2
    assert ("a = all %d" % full) in r.stdout
    # full-list positions after expansion: gemini-cli is #6, undetected
    assert "6  Gemini CLI" in r.stdout
    assert "quit; nothing written" in combined
    assert "Traceback" not in combined


# l-expansion then a full-list number installs a NON-detected agent
# (numbers after l refer to the on-screen full-list rows; the expanded
# range and the "a = all N" hint must agree, N derived not pinned)
def test_agent_menu_l_then_number_installs_nondetected(run, env_for,
                                                       fake_home, src_file):
    (fake_home / ".claude").mkdir()
    r = run(["--interactive", "--source", str(src_file)],
            env=env_for(fake_home), cwd=fake_home, input_text="u\nl\n6\ny\n")
    combined = r.stdout + r.stderr
    assert r.returncode == 0, combined
    assert "Install into which agents? [1-1]" in r.stdout
    ranges = re.findall(r"Install into which agents\? \[1-(\d+)\]",
                        r.stdout)
    full = int(ranges[-1])
    assert full > 1
    assert ("a = all %d" % full) in r.stdout
    g = fake_home / ".gemini" / "GEMINI.md"
    assert g.is_file()
    assert g.read_bytes().startswith(B)
    assert "Traceback" not in combined


# zero detections: Enter (= default) reports nothing pre-checked and
# re-asks; 'a' then selects every supported agent (confirm declined to
# stay read-only); the count strings must agree with the menu range
def test_agent_menu_zero_detections_enter_then_all(run, env_for,
                                                   fake_home, src_file):
    r = run(["--interactive", "--source", str(src_file)],
            env=env_for(fake_home), cwd=fake_home, input_text="u\n\na\nn\n")
    combined = r.stdout + r.stderr
    assert r.returncode == 0, combined
    m = re.search(r"Install into which agents\? \[1-(\d+)\]", r.stdout)
    assert m, "numbered agent prompt not found"
    full = int(m.group(1))
    assert ("no supported agents detected; showing all %d" % full) \
        in r.stdout
    assert ("a = all %d" % full) in r.stdout
    assert "nothing is pre-checked" in r.stdout
    assert "What will change" in r.stdout
    assert "aborted; nothing written" in combined
    assert "Traceback" not in combined


# row_keys mapping (one answer grammar, two input surfaces): Enter on a
# row must behave exactly like typing that row's key, for each of the
# three single-choice prompts; plus the agents-widget l-expansion
# protocol (rows/checked/visible mutated in place, Esc keeps the
# expanded view).  The real widget needs a cbreak terminal, so this
# drives the widget machinery through a fake reader in a subprocess -
# the same process-isolation pattern as test_widget_key_decoders_pure.
def test_widget_row_keys_map_rows_to_grammar():
    code = (
        "import install as I\n"
        "class R:\n"
        "    def __init__(self, keys):\n"
        "        self.keys = list(keys)\n"
        "    def read_key(self):\n"
        "        return self.keys.pop(0)\n"
        "def scope_grammar(buf):\n"
        "    a = buf.strip().lower()\n"
        "    if a in ('q', 'quit'):\n"
        "        raise I.QuitTUI()\n"
        "    if a in ('u', 'user'):\n"
        "        return 'user'\n"
        "    if a in ('p', 'proj', 'project'):\n"
        "        return 'project'\n"
        "    return None\n"
        "scope_rows = ['(u)ser', '(p)roject', '(q)uit']\n"
        "scope_keys = ['u', 'p', 'q']\n"
        "assert I._widget_choice(R(['enter']), ['t'], scope_rows, '',\n"
        "                        'bad', scope_grammar, scope_keys) == 'user'\n"
        "try:\n"
        "    I._widget_choice(R(['down', 'down', 'enter']), ['t'],\n"
        "                     scope_rows, '', 'bad', scope_grammar,\n"
        "                     scope_keys)\n"
        "    raise SystemExit('scope q-row did not quit')\n"
        "except I.QuitTUI:\n"
        "    pass\n"
        "assert I._widget_choice(R(['x', 'enter', 'p', 'enter']), ['t'],\n"
        "                        scope_rows, '', 'bad', scope_grammar,\n"
        "                        scope_keys) == 'project'\n"
        "fam_map = {'a': 'a', 'c': 'c', 'g': 'g', 'j': 'j'}\n"
        "def fam_grammar(buf):\n"
        "    a = buf.strip().lower()\n"
        "    if a == 'q':\n"
        "        raise I.QuitTUI()\n"
        "    return fam_map.get(a)\n"
        "fam_rows = ['a', 'c', 'g', 'j', 'q']\n"
        "fam_keys = ['a', 'c', 'g', 'j', 'q']\n"
        "assert I._widget_choice(R(['down', 'enter']), ['t'], fam_rows,\n"
        "                        '', 'bad', fam_grammar, fam_keys) == 'c'\n"
        "try:\n"
        "    I._widget_choice(R(['down', 'down', 'down', 'down',\n"
        "                        'enter']), ['t'], fam_rows, '', 'bad',\n"
        "                        fam_grammar, fam_keys)\n"
        "    raise SystemExit('family q-row did not quit')\n"
        "except I.QuitTUI:\n"
        "    pass\n"
        "var_map = {'1': 'root', '2': 'dot-claude', '3': 'local',\n"
        "           '4': 'rules'}\n"
        "def var_grammar(buf):\n"
        "    s = buf.strip()\n"
        "    if s.lower() in ('q', 'quit'):\n"
        "        raise I.QuitTUI()\n"
        "    return var_map.get(s.strip('()'))\n"
        "var_rows = ['1', '2', '3', '4', 'q']\n"
        "var_keys = ['1', '2', '3', '4', 'q']\n"
        "assert I._widget_choice(R(['down', 'down', 'down', 'enter']),\n"
        "                        ['t'], var_rows, '', 'bad', var_grammar,\n"
        "                        var_keys) == 'rules'\n"
        "try:\n"
        "    I._widget_choice(R(['down', 'down', 'down', 'down',\n"
        "                        'enter']), ['t'], var_rows, '', 'bad',\n"
        "                        var_grammar, var_keys)\n"
        "    raise SystemExit('variant q-row did not quit')\n"
        "except I.QuitTUI:\n"
        "    pass\n"
        "tier1 = list(I.TIER1_ORDER)\n"
        "det_map = {'claude-code': {'id': 'claude-code',\n"
        "                           'paths': ['/hx/.claude']}}\n"
        "visible = [a for a in tier1 if a in det_map]\n"
        "chosen = I._pick_agents_widget(R(['l', 'enter', 'enter']), tier1,\n"
        "                               {'claude-code'}, det_map, visible)\n"
        "assert chosen == ['claude-code']\n"
        "assert visible == tier1  # expansion mutated the shared list\n"
        "visible2 = [a for a in tier1 if a in det_map]\n"
        "esc = I._pick_agents_widget(R(['l', 'enter', 'esc']), tier1,\n"
        "                            {'claude-code'}, det_map, visible2)\n"
        "assert esc is None\n"
        "assert visible2 == tier1  # Esc keeps the expanded view\n"
        "print('rowkeys-ok')\n"
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
    assert "rowkeys-ok" in r.stdout


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


# Phase 3.1 (augment): promoted agent - --list shows augment detected
# without the "(no install support)" note
def test_augment_list_install_support(run, env_for, fake_home):
    (fake_home / ".augment").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [ln for ln in r.stdout.splitlines()
             if ln.strip().split() and ln.strip().split()[0] == "augment"]
    assert lines, r.stdout
    assert "(no install support)" not in lines[0]


# Phase 3.1 (kilo): promoted agent - --list shows kilo detected without
# the "(no install support)" note
def test_kilo_list_install_support(run, env_for, fake_home):
    (fake_home / ".kilocode").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [ln for ln in r.stdout.splitlines()
             if ln.strip().split() and ln.strip().split()[0] == "kilo"]
    assert lines, r.stdout
    assert "(no install support)" not in lines[0]


# Phase 3.1 (droid): promoted agent - --list shows droid detected without
# the "(no install support)" note
def test_droid_list_install_support(run, env_for, fake_home):
    (fake_home / ".factory").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [ln for ln in r.stdout.splitlines()
             if ln.strip().split() and ln.strip().split()[0] == "droid"]
    assert lines, r.stdout
    assert "(no install support)" not in lines[0]


# Phase 3.1 (deepagents): promoted agent - --list shows deepagents
# detected without the "(no install support)" note
def test_deepagents_list_install_support(run, env_for, fake_home):
    (fake_home / ".deepagents").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [ln for ln in r.stdout.splitlines()
             if ln.strip().split() and ln.strip().split()[0] == "deepagents"]
    assert lines, r.stdout
    assert "(no install support)" not in lines[0]


# Phase 3.1 (cline): promoted agent - --list shows cline detected without
# the "(no install support)" note
def test_cline_list_install_support(run, env_for, fake_home):
    (fake_home / ".cline").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [ln for ln in r.stdout.splitlines()
             if ln.strip().split() and ln.strip().split()[0] == "cline"]
    assert lines, r.stdout
    assert "(no install support)" not in lines[0]


# Phase 3.1 (crush): promoted agent - --list shows crush detected without
# the "(no install support)" note
def test_crush_list_install_support(run, env_for, fake_home):
    (fake_home / ".config" / "crush").mkdir(parents=True)
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [ln for ln in r.stdout.splitlines()
             if ln.strip().split() and ln.strip().split()[0] == "crush"]
    assert lines, r.stdout
    assert "(no install support)" not in lines[0]


# Phase 3.1 (amp): promoted agent - --list shows amp detected without
# the "(no install support)" note
def test_amp_list_install_support(run, env_for, fake_home):
    (fake_home / ".config" / "amp").mkdir(parents=True)
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [ln for ln in r.stdout.splitlines()
             if ln.strip().split() and ln.strip().split()[0] == "amp"]
    assert lines, r.stdout
    assert "(no install support)" not in lines[0]


# Phase 3.1 (goose): promoted agent - --list shows goose detected
# (XDG marker) without the "(no install support)" note
def test_goose_list_install_support(run, env_for, fake_home):
    (fake_home / ".config" / "goose").mkdir(parents=True)
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [ln for ln in r.stdout.splitlines()
             if ln.strip().split() and ln.strip().split()[0] == "goose"]
    assert lines, r.stdout
    assert "(no install support)" not in lines[0]


# Phase 3.1 (zed): promoted agent - --list shows zed detected without
# the "(no install support)" note
def test_zed_list_install_support(run, env_for, fake_home):
    (fake_home / ".config" / "zed").mkdir(parents=True)
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [ln for ln in r.stdout.splitlines()
             if ln.strip().split() and ln.strip().split()[0] == "zed"]
    assert lines, r.stdout
    assert "(no install support)" not in lines[0]


# Phase 3.1 (openhands): promoted agent - --list shows openhands
# detected (legacy ~/.openhands marker; the install target is the modern
# ~/.agents/skills dir) without the "(no install support)" note
def test_openhands_list_install_support(run, env_for, fake_home):
    (fake_home / ".openhands").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [ln for ln in r.stdout.splitlines()
             if ln.strip().split() and ln.strip().split()[0] == "openhands"]
    assert lines, r.stdout
    assert "(no install support)" not in lines[0]


# Phase 3.1 (warp): promoted agent - --list shows warp detected without
# the "(no install support)" note (detection marker ~/.warp differs from
# the install target ~/.agents/AGENTS.md - intended: ~/.warp is warp's
# config dir, never a rules location)
def test_warp_list_install_support(run, env_for, fake_home):
    (fake_home / ".warp").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [ln for ln in r.stdout.splitlines()
             if ln.strip().split() and ln.strip().split()[0] == "warp"]
    assert lines, r.stdout
    assert "(no install support)" not in lines[0]


# Phase 3.1 (junie): promoted agent - --list shows junie detected
# without the "(no install support)" note
def test_junie_list_install_support(run, env_for, fake_home):
    (fake_home / ".junie").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [ln for ln in r.stdout.splitlines()
             if ln.strip().split() and ln.strip().split()[0] == "junie"]
    assert lines, r.stdout
    assert "(no install support)" not in lines[0]


# Phase 3.1 (posit-assistant): promoted agent - --list shows
# posit-assistant detected without the "(no install support)" note
def test_posit_assistant_list_install_support(run, env_for, fake_home):
    (fake_home / ".posit" / "assistant").mkdir(parents=True)
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [ln for ln in r.stdout.splitlines()
             if ln.strip().split() and ln.strip().split()[0] ==
             "posit-assistant"]
    assert lines, r.stdout
    assert "(no install support)" not in lines[0]


# Phase 3.1 (zcode): promoted agent - --list shows zcode detected
# without the "(no install support)" note
def test_zcode_list_install_support(run, env_for, fake_home):
    (fake_home / ".zcode").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [ln for ln in r.stdout.splitlines()
             if ln.strip().split() and ln.strip().split()[0] == "zcode"]
    assert lines, r.stdout
    assert "(no install support)" not in lines[0]


# Phase 3.1 (minimax-code): user scope has no verified target - the
# warn note fires on stdout and nothing is written (~/.minimax/AGENTS.md
# is bundle-read but undocumented; notes are say()-only, so no --json)
def test_minimax_code_user_scope_warn_only(run, env_for, fake_home,
                                           src_file):
    r = run(["--agent", "minimax-code", "--scope", "user", "--yes",
             "--source", str(src_file)], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    assert ("warn: minimax-code has no verified user-wide target; "
            "skipping (project scope only)" in r.stdout)
    assert "nothing to install" in r.stdout
    assert not (fake_home / ".minimax" / "AGENTS.md").exists()


# Phase 3.1 (minimax-code): promoted agent - --list shows minimax-code
# detected without the "(no install support)" note
def test_minimax_code_list_install_support(run, env_for, fake_home):
    (fake_home / ".minimax").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [ln for ln in r.stdout.splitlines()
             if ln.strip().split() and ln.strip().split()[0] ==
             "minimax-code"]
    assert lines, r.stdout
    assert "(no install support)" not in lines[0]


# Phase 3.1 (openclaw): project scope is warn-only - openclaw never
# reads project ./AGENTS.md (personal workspace model), so no shared
# block is written for it (notes are say()-only, so no --json for the
# warn; the --json run asserts the empty target list)
def test_openclaw_project_scope_warn_only(run, env_for, fake_home, proj,
                                          src_file):
    env = env_for(fake_home)
    r = run(["--agent", "openclaw", "--scope", "project", "--project-dir",
             str(proj), "--yes", "--source", str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert ("warn: openclaw is user-scope only (personal workspace); "
            "skipping" in r.stdout)
    assert not (proj / "AGENTS.md").exists()
    r2 = run(["--agent", "openclaw", "--scope", "project", "--project-dir",
              str(proj), "--yes", "--json", "--source", str(src_file)],
             env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    payload = json.loads(r2.stdout)
    assert payload["targets"] == []
    assert not (proj / "AGENTS.md").exists()


# Phase 3.1 (openclaw): promoted agent - --list shows openclaw detected
# without the "(no install support)" note
def test_openclaw_list_install_support(run, env_for, fake_home):
    (fake_home / ".openclaw").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [ln for ln in r.stdout.splitlines()
             if ln.strip().split() and ln.strip().split()[0] == "openclaw"]
    assert lines, r.stdout
    assert "(no install support)" not in lines[0]


# Phase 3.1 (kimi-code-cli): promoted agent - --list shows kimi-code-cli
# detected without the "(no install support)" note
def test_kimi_code_cli_list_install_support(run, env_for, fake_home):
    (fake_home / ".kimi-code").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [ln for ln in r.stdout.splitlines()
             if ln.strip().split() and ln.strip().split()[0] ==
             "kimi-code-cli"]
    assert lines, r.stdout
    assert "(no install support)" not in lines[0]


# Canary round 2 (owner, 2026-09-09): Esc is BACK-NAVIGATION, not a
# mode switch - the numbered prompt is a capability fallback only.  A
# real TTY cannot be scripted headless, so a fake reader feeds the
# widget the same key events StdinReader would (process isolation
# preserved, like the decoders test above).
def test_widget_esc_back_navigation_pure():
    code = (
        "import install as I" + chr(10) +
        "class R:" + chr(10) +
        "    def __init__(self, keys): self.k = list(keys); self.i = 0" + chr(10) +
        "    def read_key(self):" + chr(10) +
        "        v = self.k[self.i]; self.i += 1; return v" + chr(10) +
        "class RR(R):" + chr(10) +
        "    def raw_keys(self): return True" + chr(10) +
        "def parse_scope(b):" + chr(10) +
        "    a = b.strip().lower()" + chr(10) +
        "    if a in ('q', 'quit'): raise I.QuitTUI()" + chr(10) +
        "    if a in ('u', 'user'): return 'user'" + chr(10) +
        "    if a in ('p', 'proj', 'project'): return 'project'" + chr(10) +
        "    return None" + chr(10) +
        "rows = ['(u)ser', '(p)roject', '(q)uit']" + chr(10) +
        "# mid-menu Esc -> None: the BACK signal to the caller" + chr(10) +
        "v = I._widget_choice(R(['esc']), ['t'], rows, '', 'x'," + chr(10) +
        "                        parse_scope, ['u', 'p', 'q'])" + chr(10) +
        "assert v is None" + chr(10) +
        "# the agent picker turns widget-Esc into _BACK (det_map empty" + chr(10) +
        "# -> zero-detection full view, so the cursor math is real)" + chr(10) +
        "r = I._pick_agents(RR(['esc']), set(), {})" + chr(10) +
        "assert r is I._BACK" + chr(10) +
        "print('esc-back-ok')"
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
    assert "esc-back-ok" in r.stdout


# Canary round 2, end-to-end: the WIZARD wiring, not just the widget
# components - a fake reader with raw keys drives _tui_flow through
# scope -> family, Esc -> back to scope, user -> agents, Esc -> back
# to scope, then q.  Proves headless that Esc re-asks the previous
# menu all the way up the chain (the owner canary then only has to
# confirm the same behavior on real terminals).
def test_tui_flow_esc_wizard_pure(tmp_path):
    (tmp_path / "s.md").write_bytes(
        b"# R" + bytes([10]) + b"body" + bytes([10]))
    src_arg = str(tmp_path / "s.md").replace(chr(92), "/")
    code = (
        "import install as I" + chr(10) +
        "class R:" + chr(10) +
        "    def __init__(self, keys): self.k = list(keys); self.i = 0" + chr(10) +
        "    def read_key(self):" + chr(10) +
        "        v = self.k[self.i]; self.i += 1; return v" + chr(10) +
        "    def raw_keys(self): return True" + chr(10) +
        "args = I.build_parser().parse_args(" + chr(10) +
        "    ['--interactive', '--source', '" + src_arg + "'," + chr(10) +
        "     '--project-dir', '.'])" + chr(10) +
        "keys = ['down', 'enter',   # scope -> project -> family menu" + chr(10) +
        "        'esc',                 # family -> back to scope" + chr(10) +
        "        'enter',               # scope -> user -> agents menu" + chr(10) +
        "        'esc',                 # agents -> back to scope" + chr(10) +
        "        'esc']                 # Esc at root == q (round 3)" + chr(10) +
        "try:" + chr(10) +
        "    I._tui_flow(args, R(keys))" + chr(10) +
        "    raise SystemExit('flow returned without QuitTUI')" + chr(10) +
        "except I.QuitTUI:" + chr(10) +
        "    print('wizard-esc-ok')"
    )
    import subprocess, sys
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(INSTALL_PY.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        env={**os.environ, "HOME": str(tmp_path), "USERPROFILE": str(tmp_path),
             "PWD": str(tmp_path)},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "wizard-esc-ok" in r.stdout
    # Esc walked back to the scope menu TWICE -> 3 visits; each
    # visit renders once per key event, so the fixed key script
    # yields exactly 4 frames: visit1 (render + down-redraw),
    # visit2 (render), visit3 (render; the closing Esc returns
    # without a redraw - and counts as quit per round 3)
    assert r.stdout.count("Where should the rules apply?") == 4, r.stdout
    # the round trips actually reached the family and agents menus
    assert "Which family?" in r.stdout
    assert "Scanning for installed agents" in r.stdout


# Canary round 2, the missing matrix cell: Esc at the Claude-file
# VARIANT menu walks back to the FAMILY menu (the _tui_project inner
# loop's continue path - same wiring class the wizard test caught).
def test_tui_flow_variant_esc_back_pure(tmp_path):
    (tmp_path / "s.md").write_bytes(
        b"# R" + bytes([10]) + b"body" + bytes([10]))
    src_arg = str(tmp_path / "s.md").replace(chr(92), "/")
    code = (
        "import install as I" + chr(10) +
        "class R:" + chr(10) +
        "    def __init__(self, keys): self.k = list(keys); self.i = 0" + chr(10) +
        "    def read_key(self):" + chr(10) +
        "        v = self.k[self.i]; self.i += 1; return v" + chr(10) +
        "    def raw_keys(self): return True" + chr(10) +
        "args = I.build_parser().parse_args(" + chr(10) +
        "    ['--interactive', '--source', '" + src_arg + "'," + chr(10) +
        "     '--project-dir', '.'])" + chr(10) +
        "keys = ['down', 'enter',   # scope -> project" + chr(10) +
        "        'down', 'enter',   # family -> (c)laude.md -> variant menu" + chr(10) +
        "        'esc',                 # variant -> back to family" + chr(10) +
        "        'q', 'enter']          # quit at the family menu" + chr(10) +
        "try:" + chr(10) +
        "    I._tui_flow(args, R(keys))" + chr(10) +
        "    raise SystemExit('flow returned without QuitTUI')" + chr(10) +
        "except I.QuitTUI:" + chr(10) +
        "    print('variant-esc-ok')"
    )
    import subprocess
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(INSTALL_PY.parent),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        env={**os.environ, "HOME": str(tmp_path), "USERPROFILE": str(tmp_path)},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "variant-esc-ok" in r.stdout
    assert "Which Claude file?" in r.stdout
    # family visited twice: visit1 = render + down-redraw (enter
    # returns without redraw), visit2 = render + typed-q redraw
    assert r.stdout.count("Which family?") == 4, r.stdout


# Canary round 3: the cursor row renders in reverse video on VT

# terminals (and never emits escapes otherwise - the piped tests

# assert a clean stream elsewhere).
def test_menu_block_cursor_inversion_pure():
    code = (
        "import install as I" + chr(10) +
        "plain = I._menu_block(['t'], ['a', 'b'], 1, [], False, '', '', " + chr(10) +
        "                       '', False)" + chr(10) +
        "assert not any(chr(27) in ln for ln in plain), plain" + chr(10) +
        "vt = I._menu_block(['t'], ['a', 'b'], 1, [], False, '', '', " + chr(10) +
        "                    '', True)" + chr(10) +
        "assert vt[1] == '  a', vt" + chr(10) +
        "assert vt[2] == chr(27) + '[7m> b ' + chr(27) + '[27m', vt" + chr(10) +
        "top = I._menu_block(['t'], ['a', 'b'], 0, [], False, '', '', " + chr(10) +
        "                    '', True)" + chr(10) +
        "assert len(top[1]) == len(vt[2]), (top, vt)" + chr(10) +
        "multi = I._menu_block(['t'], ['a'], 0, [True], True, '', '', " + chr(10) +
        "                       '', True)" + chr(10) +
        "assert multi[1].startswith(chr(27) + '[7m> [x] a'), multi" + chr(10) +
        "print('invert-ok')"
    )
    import subprocess
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
    assert "invert-ok" in r.stdout


# Canary round 3: --ascii forces the numbered-prompt navigation -
# the arrow widget never engages, every prompt stays scriptable
def test_ascii_flag_forces_numbered_prompts(run, env_for, fake_home,
                                            src_file):
    (fake_home / ".claude").mkdir()
    r = run(["--interactive", "--ascii", "--source", str(src_file)],
            env=env_for(fake_home), cwd=fake_home,
            input_text="u" + chr(10) + "1" + chr(10) + "y" + chr(10),
            timeout=120)
    combined = r.stdout + r.stderr
    assert r.returncode == 0, combined
    assert "Install into which agents? [1-1]" in r.stdout
    assert "Space toggles" not in r.stdout  # widget never engaged
    assert chr(27) + "[" not in r.stdout
    assert "Traceback" not in combined
    drop = fake_home / ".claude" / "rules" / "behave.md"
    assert drop.is_file()
    assert drop.read_bytes().startswith(MARKER)
    help_r = run(["--help"])
    assert "--ascii" in help_r.stdout


# Canary round 3 follow-up: --ascii ALONE launches the TUI (it picks
# the navigation style, so it implies --interactive), not headless
def test_ascii_alone_launches_tui(run, env_for, fake_home, src_file):
    (fake_home / ".claude").mkdir()
    r = run(["--ascii", "--source", str(src_file)],
            env=env_for(fake_home), cwd=fake_home,
            input_text="u" + chr(10) + "1" + chr(10) + "y" + chr(10),
            timeout=120)
    combined = r.stdout + r.stderr
    assert r.returncode == 0, combined
    assert "Where should the rules apply?" in r.stdout
    assert "Install into which agents? [1-1]" in r.stdout
    assert chr(27) + "[" not in r.stdout
    assert "no agents specified" not in combined  # ascii-alone-ok
    drop = fake_home / ".claude" / "rules" / "behave.md"
    assert drop.is_file()
    assert drop.read_bytes().startswith(MARKER)
