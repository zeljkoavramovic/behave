"""Plan section 9, tests 13-16: targets and detection."""

import re
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


# Test 15: detection: fake HOME markers, env override, multi-marker
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
    # the known-id count must agree with the ids actually listed
    # (derived from the run's own output - never a stale literal)
    m = re.search(r"All known ids \((\d+)\):\n\s+(.+)", r.stdout)
    assert m, r.stdout
    assert int(m.group(1)) == len(m.group(2).split(", "))

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


# Phase 3.1 (goose): the new APPDATA marker detects a Windows-style
# goose install (Block/goose under %APPDATA%, pointed into the fake home)
def test_goose_appdata_marker_detected(run, env_for, fake_home):
    env = env_for(fake_home)
    (Path(env["APPDATA"]) / "Block" / "goose").mkdir(parents=True)
    r = run(["--list"], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "goose" in detected_ids(r.stdout)


# Phase 3.1 (zed): both config markers present (devin precedent) ->
# user install writes BOTH AGENTS.md files; --remove cleans both
def test_zed_dual_config_dirs(run, env_for, fake_home, src_file):
    env = env_for(fake_home)
    appdata_dir = Path(env["APPDATA"]) / "Zed"
    appdata_dir.mkdir(parents=True)
    (fake_home / ".config" / "zed").mkdir(parents=True)
    r = run(["--agent", "zed", "--scope", "user", "--yes", "--source",
             str(src_file)], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    both = [appdata_dir / "AGENTS.md",
            fake_home / ".config" / "zed" / "AGENTS.md"]
    for f in both:
        assert f.is_file(), f
        assert f.read_bytes().startswith(B)
    r2 = run(["--remove", "--agent", "zed", "--scope", "user", "--yes"],
             env=env)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    for f in both:
        assert not f.exists()


# Phase 8 (qwen-code): the ~/.qwen marker detects qwen-code
def test_qwen_code_detection(run, env_for, fake_home):
    (fake_home / ".qwen").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "qwen-code" in detected_ids(r.stdout)


# Phase 8 (trae): the ~/.trae marker detects trae
def test_trae_detection(run, env_for, fake_home):
    (fake_home / ".trae").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "trae" in detected_ids(r.stdout)


# Phase 8 (antigravity): the ~/.gemini/antigravity marker detects
# antigravity (the antigravity-cli sibling marker stays tier 3)
def test_antigravity_detection(run, env_for, fake_home):
    (fake_home / ".gemini" / "antigravity").mkdir(parents=True)
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    ids = detected_ids(r.stdout)
    assert "antigravity" in ids
    assert "antigravity-cli" not in ids


# Phase 8 (kiro-cli): the ~/.kiro marker detects kiro-cli (shared by
# the Kiro IDE and Kiro CLI - the marker means "a Kiro surface")
def test_kiro_cli_detection(run, env_for, fake_home):
    (fake_home / ".kiro").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "kiro-cli" in detected_ids(r.stdout)


# Phase 8 (qoder): the ~/.qoder marker detects qoder (the qoder-cn
# sibling entry needs its own ~/.qoder-cn marker)
def test_qoder_detection(run, env_for, fake_home):
    (fake_home / ".qoder").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    ids = detected_ids(r.stdout)
    assert "qoder" in ids
    assert "qoder-cn" not in ids


# Phase 8 (grok): the ~/.grok marker detects grok (Grok Build; GROK_HOME
# overrides the whole dir per the registry env field)
def test_grok_detection(run, env_for, fake_home):
    (fake_home / ".grok").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "grok" in detected_ids(r.stdout)


# Phase 8 batch 2 (mistral-vibe): the ~/.vibe marker detects
# mistral-vibe (VIBE_HOME overrides per the registry env field)
def test_mistral_vibe_detection(run, env_for, fake_home):
    (fake_home / ".vibe").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "mistral-vibe" in detected_ids(r.stdout)


# Phase 8 batch 2 (rovodev): the ~/.rovodev marker detects rovodev
# (user AGENTS.md memory, applies to all CLI sessions)
def test_rovodev_detection(run, env_for, fake_home):
    (fake_home / ".rovodev").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "rovodev" in detected_ids(r.stdout)


# Phase 8 batch 2 (bob): the ~/.bob marker detects bob (IBM Bob IDE;
# user rules at ~/.bob/rules apply across all projects)
def test_bob_detection(run, env_for, fake_home):
    (fake_home / ".bob").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "bob" in detected_ids(r.stdout)


# Phase 8 batch 2 (trae-cn): the ~/.trae-cn marker detects trae-cn
# (the intl ~/.trae marker stays a separate agent)
def test_trae_cn_detection(run, env_for, fake_home):
    (fake_home / ".trae-cn").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    ids = detected_ids(r.stdout)
    assert "trae-cn" in ids
    assert "trae" not in ids


# Phase 8 batch 2 (cortex): the ~/.snowflake/cortex marker detects
# cortex (CoCo config root shared by CLI and Desktop)
def test_cortex_detection(run, env_for, fake_home):
    (fake_home / ".snowflake" / "cortex").mkdir(parents=True)
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "cortex" in detected_ids(r.stdout)


# Phase 8 batch 2 (antigravity-cli): the ~/.gemini/antigravity-cli
# marker detects antigravity-cli (the ~/.gemini root also lights up
# gemini-cli - its marker; the antigravity sibling dir stays absent)
def test_antigravity_cli_detection(run, env_for, fake_home):
    (fake_home / ".gemini" / "antigravity-cli").mkdir(parents=True)
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    ids = detected_ids(r.stdout)
    assert "antigravity-cli" in ids
    assert "antigravity" not in ids


# Phase 9 (xum): the ~/.xum marker detects xum; the legacy ~/.mux
# marker (vendor rename cmux -> mux -> xum; xum auto-migrates ~/.mux
# on startup) detects it too - "mux" is no longer a known id
def test_xum_detection(run, env_for, fake_home):
    (fake_home / ".xum").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "xum" in detected_ids(r.stdout)


def test_xum_legacy_mux_marker_detection(run, env_for, fake_home):
    (fake_home / ".mux").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    ids = detected_ids(r.stdout)
    assert "xum" in ids
    assert "mux" not in ids


# Phase 9 (hermes-agent): the ~/.hermes marker detects hermes-agent
# (HERMES_HOME overrides the whole dir per the registry env field)
def test_hermes_agent_detection(run, env_for, fake_home):
    (fake_home / ".hermes").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "hermes-agent" in detected_ids(r.stdout)


# Phase 9 (aider-desk): the ~/.aider-desk marker detects aider-desk
def test_aider_desk_detection(run, env_for, fake_home):
    (fake_home / ".aider-desk").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "aider-desk" in detected_ids(r.stdout)


# Phase 9 (forgecode): the ~/.forge marker detects forgecode (legacy
# ~/forge is presence-only, never a marker)
def test_forgecode_detection(run, env_for, fake_home):
    (fake_home / ".forge").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "forgecode" in detected_ids(r.stdout)


# Phase 9 (command-code): the ~/.commandcode marker detects command-code
def test_command_code_detection(run, env_for, fake_home):
    (fake_home / ".commandcode").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "command-code" in detected_ids(r.stdout)


# Phase 9 (qoder-cn): the ~/.qoder-cn marker detects qoder-cn (the
# intl ~/.qoder marker stays a separate agent)
def test_qoder_cn_detection(run, env_for, fake_home):
    (fake_home / ".qoder-cn").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    ids = detected_ids(r.stdout)
    assert "qoder-cn" in ids
    assert "qoder" not in ids


# Phase 9 (tabnine-cli): the ~/.tabnine marker detects tabnine-cli
def test_tabnine_cli_detection(run, env_for, fake_home):
    (fake_home / ".tabnine").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "tabnine-cli" in detected_ids(r.stdout)


# Phase 10 (codewhale): the ~/.codewhale marker detects codewhale
def test_codewhale_detection(run, env_for, fake_home):
    (fake_home / ".codewhale").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "codewhale" in detected_ids(r.stdout)


# Phase 10 (jcode): the ~/.jcode marker detects jcode
def test_jcode_detection(run, env_for, fake_home):
    (fake_home / ".jcode").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "jcode" in detected_ids(r.stdout)


# Phase 10 (codebuff): the ~/.config/manicode marker (legacy vendor
# dir name) detects codebuff - x-marker like opencode/crush
def test_codebuff_detection(run, env_for, fake_home):
    (fake_home / ".config" / "manicode").mkdir(parents=True)
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "codebuff" in detected_ids(r.stdout)


# Phase 8 batch 5 (kimchi): the ~/.config/kimchi marker detects kimchi
# ("h" marker - kimchi hardcodes homedir()/.config/kimchi, so the home
# base is correct cross-platform and XDG/APPDATA never apply)
def test_kimchi_detection(run, env_for, fake_home):
    (fake_home / ".config" / "kimchi").mkdir(parents=True)
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "kimchi" in detected_ids(r.stdout)


# Phase 8 batch 5 (pochi): the ~/.pochi marker detects pochi
# (user-global rules live in README.pochi.md inside it)
def test_pochi_detection(run, env_for, fake_home):
    (fake_home / ".pochi").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "pochi" in detected_ids(r.stdout)


# Phase 8 batch 5 (reasonix): the ~/.reasonix marker detects reasonix
# (Unix home; REASONIX_HOME overrides the whole dir per the env field)
def test_reasonix_detection(run, env_for, fake_home):
    (fake_home / ".reasonix").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "reasonix" in detected_ids(r.stdout)


# Phase 8 batch 5 (reasonix): the %APPDATA%\reasonix marker detects
# reasonix (Windows home - devin/goose APPDATA marker precedent, the
# batch-5 Windows marker fix)
def test_reasonix_appdata_marker_detected(run, env_for, fake_home):
    env = env_for(fake_home)
    (Path(env["APPDATA"]) / "reasonix").mkdir(parents=True)
    r = run(["--list"], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "reasonix" in detected_ids(r.stdout)


# Phase 8 batch 6 (deepseek-harness): the ~/.dsh marker detects
# deepseek-harness (DSH home; sessions/credentials live under it)
def test_deepseek_harness_detection(run, env_for, fake_home):
    (fake_home / ".dsh").mkdir()
    r = run(["--list"], env=env_for(fake_home))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "deepseek-harness" in detected_ids(r.stdout)


# Phase 8 batch 6 (deepseek-harness): DSH_HOME relocates the whole
# home per the registry env field (detection override only)
def test_deepseek_harness_dsh_home_env_detected(run, env_for, fake_home,
                                                tmp_path):
    custom = tmp_path / "dshhome"
    (custom / ".dsh").mkdir(parents=True)
    env = env_for(fake_home)
    env["DSH_HOME"] = str(custom)
    r = run(["--list"], env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "deepseek-harness" in detected_ids(r.stdout)
