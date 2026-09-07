"""Plan section 9, tests 13-16: targets and detection."""

import subprocess
from pathlib import Path

import pytest

B = b"<!-- BEGIN behave - installed by install.py; --remove uninstalls -->\n"
MARKER = (b"<!-- installed by install.py (behave); "
          b"--remove deletes this file -->\n")


def git_init(d):
    subprocess.run(["git", "init"], cwd=str(d), capture_output=True,
                   timeout=60)


# Test 13: scope matrix: user vs project vs local (+ auto rule)
def test_13_scope_matrix(run, env_for, fake_home, tmp_path, src_file,
                         git_available):
    if not git_available:
        pytest.skip("git not available")
    env = env_for(fake_home)

    r = run(["--agent", "gemini-cli", "--scope", "user", "--yes",
             "--source", str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (fake_home / ".gemini" / "GEMINI.md").is_file()

    p1 = tmp_path / "p1"
    p1.mkdir()
    run(["--agent", "gemini-cli", "--scope", "project", "--project-dir",
         str(p1), "--yes", "--source", str(src_file)], env=env)
    assert (p1 / "GEMINI.md").is_file()

    p2 = tmp_path / "p2"
    p2.mkdir()
    git_init(p2)
    r2 = run(["--agent", "claude-code", "--scope", "local",
              "--project-dir", str(p2), "--yes", "--source",
              str(src_file)], env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert (p2 / "CLAUDE.local.md").read_bytes().startswith(B)
    gi = p2 / ".gitignore"
    assert gi.is_file()
    assert "CLAUDE.local.md" in gi.read_text(encoding="utf-8")

    p3 = tmp_path / "p3"
    p3.mkdir()
    r3 = run(["--agent", "claude-code", "--scope", "local",
              "--project-dir", str(p3), "--yes", "--source",
              str(src_file)], env=env)
    assert r3.returncode == 0, r3.stdout + r3.stderr
    assert (p3 / "CLAUDE.local.md").is_file()
    assert not (p3 / ".gitignore").exists()
    assert "no git repo" in (r3.stdout + r3.stderr)

    p4 = tmp_path / "p4"
    p4.mkdir()
    git_init(p4)
    run(["--agent", "gemini-cli", "--scope", "auto", "--yes", "--source",
         str(src_file)], env=env, cwd=p4)
    assert (p4 / "GEMINI.md").is_file()

    (fake_home / ".gemini" / "GEMINI.md").unlink()
    p5 = tmp_path / "p5"
    p5.mkdir()
    run(["--agent", "gemini-cli", "--scope", "auto", "--yes", "--source",
         str(src_file)], env=env, cwd=p5)
    assert (fake_home / ".gemini" / "GEMINI.md").is_file()

    r6 = run(["--agent", "codex", "--scope", "local", "--project-dir",
              str(p5), "--yes", "--source", str(src_file)], env=env)
    assert r6.returncode == 0, r6.stdout + r6.stderr
    assert "warn" in (r6.stdout + r6.stderr).lower()
    assert not (p5 / "AGENTS.md").exists()


# Test 14: variant + mode resolution -> correct files, import-free content
def test_14_variant_mode_resolution(run, env_for, fake_home, tmp_path,
                                    src_file):
    env = env_for(fake_home)
    cases = [
        ("root", "v1", ["CLAUDE.md"], "inline"),
        ("dot-claude", "v2", [".claude", "CLAUDE.md"], "inline"),
        ("local", "v3", ["CLAUDE.local.md"], "inline"),
        ("rules", "v4", [".claude", "rules", "behave.md"], "drop"),
        (None, "v5", [".claude", "rules", "behave.md"], "drop"),
    ]
    for variant, name, rel, mode in cases:
        d = tmp_path / name
        d.mkdir()
        args = ["--agent", "claude-code", "--scope", "project",
                "--project-dir", str(d), "--yes", "--source", str(src_file)]
        if variant:
            args += ["--claude-variant", variant]
        r = run(args, env=env)
        assert r.returncode == 0, r.stdout + r.stderr
        f = d.joinpath(*rel)
        assert f.is_file(), f
        data = f.read_bytes()
        if mode == "inline":
            assert data.startswith(B)
        else:
            assert data.startswith(MARKER)
        assert b"\n@" not in data
        assert not data.startswith(b"@")

    run(["--agent", "claude-code", "--scope", "user", "--claude-mode",
         "rules", "--yes", "--source", str(src_file)], env=env)
    assert (fake_home / ".claude" / "rules" / "behave.md").is_file()
    run(["--agent", "claude-code", "--scope", "user", "--claude-mode",
         "inline", "--yes", "--source", str(src_file)], env=env)
    assert (fake_home / ".claude" / "CLAUDE.md").read_bytes().startswith(B)


def detected_ids(out):
    ids = set()
    in_det = False
    for line in out.splitlines():
        if line.startswith("Detected agents ("):
            in_det = True
            continue
        if line.startswith("All known ids"):
            in_det = False
            continue
        if in_det and line.startswith("  ") and line.strip():
            token = line.strip().split()[0]
            if token != "(none)":
                ids.add(token)
    return ids


# Test 15: detection: fake HOME markers, env override, multi-marker, eve
def test_15_detection(run, env_for, fake_home, tmp_path):
    (fake_home / ".claude").mkdir()
    (fake_home / ".kimi-code").mkdir()
    (fake_home / ".codeium" / "windsurf").mkdir(parents=True)
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    ids = detected_ids(r.stdout)
    assert "claude-code" in ids
    assert "kimi-code-cli" in ids
    assert "windsurf" in ids
    assert "deprecated" in r.stdout
    assert "All known ids (77):" in r.stdout

    h2 = tmp_path / "h2"
    h2.mkdir()
    (h2 / ".kimi").mkdir()
    ids2 = detected_ids(run(["--list"], env=env_for(h2)).stdout)
    assert "kimi-code-cli" in ids2

    h3 = tmp_path / "h3"
    h3.mkdir()
    custom = h3 / "claudecfg"
    custom.mkdir()
    env3 = env_for(h3, CLAUDE_CONFIG_DIR=str(custom))
    r3 = run(["--list"], env=env3)
    assert "claude-code" in detected_ids(r3.stdout)
    assert str(custom) in r3.stdout

    ev = tmp_path / "evproj"
    (ev / "agent").mkdir(parents=True)
    (ev / "package.json").write_text('{"dependencies": {"eve": "^1.0"}}')
    ids4 = detected_ids(run(["--list"], env=env_for(fake_home),
                            cwd=ev).stdout)
    assert "eve" in ids4
    (ev / "package.json").write_text(
        '{"dependencies": {"left-pad": "^1.0"}}')
    ids5 = detected_ids(run(["--list"], env=env_for(fake_home),
                            cwd=ev).stdout)
    assert "eve" not in ids5


# Test 16: both devin markers present -> both targets written
def test_16_devin_dual_markers(run, env_for, fake_home, tmp_path, src_file):
    env = env_for(fake_home)
    appdata_dir = Path(env["APPDATA"]) / "devin"
    appdata_dir.mkdir(parents=True)
    (fake_home / ".config" / "devin").mkdir(parents=True)
    r = run(["--agent", "devin", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    both = [appdata_dir / "AGENTS.md",
            fake_home / ".config" / "devin" / "AGENTS.md"]
    for f in both:
        assert f.is_file(), f
        assert f.read_bytes().startswith(B)

    h2 = tmp_path / "h2"
    h2.mkdir()
    env2 = env_for(h2)
    (Path(env2["APPDATA"]) / "devin").mkdir(parents=True)
    r2 = run(["--agent", "devin", "--scope", "user", "--yes", "--source",
              str(src_file)], env=env2)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert (Path(env2["APPDATA"]) / "devin" / "AGENTS.md").is_file()
    assert not (h2 / ".config" / "devin" / "AGENTS.md").exists()
