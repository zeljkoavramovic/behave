"""Roster invariants: FAMILY_IDS derivation from TIER1_ORDER.

The derivation makes the common drift direction impossible (a new
roster agent joins the family automatically); these tests pin the
exception set and the exact membership so the OTHER drift direction
(a non-family agent silently becoming family) fails in CI, not in a
user's project.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

NON_FAMILY = {"claude-code", "gemini-cli", "github-copilot", "openclaw",
              "tabnine-cli", "trae", "trae-cn"}

SNAPSHOT_FAMILY = [
    "codex", "opencode", "devin", "cursor", "pi", "omp", "roo", "augment",
    "kilo", "droid", "deepagents", "cline", "crush", "amp", "goose", "zed",
    "openhands", "warp", "junie", "posit-assistant", "zcode",
    "kimi-code-cli", "qwen-code", "antigravity", "kiro-cli", "qoder",
    "grok", "mistral-vibe", "rovodev", "bob", "cortex", "antigravity-cli",
    "xum", "hermes-agent", "aider-desk", "forgecode", "command-code",
    "qoder-cn", "codewhale", "jcode", "codebuff", "kimchi", "pochi",
    "reasonix", "deepseek-harness",
]


def _roster():
    out = subprocess.run(
        [sys.executable, "-c",
         "import json, install as I\n"
         "print(json.dumps({'family': I.FAMILY_IDS,\n"
         "                  'tier1': I.TIER1_ORDER,\n"
         "                  'all': I.ALL_IDS}))"],
        cwd=str(REPO), capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_family_ids_derived_from_tier1_order():
    r = _roster()
    assert r["family"] == [a for a in r["tier1"] if a not in NON_FAMILY]


def test_family_ids_snapshot():
    r = _roster()
    assert r["family"] == SNAPSHOT_FAMILY


def test_non_family_disjoint_and_complete():
    r = _roster()
    assert set(r["tier1"]) - set(r["family"]) == NON_FAMILY
    assert set(r["family"]) | NON_FAMILY == set(r["tier1"])
    assert set(r["all"]) == set(r["tier1"])


def _run_snippet(snippet, env):
    return subprocess.run([sys.executable, "-c", snippet], cwd=str(REPO),
                          env=env, capture_output=True, text=True,
                          timeout=60)


def test_user_targets_cover_roster(env_for, fake_home):
    out = _run_snippet(
        "import json, install as I\n"
        "print(json.dumps(sorted(I._USER_TARGETS)))",
        env_for(fake_home))
    assert out.returncode == 0, out.stderr
    table_ids = set(json.loads(out.stdout))
    all_ids = set(_roster()["all"])
    assert table_ids == all_ids - {"claude-code"}


def test_user_targets_rows_wellformed(env_for, fake_home):
    out = _run_snippet(
        "import json, install as I\n"
        "rows = []\n"
        "for aid, build in sorted(I._USER_TARGETS.items()):\n"
        "    for t in build():\n"
        "        rows.append([aid, str(t[0]), t[1], t[2], t[3]])\n"
        "print(json.dumps(rows))",
        env_for(fake_home))
    assert out.returncode == 0, out.stderr
    for aid, path, mode, drop_agent, ags in json.loads(out.stdout):
        assert aid in ags, (aid, ags)
        assert mode in ("inline", "drop"), mode
        assert mode != "drop" or drop_agent == aid, (aid, drop_agent)
        assert path, aid
