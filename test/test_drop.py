"""Plan section 9, tests 7-8: drop mode."""

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
