"""Plan section 9 smoke test: full cycle against a temp git repo."""

import subprocess

import pytest

B = b"<!-- BEGIN behave - installed by install.py; --remove uninstalls -->\n"
MARKER = (b"<!-- installed by install.py (behave); "
          b"--remove deletes this file -->\n")


def test_smoke_full_cycle(run, env_for, tmp_path, src_file, git_available):
    if not git_available:
        pytest.skip("git not available")
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True,
                   timeout=60)
    env = env_for(tmp_path / "h")

    base = ["--project-dir", str(repo), "--yes", "--source", str(src_file)]
    r1 = run(["--agent", "claude-code", "--scope", "project",
              "--claude-variant", "rules"] + base, env=env)
    assert r1.returncode == 0, r1.stdout + r1.stderr
    r2 = run(["--agent", "codex,opencode,pi,devin", "--scope",
              "project"] + base, env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    r3 = run(["--agent", "cursor", "--scope", "project"] + base, env=env)
    assert r3.returncode == 0, r3.stdout + r3.stderr

    f_rules = repo / ".claude" / "rules" / "behave.md"
    f_agents = repo / "AGENTS.md"
    f_cursor = repo / ".cursor" / "rules" / "behave.mdc"
    assert f_rules.read_bytes().startswith(MARKER)
    assert f_agents.read_bytes().startswith(B)
    assert f_cursor.read_bytes().startswith(b"---\nalwaysApply: true\n---\n")
    assert b"# RULES\nrules body line\n" in f_agents.read_bytes()

    st = subprocess.run(["git", "status", "--porcelain"], cwd=str(repo),
                        capture_output=True, text=True, env=env,
                        timeout=60)
    # untracked dirs are collapsed by git: ?? .claude/, ?? .cursor/, ?? AGENTS.md
    assert "AGENTS.md" in st.stdout
    assert ".claude/" in st.stdout
    assert ".cursor/" in st.stdout

    r4 = run(["--remove", "--scope", "project", "--project-dir", str(repo),
              "--yes"], env=env)
    assert r4.returncode == 0, r4.stdout + r4.stderr
    assert not f_rules.exists()
    assert not f_agents.exists()
    assert not f_cursor.exists()

    r5 = run(["--remove", "--project-dir", str(repo), "--yes"], env=env)
    assert r5.returncode == 0, r5.stdout + r5.stderr
    assert "nothing installed" in r5.stdout

    st2 = subprocess.run(["git", "status", "--porcelain"], cwd=str(repo),
                         capture_output=True, text=True, env=env,
                         timeout=60)
    assert st2.stdout.strip() == ""
