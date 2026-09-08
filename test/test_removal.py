"""Plan section 9, tests 9-12: removal semantics."""

import json
import os
from pathlib import Path

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
    r_g = run(["--agent", "gemini-cli,cursor,github-copilot", "--scope",
               "project", "--project-dir", str(proj), "--yes", "--source",
               str(src_file)], env=env)
    assert r_g.returncode == 0, r_g.stdout + r_g.stderr
    # cursor is family now; the project has a Claude file, so the shared
    # AGENTS.md path is skipped (note) and no .cursor drop is written
    assert "Claude file" in r_g.stdout
    assert not (proj / ".cursor" / "rules" / "behave.mdc").exists()
    assert not (proj / "AGENTS.md").exists()

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
    assert (proj2 / "AGENTS.md").is_file()
    # legacy cleanup: a marker-bearing .cursor/rules/behave.mdc dropped by
    # an older installer must still be found and deleted
    legacy = proj2 / ".cursor" / "rules" / "behave.mdc"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(MARKER + b"# legacy cursor rules\n")
    r2 = run(["--remove", "--agent", "cursor", "--scope", "project",
              "--project-dir", str(proj2), "--yes"], env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert not legacy.exists()
    assert not (proj2 / "AGENTS.md").exists()
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
    assert "codex,opencode,pi,omp,devin,cursor" in r2.stdout
    assert not (proj / "AGENTS.md").exists()

    run(["--agent", "codex,opencode,pi,devin", "--scope", "project",
         "--project-dir", str(proj), "--yes", "--source", str(src_file)],
        env=env)
    r3 = run(["--remove", "--project-dir", str(proj), "--yes", "--json"],
             env=env)
    payload = json.loads(r3.stdout)
    agents = [t["agent"] for t in payload["targets"]]
    agents_list = "codex,opencode,pi,omp,devin,cursor,roo,augment,kilo," \
                  "droid,deepagents,cline,crush,amp,goose,zed,openhands"
    assert agents_list in agents


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


# Phase 3.1 (roo): --remove round-trip cleans the ~/.roo/rules drop
def test_roo_user_remove_round_trip(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "roo", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    drop = fake_home / ".roo" / "rules" / "behave.md"
    assert drop.is_file()
    r2 = run(["--remove", "--agent", "roo", "--scope", "user", "--yes"],
             env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert not drop.exists()


# Phase 3.1 (augment): --remove round-trip cleans the ~/.augment/rules drop
def test_augment_user_remove_round_trip(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "augment", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    drop = fake_home / ".augment" / "rules" / "behave.md"
    assert drop.is_file()
    r2 = run(["--remove", "--agent", "augment", "--scope", "user",
              "--yes"], env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert not drop.exists()


# Phase 3.1 (kilo): --remove round-trip cleans the ~/.kilocode/rules drop
def test_kilo_user_remove_round_trip(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "kilo", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    drop = fake_home / ".kilocode" / "rules" / "behave.md"
    assert drop.is_file()
    r2 = run(["--remove", "--agent", "kilo", "--scope", "user", "--yes"],
             env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert not drop.exists()


# Phase 3.1 (droid): --remove round-trip cleans ~/.factory/AGENTS.md
def test_droid_user_remove_round_trip(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "droid", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    target = fake_home / ".factory" / "AGENTS.md"
    assert target.is_file()
    r2 = run(["--remove", "--agent", "droid", "--scope", "user", "--yes"],
             env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert not target.exists()


# Phase 3.1 (deepagents): --remove round-trip cleans
# ~/.deepagents/agent/AGENTS.md
def test_deepagents_user_remove_round_trip(run, env_for, fake_home,
                                           src_file):
    env = env_for(fake_home)
    r = run(["--agent", "deepagents", "--scope", "user", "--yes",
             "--source", str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    target = fake_home / ".deepagents" / "agent" / "AGENTS.md"
    assert target.is_file()
    r2 = run(["--remove", "--agent", "deepagents", "--scope", "user",
              "--yes"], env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert not target.exists()


# Phase 3.1 (cline): --remove round-trip cleans the ~/.cline/rules drop
def test_cline_user_remove_round_trip(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "cline", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    drop = fake_home / ".cline" / "rules" / "behave.md"
    assert drop.is_file()
    r2 = run(["--remove", "--agent", "cline", "--scope", "user", "--yes"],
             env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert not drop.exists()


# Phase 3.1 (crush): --remove round-trip strips the block from
# <xdg>/crush/CRUSH.md and deletes the file when nothing remains
def test_crush_user_remove_round_trip(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "crush", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    target = fake_home / ".config" / "crush" / "CRUSH.md"
    assert target.is_file()
    r2 = run(["--remove", "--agent", "crush", "--scope", "user", "--yes"],
             env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert not target.exists()


# Phase 3.1 (amp): --remove round-trip cleans ~/.config/amp/AGENTS.md
def test_amp_user_remove_round_trip(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "amp", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    target = fake_home / ".config" / "amp" / "AGENTS.md"
    assert target.is_file()
    r2 = run(["--remove", "--agent", "amp", "--scope", "user", "--yes"],
             env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert not target.exists()


# Phase 3.1 (goose): --remove round-trip cleans the goose config dir's
# AGENTS.md (appdata-based on Windows, XDG under the fake home elsewhere)
def test_goose_user_remove_round_trip(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "goose", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    if os.name == "nt":
        target = Path(env["APPDATA"]) / "Block" / "goose" / "AGENTS.md"
    else:
        target = fake_home / ".config" / "goose" / "AGENTS.md"
    assert target.is_file()
    r2 = run(["--remove", "--agent", "goose", "--scope", "user", "--yes"],
             env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert not target.exists()


# Phase 3.1 (zed): --remove round-trip cleans the default Zed config
# dir's AGENTS.md (the every-dir case is covered by the dual-marker test
# in test_targets_detection.py)
def test_zed_user_remove_round_trip(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "zed", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    if os.name == "nt":
        target = Path(env["APPDATA"]) / "Zed" / "AGENTS.md"
    else:
        target = fake_home / ".config" / "zed" / "AGENTS.md"
    assert target.is_file()
    r2 = run(["--remove", "--agent", "zed", "--scope", "user", "--yes"],
             env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert not target.exists()


# Phase 3.1 (openhands): --remove round-trip cleans the ~/.agents/skills
# drop
def test_openhands_user_remove_round_trip(run, env_for, fake_home,
                                          src_file):
    env = env_for(fake_home)
    r = run(["--agent", "openhands", "--scope", "user", "--yes",
             "--source", str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    drop = fake_home / ".agents" / "skills" / "behave.md"
    assert drop.is_file()
    r2 = run(["--remove", "--agent", "openhands", "--scope", "user",
              "--yes"], env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert not drop.exists()
