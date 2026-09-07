"""Plan section 9, tests 9-12: removal semantics."""

import json

B = b"<!-- BEGIN behave - installed by install.py; --remove uninstalls -->\n"
E = b"<!-- END behave -->\n"
MARKER = (b"<!-- installed by install.py (behave); "
          b"--remove deletes this file -->\n")


# Test 9: inline strip leaves remainder byte-identical (BOM/CRLF included);
#         empty/whitespace remainder deletes the file; plain copies untouched
def test_9_inline_strip(run, env_for, fake_home, proj, src_file):
    env = env_for(fake_home)
    content = src_file.read_bytes()

    target = fake_home / ".codex" / "AGENTS.md"
    target.parent.mkdir(parents=True)
    original = b"\xef\xbb\xbf# Notes\r\n\r\nline two\r\nmore\r\n"
    target.write_bytes(original)
    r = run(["--agent", "codex", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    r2 = run(["--remove", "--agent", "codex", "--scope", "user", "--yes"],
             env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert target.read_bytes() == original

    gemini = fake_home / ".gemini" / "GEMINI.md"
    run(["--agent", "gemini-cli", "--scope", "user", "--yes", "--source",
         str(src_file)], env=env)
    assert gemini.is_file()
    run(["--remove", "--agent", "gemini-cli", "--scope", "user", "--yes"],
        env=env)
    assert not gemini.exists()

    pi = fake_home / ".pi" / "agent" / "AGENTS.md"
    pi.parent.mkdir(parents=True)
    pi.write_bytes(B + content + E + b"   \n")
    run(["--remove", "--agent", "pi", "--scope", "user", "--yes"], env=env)
    assert not pi.exists()

    run(["--copy-only", "--project-dir", str(proj), "--source",
         str(src_file)], env=env)
    assert (proj / "BEHAVE.md").is_file()
    r5 = run(["--remove", "--project-dir", str(proj), "--yes"], env=env)
    assert r5.returncode == 0, r5.stdout + r5.stderr
    assert (proj / "BEHAVE.md").read_bytes() == content


# Test 10: scan-all finds user + project variations; narrowing filters
#          exactly; nothing found -> exit 0
def test_10_scan_all_and_narrowing(run, env_for, fake_home, tmp_path,
                                   src_file):
    env = env_for(fake_home)
    run(["--agent", "codex", "--scope", "user", "--yes", "--source",
         str(src_file)], env=env)

    proj = tmp_path / "p1"
    proj.mkdir()
    (proj / "CLAUDE.md").write_bytes(b"# project claude\n")
    run(["--agent", "claude-code", "--scope", "project", "--claude-variant",
         "root", "--project-dir", str(proj), "--yes", "--source",
         str(src_file)], env=env)
    run(["--agent", "gemini-cli,cursor,github-copilot", "--scope",
         "project", "--project-dir", str(proj), "--yes", "--source",
         str(src_file)], env=env)
    assert (proj / ".cursor" / "rules" / "behave.mdc").is_file()

    r = run(["--remove", "--project-dir", str(proj), "--yes"], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "AGENTS.md" in r.stdout
    assert not (fake_home / ".codex" / "AGENTS.md").exists()
    assert not (proj / ".cursor" / "rules" / "behave.mdc").exists()
    assert not (proj / "GEMINI.md").exists()
    assert not (proj / ".github" / "copilot-instructions.md").exists()
    assert (proj / "CLAUDE.md").read_bytes() == b"# project claude\n"

    proj2 = tmp_path / "p2"
    proj2.mkdir()
    run(["--agent", "gemini-cli,cursor", "--scope", "project",
         "--project-dir", str(proj2), "--yes", "--source", str(src_file)],
        env=env)
    r2 = run(["--remove", "--agent", "cursor", "--scope", "project",
              "--project-dir", str(proj2), "--yes"], env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert not (proj2 / ".cursor" / "rules" / "behave.mdc").exists()
    assert b"<!-- BEGIN behave " in (proj2 / "GEMINI.md").read_bytes()

    home2 = tmp_path / "h2"
    home2.mkdir()
    proj3 = tmp_path / "p3"
    proj3.mkdir()
    r3 = run(["--remove", "--project-dir", str(proj3), "--yes"],
             env=env_for(home2))
    assert r3.returncode == 0, r3.stdout + r3.stderr
    assert "nothing installed" in r3.stdout


# Test 11: shared ./AGENTS.md block removal reports all agents served
def test_11_shared_block_reports_family(run, env_for, fake_home, proj,
                                        src_file):
    env = env_for(fake_home)
    r = run(["--agent", "codex,opencode,pi,devin", "--scope", "project",
             "--project-dir", str(proj), "--yes", "--source",
             str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (proj / "AGENTS.md").is_file()

    r2 = run(["--remove", "--project-dir", str(proj), "--yes"], env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert "codex,opencode,pi,devin" in r2.stdout
    assert not (proj / "AGENTS.md").exists()

    run(["--agent", "codex,opencode,pi,devin", "--scope", "project",
         "--project-dir", str(proj), "--yes", "--source", str(src_file)],
        env=env)
    r3 = run(["--remove", "--project-dir", str(proj), "--yes", "--json"],
             env=env)
    payload = json.loads(r3.stdout)
    agents = [t["agent"] for t in payload["targets"]]
    assert "codex,opencode,pi,devin" in agents


# Test 12: stale-block hint printed when a second marked block exists
def test_12_stale_hint(run, env_for, fake_home, proj, src_file):
    env = env_for(fake_home)
    args = ["--agent", "codex", "--scope", "user", "--yes", "--project-dir",
            str(proj), "--source", str(src_file)]
    run(args, env=env)
    run(["--agent", "claude-code", "--scope", "project", "--claude-variant",
         "root", "--project-dir", str(proj), "--yes", "--source",
         str(src_file)], env=env)
    r = run(args, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "also found:" in r.stdout
    assert "CLAUDE.md" in r.stdout
