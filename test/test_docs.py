"""Docs consistency: README.md and index.html must agree with install.py.

The agent count is DERIVED in install.py (TIER1_ORDER) but stated as a
literal in README.md and index.html - a parallel literal list went
stale before (the 51 -> 52 refreshes in TODO-LEFT).  These tests fail
when a roster change is not reflected in the docs, in either direction:
a new agent without a docs refresh, and a docs count edit without a
roster change.
"""

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _roster():
    out = subprocess.run(
        [sys.executable, "-c",
         "import json, install as I\n"
         "print(json.dumps({'tier1': I.TIER1_ORDER,\n"
         "                  'display': I.DISPLAY}))"],
        cwd=str(REPO), capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _readme():
    return (REPO / "README.md").read_text(encoding="utf-8")


def _index_html():
    return (REPO / "index.html").read_text(encoding="utf-8")


def _readme_roster(readme):
    """Returns (stated_count, [display names]) from the installer
    paragraph: the '**Supported agents list (N):**' heading plus the
    comma-separated roster paragraph that follows it."""
    m = re.search(r"Supported agents list \((\d+)\):", readme)
    assert m, "README agent-count heading ('Supported agents list (N):') not found"
    d = re.search(r"Supported agents list \(\d+\):\*\*\s+(.+?)\n\s*\n",
                  readme, re.DOTALL)
    assert d, "README roster paragraph not found"
    tokens = []
    for tok in d.group(1).split(","):
        tok = tok.strip()
        if tok.startswith("and "):
            tok = tok[len("and "):]
        tokens.append(tok)
    return int(m.group(1)), tokens


def test_readme_count_matches_roster():
    stated, _ = _readme_roster(_readme())
    assert stated == len(_roster()["tier1"])


def test_readme_names_match_display_exactly():
    display = _roster()["display"]
    stated, tokens = _readme_roster(_readme())
    assert len(tokens) == stated, (
        "README names %d agents but states %d" % (len(tokens), stated))
    assert sorted(tokens) == sorted(display.values()), (
        "README roster and install.py DISPLAY disagree:\n"
        "README only: %s\ninstall.py only: %s"
        % (sorted(set(tokens) - set(display.values())),
           sorted(set(display.values()) - set(tokens))))


def test_index_html_counts_match_roster():
    n = len(_roster()["tier1"])
    html = _index_html()
    counts = (
        [int(x) for x in re.findall(r"(\d+) AI coding agents", html)]
        + [int(x) for x in re.findall(r"supports (\d+) agents natively", html)])
    assert counts, "index.html states no agent count anywhere"
    bad = [(c, c != n) for c in counts]
    assert all(c == n for c in counts), (
        "index.html counts %s disagree with TIER1_ORDER (%d)"
        % (bad, n))
