"""Plan section 9, tests 7-8: drop mode."""

import json

MARKER = (b"<!-- installed by install.py (behave); "
          b"--remove deletes this file -->\n")


# Test 7: drop creates missing rules dirs with frontmatter + marker line;
#         re-run overwrites identically
def test_7_drop_targets(run, env_for, fake_home, proj, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "claude-code,cursor,github-copilot", "--scope",
             "user", "--yes", "--source", str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr

    claude = fake_home / ".claude" / "rules" / "behave.md"
    cursor = fake_home / ".cursor" / "rules" / "behave.mdc"
    copilot = (fake_home / ".copilot" / "instructions" /
               "behave.instructions.md")

    cdata = claude.read_bytes()
    assert cdata.startswith(MARKER)
    assert not cdata.startswith(b"---")
    assert b"# RULES\nrules body line\n" in cdata

    udata = cursor.read_bytes()
    assert udata.startswith(b"---\nalwaysApply: true\n---\n")
    assert MARKER in udata

    pdata = copilot.read_bytes()
    assert pdata.startswith(b'---\napplyTo: "**"\n---\n')
    assert MARKER in pdata

    r2 = run(["--agent", "devin", "--scope", "project", "--project-dir",
              str(proj), "--yes", "--source", str(src_file)], env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    dfile = proj / ".devin" / "rules" / "behave.md"
    ddata = dfile.read_bytes()
    assert ddata.startswith(b"---\ntrigger: always_on\n---\n")
    assert MARKER in ddata

    before = [p.read_bytes() for p in (claude, cursor, copilot, dfile)]
    run(["--agent", "claude-code,cursor,github-copilot", "--scope", "user",
         "--yes", "--source", str(src_file)], env=env)
    run(["--agent", "devin", "--scope", "project", "--project-dir",
         str(proj), "--yes", "--source", str(src_file)], env=env)
    after = [p.read_bytes() for p in (claude, cursor, copilot, dfile)]
    assert before == after


# Test 8: remove deletes marker-bearing dropped files; a user-authored file
#         with the same name but no marker is left untouched
def test_8_remove_only_marker_bearing(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "claude-code,cursor", "--scope", "user", "--yes",
             "--source", str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    claude = fake_home / ".claude" / "rules" / "behave.md"
    cursor = fake_home / ".cursor" / "rules" / "behave.mdc"
    assert claude.is_file() and cursor.is_file()

    r2 = run(["--remove", "--agent", "claude-code,cursor", "--scope",
              "user", "--yes"], env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert not claude.exists()
    assert not cursor.exists()

    claude.write_bytes(b"my own claude rules\n")
    cursor.write_bytes(b"my own cursor rules\n")
    r3 = run(["--remove", "--agent", "claude-code,cursor", "--scope",
              "user", "--yes"], env=env)
    assert r3.returncode == 0, r3.stdout + r3.stderr
    assert "nothing installed" in r3.stdout
    assert claude.read_bytes() == b"my own claude rules\n"
    assert cursor.read_bytes() == b"my own cursor rules\n"


# Test 8b: user-scope Cursor drop warns that ~/.cursor/rules loads only
#          for projects inside the home directory (stdout + --json field)
def test_8b_cursor_user_drop_warning(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "cursor", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    cursor = fake_home / ".cursor" / "rules" / "behave.mdc"
    assert cursor.is_file()
    assert cursor.read_bytes().startswith(b"---\nalwaysApply: true\n---\n")
    assert "warning:" in r.stdout
    assert "resolved home:" in r.stdout
    assert str(fake_home) in r.stdout

    r2 = run(["--agent", "cursor", "--scope", "user", "--yes", "--json",
              "--source", str(src_file)], env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    payload = json.loads(r2.stdout)
    entry = payload["targets"][0]
    assert entry["agent"] == "cursor"
    assert entry["warning"]
    assert "resolved home: %s" % fake_home in entry["warning"]


# Phase 3.1 (roo): user-scope drop into ~/.roo/rules (no frontmatter,
# plain marker + rules body)
def test_roo_user_drop(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "roo", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    drop = fake_home / ".roo" / "rules" / "behave.md"
    data = drop.read_bytes()
    assert data.startswith(MARKER)
    assert not data.startswith(b"---")
    assert b"# RULES\nrules body line\n" in data


# Phase 3.1 (augment): user-scope drop into ~/.augment/rules (no
# frontmatter, plain marker + rules body)
def test_augment_user_drop(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "augment", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    drop = fake_home / ".augment" / "rules" / "behave.md"
    data = drop.read_bytes()
    assert data.startswith(MARKER)
    assert not data.startswith(b"---")
    assert b"# RULES\nrules body line\n" in data


# Phase 8 (trae): project-scope drop into .trae/rules with
# alwaysApply frontmatter; the root AGENTS.md family path is never
# written (trae reads AGENTS.md only behind an import toggle)
def test_trae_project_drop(run, env_for, fake_home, proj, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "trae", "--scope", "project", "--project-dir",
             str(proj), "--yes", "--source", str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    drop = proj / ".trae" / "rules" / "behave.md"
    data = drop.read_bytes()
    assert data.startswith(b"---\nalwaysApply: true\n---\n")
    assert b"# RULES\nrules body line\n" in data
    assert not (proj / "AGENTS.md").exists()


# Phase 8 (kiro-cli): user-scope drop into ~/.kiro/steering (no
# frontmatter - the CLI ignores inclusion modes, the IDE defaults to
# always)
def test_kiro_cli_user_drop(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "kiro-cli", "--scope", "user", "--yes",
             "--source", str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    drop = fake_home / ".kiro" / "steering" / "behave.md"
    data = drop.read_bytes()
    assert data.startswith(MARKER)
    assert not data.startswith(b"---")
    assert b"# RULES\nrules body line\n" in data


# Phase 8 (qoder): user-scope drop into ~/.qoder/rules (no frontmatter
# - documented default: "rules are always active by default")
def test_qoder_user_drop(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "qoder", "--scope", "user", "--yes",
             "--source", str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    drop = fake_home / ".qoder" / "rules" / "behave.md"
    data = drop.read_bytes()
    assert data.startswith(MARKER)
    assert not data.startswith(b"---")
    assert b"# RULES\nrules body line\n" in data


# Phase 8 (grok): user-scope drop into ~/.grok/rules (no frontmatter -
# the home rules dir is scanned unconditionally; bodies are
# frontmatter-stripped)
def test_grok_user_drop(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "grok", "--scope", "user", "--yes",
             "--source", str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    drop = fake_home / ".grok" / "rules" / "behave.md"
    data = drop.read_bytes()
    assert data.startswith(MARKER)
    assert not data.startswith(b"---")
    assert b"# RULES\nrules body line\n" in data


# Phase 8 batch 2 (bob): user-scope drop into ~/.bob/rules (no
# frontmatter - plain text rules, no activation system documented)
def test_bob_user_drop(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "bob", "--scope", "user", "--yes",
             "--source", str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    drop = fake_home / ".bob" / "rules" / "behave.md"
    data = drop.read_bytes()
    assert data.startswith(MARKER)
    assert not data.startswith(b"---")
    assert b"# RULES\nrules body line\n" in data


# Phase 8 batch 2 (trae-cn): user-scope drop into ~/.trae-cn/user_rules/
# (the CN global rules dir; alwaysApply frontmatter like the project
# drop - docs.trae.cn/work_rules)
def test_trae_cn_user_drop(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "trae-cn", "--scope", "user", "--yes",
             "--source", str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    drop = fake_home / ".trae-cn" / "user_rules" / "behave.md"
    data = drop.read_bytes()
    assert data.startswith(b"---\nalwaysApply: true\n---\n")
    assert b"# RULES\nrules body line\n" in data


# Phase 8 batch 2 (trae-cn): project-scope drop SHARES .trae/rules with
# trae (one file, two editions; the root AGENTS.md family path is never
# written - CN import toggle is off by default, desktop-only)
def test_trae_cn_project_drop(run, env_for, fake_home, proj, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "trae-cn", "--scope", "project", "--project-dir",
             str(proj), "--yes", "--source", str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    drop = proj / ".trae" / "rules" / "behave.md"
    data = drop.read_bytes()
    assert data.startswith(b"---\nalwaysApply: true\n---\n")
    assert b"# RULES\nrules body line\n" in data
    assert not (proj / "AGENTS.md").exists()


# Phase 3.1 (kilo): user-scope drop into ~/.kilocode/rules (no
# frontmatter, plain marker + rules body)
def test_kilo_user_drop(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "kilo", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    drop = fake_home / ".kilocode" / "rules" / "behave.md"
    data = drop.read_bytes()
    assert data.startswith(MARKER)
    assert not data.startswith(b"---")
    assert b"# RULES\nrules body line\n" in data


# Phase 3.1 (cline): user-scope drop into ~/.cline/rules (no frontmatter,
# plain marker + rules body)
def test_cline_user_drop(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "cline", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    drop = fake_home / ".cline" / "rules" / "behave.md"
    data = drop.read_bytes()
    assert data.startswith(MARKER)
    assert not data.startswith(b"---")
    assert b"# RULES\nrules body line\n" in data


# Phase 3.1 (openhands): user-scope drop into ~/.agents/skills (no
# frontmatter, plain marker + rules body)
def test_openhands_user_drop(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "openhands", "--scope", "user", "--yes",
             "--source", str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    drop = fake_home / ".agents" / "skills" / "behave.md"
    data = drop.read_bytes()
    assert data.startswith(MARKER)
    assert not data.startswith(b"---")
    assert b"# RULES\nrules body line\n" in data


# Phase 9 (aider-desk): user-scope drop into ~/.aider-desk/rules (no
# frontmatter - no activation system documented, always active)
def test_aider_desk_user_drop(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "aider-desk", "--scope", "user", "--yes",
             "--source", str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    drop = fake_home / ".aider-desk" / "rules" / "behave.md"
    data = drop.read_bytes()
    assert data.startswith(MARKER)
    assert not data.startswith(b"---")
    assert b"# RULES\nrules body line\n" in data


# Phase 9 (qoder-cn): user-scope drop into ~/.qoder-cn/rules (bare,
# mirrors the intl qoder exactly - always active by default)
def test_qoder_cn_user_drop(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "qoder-cn", "--scope", "user", "--yes",
             "--source", str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    drop = fake_home / ".qoder-cn" / "rules" / "behave.md"
    data = drop.read_bytes()
    assert data.startswith(MARKER)
    assert not data.startswith(b"---")
    assert b"# RULES\nrules body line\n" in data
