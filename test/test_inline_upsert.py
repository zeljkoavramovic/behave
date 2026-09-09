"""Plan section 9, tests 1-6: inline upsert (the risk center)."""

import json
import os
from pathlib import Path

B = b"<!-- BEGIN behave - installed by install.py; --remove uninstalls -->\n"
E = b"<!-- END behave -->\n"


def codex_args(src, extra=()):
    return ["--agent", "codex", "--scope", "user", "--yes",
            "--source", str(src)] + list(extra)


def target_file(fake_home):
    return fake_home / ".codex" / "AGENTS.md"


# Test 1: create new file (did not exist) -> block + trailing newline
def test_1_create_new_file(run, env_for, fake_home, src_file):
    r = run(codex_args(src_file), env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    data = target_file(fake_home).read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.endswith(E)
    assert data.count(b"<!-- BEGIN behave ") == 1


# Test 2: prepend to existing file without trailing newline -> old content intact
def test_2_prepend_without_trailing_newline(run, env_for, fake_home, src_file):
    target = target_file(fake_home)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"original user notes")
    r = run(codex_args(src_file), env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    data = target.read_bytes()
    assert data.startswith(B)
    assert data.count(b"<!-- BEGIN behave ") == 1
    assert b"original user notes" in data
    # plan 4.1 step 4: a trailing newline is added when the file lacked one
    assert data.endswith(b"original user notes\n")


# Test 3: idempotency: run twice -> identical output, single block
def test_3_double_run_idempotent(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    run(codex_args(src_file), env=env)
    first = target_file(fake_home).read_bytes()
    r = run(codex_args(src_file), env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    second = target_file(fake_home).read_bytes()
    assert first == second
    assert second.count(b"<!-- BEGIN behave ") == 1


# Test 4: upgrade: old block with different content -> replaced, rest intact
def test_4_upgrade_replaces_old_block(run, env_for, fake_home, tmp_path,
                                      src_file):
    target = target_file(fake_home)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"user text before\n")
    src_a = tmp_path / "a.md"
    src_a.write_bytes(b"# SOURCE A\naaa content\n")
    src_b = tmp_path / "b.md"
    src_b.write_bytes(b"# SOURCE B\nbbb content\n")
    env = env_for(fake_home)
    r1 = run(codex_args(src_a), env=env)
    assert r1.returncode == 0, r1.stdout + r1.stderr
    r2 = run(codex_args(src_b), env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    data = target.read_bytes()
    assert data.count(b"<!-- BEGIN behave ") == 1
    assert b"# SOURCE B" in data
    assert b"# SOURCE A" not in data
    assert b"user text before\n" in data


# Test 5: unrelated `<!-- BEGIN other-id ... -->` blocks untouched
def test_5_foreign_block_untouched(run, env_for, fake_home, src_file):
    foreign = (b"<!-- BEGIN other-id - installed by install.py; "
               b"--remove uninstalls -->\nFOREIGN BODY\n"
               b"<!-- END other-id -->\n")
    target = target_file(fake_home)
    target.parent.mkdir(parents=True)
    target.write_bytes(foreign + b"user tail\n")
    r = run(codex_args(src_file), env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    data = target.read_bytes()
    assert data.startswith(B)
    assert foreign in data
    assert b"user tail\n" in data
    assert data.count(b"<!-- BEGIN behave ") == 1
    assert data.count(b"<!-- BEGIN other-id ") == 1


# Test 6: size check: upserted content > 30 KiB -> warning present, written
def test_6_size_warning(run, env_for, fake_home, tmp_path):
    big = tmp_path / "big.md"
    big.write_bytes(b"# BIG\n" + b"x" * 32000 + b"\n")
    env = env_for(fake_home)
    r = run(codex_args(big), env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "30 KiB" in (r.stdout + r.stderr)
    data = target_file(fake_home).read_bytes()
    assert len(data) > 30720
    assert b"x" * 1000 in data
    home2 = tmp_path / "h2"
    home2.mkdir()
    r2 = run(codex_args(big, ["--json"]), env=env_for(home2))
    assert r2.returncode == 0, r2.stdout + r2.stderr
    payload = json.loads(r2.stdout)
    assert payload["targets"][0]["warning"]


# Phase 3.1 (roo): project scope with only roo selected rides the shared
# ./AGENTS.md family block; the agent list reports the whole family
def test_roo_project_shared_agents_md(run, env_for, fake_home, proj,
                                      src_file):
    env = env_for(fake_home)
    r = run(["--agent", "roo", "--scope", "project", "--project-dir",
             str(proj), "--yes", "--json", "--source", str(src_file)],
            env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    served = payload["targets"][0]["agent"].split(",")
    assert "roo" in served
    assert "codex" in served  # the shared block, not a roo-only target
    data = (proj / "AGENTS.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (augment): project scope with only augment selected rides the
# shared ./AGENTS.md family block
def test_augment_project_shared_agents_md(run, env_for, fake_home, proj,
                                          src_file):
    env = env_for(fake_home)
    r = run(["--agent", "augment", "--scope", "project", "--project-dir",
             str(proj), "--yes", "--json", "--source", str(src_file)],
            env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    served = payload["targets"][0]["agent"].split(",")
    assert "augment" in served
    assert "codex" in served  # the shared block, not an augment-only target
    data = (proj / "AGENTS.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (kilo): project scope with only kilo selected rides the
# shared ./AGENTS.md family block
def test_kilo_project_shared_agents_md(run, env_for, fake_home, proj,
                                       src_file):
    env = env_for(fake_home)
    r = run(["--agent", "kilo", "--scope", "project", "--project-dir",
             str(proj), "--yes", "--json", "--source", str(src_file)],
            env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    served = payload["targets"][0]["agent"].split(",")
    assert "kilo" in served
    assert "codex" in served  # the shared block, not a kilo-only target
    data = (proj / "AGENTS.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (droid): user-scope inline block at the top of
# ~/.factory/AGENTS.md
def test_droid_user_inline(run, env_for, fake_home, src_file):
    r = run(["--agent", "droid", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    data = (fake_home / ".factory" / "AGENTS.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.endswith(E)
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (droid): project scope with only droid selected rides the
# shared ./AGENTS.md family block
def test_droid_project_shared_agents_md(run, env_for, fake_home, proj,
                                        src_file):
    env = env_for(fake_home)
    r = run(["--agent", "droid", "--scope", "project", "--project-dir",
             str(proj), "--yes", "--json", "--source", str(src_file)],
            env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    served = payload["targets"][0]["agent"].split(",")
    assert "droid" in served
    assert "codex" in served  # the shared block, not a droid-only target
    data = (proj / "AGENTS.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (deepagents): user-scope inline block at the top of
# ~/.deepagents/agent/AGENTS.md; parent dirs are created when missing
def test_deepagents_user_inline(run, env_for, fake_home, src_file):
    r = run(["--agent", "deepagents", "--scope", "user", "--yes",
             "--source", str(src_file)], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    data = (fake_home / ".deepagents" / "agent" / "AGENTS.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.endswith(E)
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (deepagents): project scope with only deepagents selected
# rides the shared ./AGENTS.md family block
def test_deepagents_project_shared_agents_md(run, env_for, fake_home, proj,
                                             src_file):
    env = env_for(fake_home)
    r = run(["--agent", "deepagents", "--scope", "project", "--project-dir",
             str(proj), "--yes", "--json", "--source", str(src_file)],
            env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    served = payload["targets"][0]["agent"].split(",")
    assert "deepagents" in served
    assert "codex" in served  # the shared block, not a deepagents-only one
    data = (proj / "AGENTS.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (cline): project scope with only cline selected rides the
# shared ./AGENTS.md family block
def test_cline_project_shared_agents_md(run, env_for, fake_home, proj,
                                        src_file):
    env = env_for(fake_home)
    r = run(["--agent", "cline", "--scope", "project", "--project-dir",
             str(proj), "--yes", "--json", "--source", str(src_file)],
            env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    served = payload["targets"][0]["agent"].split(",")
    assert "cline" in served
    assert "codex" in served  # the shared block, not a cline-only one
    data = (proj / "AGENTS.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (crush): user-scope inline block at the top of
# <xdg>/crush/CRUSH.md
def test_crush_user_inline(run, env_for, fake_home, src_file):
    r = run(["--agent", "crush", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    data = (fake_home / ".config" / "crush" / "CRUSH.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.endswith(E)
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (crush): CRUSH.md is the user's own instructions file - a
# pre-existing file keeps its content below the newly prepended block
def test_crush_user_inline_preserves_existing(run, env_for, fake_home,
                                              src_file):
    target = fake_home / ".config" / "crush" / "CRUSH.md"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"MY NOTES\n")
    r = run(["--agent", "crush", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    data = target.read_bytes()
    assert data.startswith(B)
    assert b"MY NOTES" in data
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (crush): project scope with only crush selected rides the
# shared ./AGENTS.md family block
def test_crush_project_shared_agents_md(run, env_for, fake_home, proj,
                                        src_file):
    env = env_for(fake_home)
    r = run(["--agent", "crush", "--scope", "project", "--project-dir",
             str(proj), "--yes", "--json", "--source", str(src_file)],
            env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    served = payload["targets"][0]["agent"].split(",")
    assert "crush" in served
    assert "codex" in served  # the shared block, not a crush-only one
    data = (proj / "AGENTS.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (amp): user-scope inline block at the top of
# ~/.config/amp/AGENTS.md (amp hardcodes $HOME/.config on every platform)
def test_amp_user_inline(run, env_for, fake_home, src_file):
    r = run(["--agent", "amp", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    data = (fake_home / ".config" / "amp" / "AGENTS.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.endswith(E)
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (amp): a pre-existing ~/.config/amp/AGENTS.md keeps its
# content below the newly prepended block
def test_amp_user_inline_preserves_existing(run, env_for, fake_home,
                                            src_file):
    target = fake_home / ".config" / "amp" / "AGENTS.md"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"MY NOTES\n")
    r = run(["--agent", "amp", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    data = target.read_bytes()
    assert data.startswith(B)
    assert b"MY NOTES" in data
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (amp): project scope with only amp selected rides the shared
# ./AGENTS.md family block
def test_amp_project_shared_agents_md(run, env_for, fake_home, proj,
                                      src_file):
    env = env_for(fake_home)
    r = run(["--agent", "amp", "--scope", "project", "--project-dir",
             str(proj), "--yes", "--json", "--source", str(src_file)],
            env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    served = payload["targets"][0]["agent"].split(",")
    assert "amp" in served
    assert "codex" in served  # the shared block, not an amp-only one
    data = (proj / "AGENTS.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.count(b"<!-- BEGIN behave ") == 1


def goose_target(env, fake_home):
    # goose_config_dir(): %APPDATA%/Block/goose on Windows, XDG goose
    # elsewhere (conftest points APPDATA and HOME into the fake home)
    if os.name == "nt":
        return Path(env["APPDATA"]) / "Block" / "goose" / "AGENTS.md"
    return fake_home / ".config" / "goose" / "AGENTS.md"


# Phase 3.1 (goose): user-scope inline block at the top of the goose
# config dir's AGENTS.md
def test_goose_user_inline(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "goose", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    data = goose_target(env, fake_home).read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.endswith(E)
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (goose): project scope with only goose selected rides the
# shared ./AGENTS.md family block
def test_goose_project_shared_agents_md(run, env_for, fake_home, proj,
                                        src_file):
    env = env_for(fake_home)
    r = run(["--agent", "goose", "--scope", "project", "--project-dir",
             str(proj), "--yes", "--json", "--source", str(src_file)],
            env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    served = payload["targets"][0]["agent"].split(",")
    assert "goose" in served
    assert "codex" in served  # the shared block, not a goose-only one
    data = (proj / "AGENTS.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.count(b"<!-- BEGIN behave ") == 1


def zed_default_target(env, fake_home):
    # zed_dirs() fallback when no config dir exists yet: %APPDATA%/Zed on
    # Windows, ~/.config/zed elsewhere
    if os.name == "nt":
        return Path(env["APPDATA"]) / "Zed" / "AGENTS.md"
    return fake_home / ".config" / "zed" / "AGENTS.md"


# Phase 3.1 (zed): user-scope inline block at the top of the default Zed
# config dir's AGENTS.md
def test_zed_user_inline(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "zed", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    data = zed_default_target(env, fake_home).read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.endswith(E)
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (zed): project scope with only zed selected rides the shared
# ./AGENTS.md family block
def test_zed_project_shared_agents_md(run, env_for, fake_home, proj,
                                      src_file):
    env = env_for(fake_home)
    r = run(["--agent", "zed", "--scope", "project", "--project-dir",
             str(proj), "--yes", "--json", "--source", str(src_file)],
            env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    served = payload["targets"][0]["agent"].split(",")
    assert "zed" in served
    assert "codex" in served  # the shared block, not a zed-only one
    data = (proj / "AGENTS.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (openhands): project scope with only openhands selected rides
# the shared ./AGENTS.md family block
def test_openhands_project_shared_agents_md(run, env_for, fake_home, proj,
                                            src_file):
    env = env_for(fake_home)
    r = run(["--agent", "openhands", "--scope", "project", "--project-dir",
             str(proj), "--yes", "--json", "--source", str(src_file)],
            env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    served = payload["targets"][0]["agent"].split(",")
    assert "openhands" in served
    assert "codex" in served  # the shared block, not an openhands-only one
    data = (proj / "AGENTS.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (warp): user-scope inline block at the top of
# ~/.agents/AGENTS.md (warp's only registered global rulefile; shared
# with other cross-agent readers)
def test_warp_user_inline(run, env_for, fake_home, src_file):
    r = run(["--agent", "warp", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    data = (fake_home / ".agents" / "AGENTS.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.endswith(E)
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (warp): a pre-existing ~/.agents/AGENTS.md keeps its content
# below the newly prepended block
def test_warp_user_inline_preserves_existing(run, env_for, fake_home,
                                             src_file):
    target = fake_home / ".agents" / "AGENTS.md"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"MY NOTES\n")
    r = run(["--agent", "warp", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    data = target.read_bytes()
    assert data.startswith(B)
    assert b"MY NOTES" in data
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (warp): project scope with only warp selected rides the
# shared ./AGENTS.md family block
def test_warp_project_shared_agents_md(run, env_for, fake_home, proj,
                                       src_file):
    env = env_for(fake_home)
    r = run(["--agent", "warp", "--scope", "project", "--project-dir",
             str(proj), "--yes", "--json", "--source", str(src_file)],
            env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    served = payload["targets"][0]["agent"].split(",")
    assert "warp" in served
    assert "codex" in served  # the shared block, not a warp-only one
    data = (proj / "AGENTS.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (junie): user-scope inline block at the top of
# ~/.junie/AGENTS.md (documented for the Junie CLI)
def test_junie_user_inline(run, env_for, fake_home, src_file):
    r = run(["--agent", "junie", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    data = (fake_home / ".junie" / "AGENTS.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.endswith(E)
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (junie): a pre-existing ~/.junie/AGENTS.md keeps its content
# below the newly prepended block
def test_junie_user_inline_preserves_existing(run, env_for, fake_home,
                                              src_file):
    target = fake_home / ".junie" / "AGENTS.md"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"MY NOTES\n")
    r = run(["--agent", "junie", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    data = target.read_bytes()
    assert data.startswith(B)
    assert b"MY NOTES" in data
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (junie): project scope with only junie selected rides the
# shared ./AGENTS.md family block (.junie/AGENTS.md is exclusive in
# project scope and would suppress the root AGENTS.md - never written)
def test_junie_project_shared_agents_md(run, env_for, fake_home, proj,
                                        src_file):
    env = env_for(fake_home)
    r = run(["--agent", "junie", "--scope", "project", "--project-dir",
             str(proj), "--yes", "--json", "--source", str(src_file)],
            env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    served = payload["targets"][0]["agent"].split(",")
    assert "junie" in served
    assert "codex" in served  # the shared block, not a junie-only one
    data = (proj / "AGENTS.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.count(b"<!-- BEGIN behave ") == 1
    assert not (proj / ".junie" / "AGENTS.md").exists()


# Phase 3.1 (posit-assistant): user-scope inline block at the top of
# ~/.posit/assistant/AGENTS.md (Posit Assistant user memory)
def test_posit_assistant_user_inline(run, env_for, fake_home, src_file):
    r = run(["--agent", "posit-assistant", "--scope", "user", "--yes",
             "--source", str(src_file)], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    data = (fake_home / ".posit" / "assistant" / "AGENTS.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.endswith(E)
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (posit-assistant): a pre-existing ~/.posit/assistant/AGENTS.md
# keeps its content below the newly prepended block
def test_posit_assistant_user_inline_preserves_existing(run, env_for,
                                                         fake_home,
                                                         src_file):
    target = fake_home / ".posit" / "assistant" / "AGENTS.md"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"MY NOTES\n")
    r = run(["--agent", "posit-assistant", "--scope", "user", "--yes",
             "--source", str(src_file)], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    data = target.read_bytes()
    assert data.startswith(B)
    assert b"MY NOTES" in data
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (posit-assistant): project scope rides the shared ./AGENTS.md
# family block (legacy ~/.positai is never an install target)
def test_posit_assistant_project_shared_agents_md(run, env_for, fake_home,
                                                  proj, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "posit-assistant", "--scope", "project",
             "--project-dir", str(proj), "--yes", "--json", "--source",
             str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    served = payload["targets"][0]["agent"].split(",")
    assert "posit-assistant" in served
    assert "codex" in served  # the shared block, not a posit-only one
    data = (proj / "AGENTS.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (zcode): user-scope inline block at the top of
# ~/.zcode/AGENTS.md (read at task start, appended first)
def test_zcode_user_inline(run, env_for, fake_home, src_file):
    r = run(["--agent", "zcode", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    data = (fake_home / ".zcode" / "AGENTS.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.endswith(E)
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (zcode): a pre-existing ~/.zcode/AGENTS.md keeps its content
# below the newly prepended block
def test_zcode_user_inline_preserves_existing(run, env_for, fake_home,
                                              src_file):
    target = fake_home / ".zcode" / "AGENTS.md"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"MY NOTES\n")
    r = run(["--agent", "zcode", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    data = target.read_bytes()
    assert data.startswith(B)
    assert b"MY NOTES" in data
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (zcode): project scope rides the shared ./AGENTS.md family
# block (zcode also searches AGENTS.md up to the project root)
def test_zcode_project_shared_agents_md(run, env_for, fake_home, proj,
                                        src_file):
    env = env_for(fake_home)
    r = run(["--agent", "zcode", "--scope", "project", "--project-dir",
             str(proj), "--yes", "--json", "--source", str(src_file)],
            env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    served = payload["targets"][0]["agent"].split(",")
    assert "zcode" in served
    assert "codex" in served  # the shared block, not a zcode-only one
    data = (proj / "AGENTS.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (minimax-code): project scope rides the shared ./AGENTS.md
# family block (documented mcode CLI "configuration layers" default);
# user scope has no verified target - see test_interface.py
def test_minimax_code_project_shared_agents_md(run, env_for, fake_home,
                                               proj, src_file):
    env = env_for(fake_home)
    r = run(["--agent", "minimax-code", "--scope", "project",
             "--project-dir", str(proj), "--yes", "--json", "--source",
             str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    payload = json.loads(r.stdout)
    served = payload["targets"][0]["agent"].split(",")
    assert "minimax-code" in served
    assert "codex" in served  # the shared block, not a minimax-only one
    data = (proj / "AGENTS.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (openclaw): user-scope inline block at the top of
# ~/.openclaw/workspace/AGENTS.md (workspace bootstrap, every session)
def test_openclaw_user_inline(run, env_for, fake_home, src_file):
    r = run(["--agent", "openclaw", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    data = (fake_home / ".openclaw" / "workspace" / "AGENTS.md").read_bytes()
    assert data.startswith(B)
    assert b"# RULES\nrules body line\n" in data
    assert data.endswith(E)
    assert data.count(b"<!-- BEGIN behave ") == 1


# Phase 3.1 (openclaw): a pre-existing ~/.openclaw/workspace/AGENTS.md
# keeps its content below the newly prepended block
def test_openclaw_user_inline_preserves_existing(run, env_for, fake_home,
                                                 src_file):
    target = fake_home / ".openclaw" / "workspace" / "AGENTS.md"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"MY NOTES\n")
    r = run(["--agent", "openclaw", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    data = target.read_bytes()
    assert data.startswith(B)
    assert b"MY NOTES" in data
    assert data.count(b"<!-- BEGIN behave ") == 1
