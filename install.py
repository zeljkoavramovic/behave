# install.py - BEHAVE.md installer
# Copyright © 2026 Zeljko Avramovic
#
# Detection table derived from vercel-labs/skills
# https://github.com/vercel-labs/skills - Copyright (c) 2026 Vercel, Inc.
# Licensed under the MIT License; full text follows.
#
# MIT License
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
"""install.py - cross-platform BEHAVE.md installer (single file, stdlib only).

Installs one canonical rules file (BEHAVE.md) into AI coding agents:

  - inline mode: a marked block at the TOP of a memory file (AGENTS.md
    family, CLAUDE.md variants, GEMINI.md, copilot-instructions.md)
  - drop mode:   a whole rules file the installer owns, placed in a rules
    directory (Claude rules dirs, Cursor .mdc, Devin rules, Copilot
    instructions)
  - plain copy:  --copy-only writes BEHAVE.md and touches nothing else.

Idempotent (re-run = update), fully scriptable (any flags = headless),
--remove uninstalls.  Full specification: INSTALLER-PLAN.md.

Owner decisions applied (2026-09-07):
  D1  no versioning anywhere: plain BEGIN/END markers, no sha inside
      markers; re-run replaces any existing block regardless of content.
  D2  CANONICAL_URL below is the fetch fallback when the bundled
      BEHAVE.md is absent.
  D3  --copy-only does not require --yes; all other headless writes do.

Managed-block markers (block id defaults to "behave"):
  inline:  <!-- BEGIN {id} - installed by install.py; --remove uninstalls -->
           ... BEHAVE.md content verbatim ...
           <!-- END {id} -->
  drop:    <!-- installed by install.py ({id}); --remove deletes this file -->
"""

import argparse
import difflib
import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

CANONICAL_URL = (
    "https://raw.githubusercontent.com/zeljkoavramovic/behave/master/BEHAVE.md"
)

BOM = b"\xef\xbb\xbf"
SIZE_WARN_BYTES = 30 * 1024  # ~30 KiB soft cap; Codex caps AGENTS.md at 32 KiB

INLINE_CONSENT = (
    "the rules are inserted at the TOP, so everything you already have "
    "loads AFTER them and keeps more weight"
)
DROP_CONSENT = (
    "own file that loads alongside your CLAUDE.md at the same tier; "
    "delete the file (or run --remove) to uninstall"
)

# ---------------------------------------------------------------------------
# Agent detection table - all 77 entries (INSTALLER-PLAN section 5)
# ---------------------------------------------------------------------------
# Marker bases:
#   "h" home dir (agent root; env override replaces the whole agent dir)
#   "x" XDG config base ($XDG_CONFIG_HOME or ~/.config)
#   "a" %APPDATA%
#   "f" $FLATPAK_XDG_CONFIG_HOME
#   "c" current working directory (report-only signal)
#   "p" absolute path (as-is)
# flags: "cwd" (has cwd markers),
#        "content" (package.json content check), "never" (pseudo entry),
#        "deprecated" (report-only deprecation notice)
AGENTS: List[Dict[str, Any]] = [
    {"id": "aider-desk", "env": None, "markers": [("h", ".aider-desk")], "tier": 3, "flags": ()},
    {"id": "amp", "env": None, "markers": [("x", "amp")], "tier": 1, "flags": ()},
    {"id": "antigravity", "env": None, "markers": [("h", ".gemini/antigravity")], "tier": 1, "flags": ()},
    {"id": "antigravity-cli", "env": None, "markers": [("h", ".gemini/antigravity-cli")], "tier": 3, "flags": ()},
    {"id": "astrbot", "env": None, "markers": [("c", "data/skills"), ("h", ".astrbot")], "tier": 3, "flags": ("cwd",)},
    {"id": "autohand-code", "env": "AUTOHAND_HOME", "markers": [("h", ".autohand")], "tier": 3, "flags": ()},
    {"id": "augment", "env": None, "markers": [("h", ".augment")], "tier": 1, "flags": ()},
    {"id": "bob", "env": None, "markers": [("h", ".bob")], "tier": 3, "flags": ()},
    {"id": "claude-code", "env": "CLAUDE_CONFIG_DIR", "markers": [("h", ".claude")], "tier": 1, "flags": ()},
    {"id": "openclaw", "env": None, "markers": [("h", ".openclaw"), ("h", ".clawdbot"), ("h", ".moltbot")], "tier": 1, "flags": ()},
    {"id": "cline", "env": None, "markers": [("h", ".cline")], "tier": 1, "flags": ()},
    {"id": "codearts-agent", "env": None, "markers": [("h", ".codeartsdoer")], "tier": 3, "flags": ()},
    {"id": "codebuddy", "env": None, "markers": [("c", ".codebuddy"), ("h", ".codebuddy")], "tier": 3, "flags": ("cwd",)},
    {"id": "codemaker", "env": None, "markers": [("h", ".codemaker")], "tier": 3, "flags": ()},
    {"id": "codestudio", "env": None, "markers": [("h", ".codestudio")], "tier": 3, "flags": ()},
    {"id": "codex", "env": "CODEX_HOME", "markers": [("h", ".codex"), ("p", "/etc/codex")], "tier": 1, "flags": ()},
    {"id": "command-code", "env": None, "markers": [("h", ".commandcode")], "tier": 3, "flags": ()},
    {"id": "continue", "env": None, "markers": [("c", ".continue"), ("h", ".continue")], "tier": 3, "flags": ("cwd",)},
    {"id": "cortex", "env": None, "markers": [("h", ".snowflake/cortex")], "tier": 3, "flags": ()},
    {"id": "crush", "env": None, "markers": [("h", ".config/crush")], "tier": 1, "flags": ()},
    {"id": "cursor", "env": None, "markers": [("h", ".cursor")], "tier": 1, "flags": ()},
    {"id": "deepagents", "env": None, "markers": [("h", ".deepagents")], "tier": 1, "flags": ()},
    {"id": "devin", "env": None, "markers": [("x", "devin"), ("a", "devin")], "tier": 1, "flags": ()},
    {"id": "dexto", "env": None, "markers": [("h", ".dexto")], "tier": 3, "flags": ()},
    {"id": "droid", "env": None, "markers": [("h", ".factory")], "tier": 1, "flags": ()},
    {"id": "eve", "env": None, "markers": [], "tier": 3, "flags": ("content", "cwd")},
    {"id": "firebender", "env": None, "markers": [("h", ".firebender")], "tier": 3, "flags": ()},
    {"id": "forgecode", "env": None, "markers": [("h", ".forge")], "tier": 3, "flags": ()},
    {"id": "gemini-cli", "env": None, "markers": [("h", ".gemini")], "tier": 1, "flags": ()},
    {"id": "github-copilot", "env": None, "markers": [("h", ".copilot")], "tier": 1, "flags": ()},
    # goose: the ("a", "Block/goose") marker matches the install target -
    # Windows detection missed goose while it was XDG-only (goose stores
    # config under %APPDATA%\Block\goose there, not under ~/.config).
    {"id": "goose", "env": None, "markers": [("x", "goose"), ("a", "Block/goose")], "tier": 1, "flags": ()},
    {"id": "grok", "env": "GROK_HOME", "markers": [("h", ".grok")], "tier": 1, "flags": ()},
    {"id": "hermes-agent", "env": "HERMES_HOME", "markers": [("h", ".hermes")], "tier": 3, "flags": ()},
    {"id": "inference-sh", "env": None, "markers": [("h", ".inferencesh")], "tier": 3, "flags": ()},
    {"id": "jazz", "env": None, "markers": [("h", ".jazz"), ("c", ".jazz")], "tier": 3, "flags": ()},
    {"id": "junie", "env": None, "markers": [("h", ".junie")], "tier": 1, "flags": ()},
    {"id": "iflow-cli", "env": None, "markers": [("h", ".iflow")], "tier": 3, "flags": ()},
    {"id": "kilo", "env": None, "markers": [("h", ".kilocode")], "tier": 1, "flags": ()},
    {"id": "kimchi", "env": None, "markers": [("h", ".config/kimchi")], "tier": 3, "flags": ()},
    {"id": "kimi-code-cli", "env": None, "markers": [("h", ".kimi-code"), ("h", ".kimi")], "tier": 1, "flags": ()},
    {"id": "kiro-cli", "env": None, "markers": [("h", ".kiro")], "tier": 1, "flags": ()},
    {"id": "kode", "env": None, "markers": [("h", ".kode")], "tier": 3, "flags": ()},
    {"id": "lingma", "env": None, "markers": [("h", ".lingma")], "tier": 3, "flags": ()},
    {"id": "loaf", "env": None, "markers": [("h", ".loaf")], "tier": 3, "flags": ()},
    {"id": "mcpjam", "env": None, "markers": [("h", ".mcpjam")], "tier": 3, "flags": ()},
    {"id": "minimax-code", "env": None, "markers": [("h", ".minimax"), ("p", "/Applications/MiniMax Code.app")], "tier": 1, "flags": ()},
    {"id": "mistral-vibe", "env": "VIBE_HOME", "markers": [("h", ".vibe")], "tier": 3, "flags": ()},
    {"id": "moxby", "env": None, "markers": [("h", ".moxby")], "tier": 3, "flags": ()},
    {"id": "mux", "env": None, "markers": [("h", ".mux")], "tier": 3, "flags": ()},
    {"id": "omp", "env": None, "markers": [("h", ".omp/agent")], "tier": 1, "flags": ()},
    {"id": "opencode", "env": None, "markers": [("x", "opencode")], "tier": 1, "flags": ()},
    {"id": "openhands", "env": None, "markers": [("h", ".openhands")], "tier": 1, "flags": ()},
    {"id": "ona", "env": None, "markers": [("h", ".ona")], "tier": 2, "flags": ()},
    {"id": "pi", "env": None, "markers": [("h", ".pi/agent")], "tier": 1, "flags": ()},
    {"id": "posit-assistant", "env": None, "markers": [("h", ".posit/assistant"), ("h", ".positai")], "tier": 1, "flags": ()},
    {"id": "qoder", "env": None, "markers": [("h", ".qoder")], "tier": 1, "flags": ()},
    {"id": "qoder-cn", "env": None, "markers": [("h", ".qoder-cn")], "tier": 3, "flags": ()},
    {"id": "qwen-code", "env": None, "markers": [("h", ".qwen")], "tier": 1, "flags": ()},
    {"id": "replit", "env": None, "markers": [("c", ".replit")], "tier": 3, "flags": ("cwd",)},
    {"id": "reasonix", "env": None, "markers": [("h", ".reasonix")], "tier": 3, "flags": ()},
    {"id": "rovodev", "env": None, "markers": [("h", ".rovodev")], "tier": 3, "flags": ()},
    {"id": "roo", "env": None, "markers": [("h", ".roo")], "tier": 1, "flags": ()},
    {"id": "tabnine-cli", "env": None, "markers": [("h", ".tabnine")], "tier": 3, "flags": ()},
    {"id": "terramind", "env": None, "markers": [("h", ".terramind")], "tier": 3, "flags": ()},
    {"id": "tinycloud", "env": None, "markers": [("h", ".tinycloud")], "tier": 3, "flags": ()},
    {"id": "trae", "env": None, "markers": [("h", ".trae")], "tier": 1, "flags": ()},
    {"id": "trae-cn", "env": None, "markers": [("h", ".trae-cn")], "tier": 3, "flags": ()},
    {"id": "warp", "env": None, "markers": [("h", ".warp")], "tier": 1, "flags": ()},
    {"id": "windsurf", "env": None, "markers": [("h", ".codeium/windsurf")], "tier": 3, "flags": ("deprecated",)},
    {"id": "zed", "env": None, "markers": [("x", "zed"), ("a", "Zed"), ("f", "zed")], "tier": 1, "flags": ()},
    {"id": "zcode", "env": None, "markers": [("h", ".zcode"), ("p", "/Applications/ZCode.app")], "tier": 1, "flags": ()},
    {"id": "zencoder", "env": None, "markers": [("h", ".zencoder")], "tier": 3, "flags": ()},
    {"id": "zenflow", "env": None, "markers": [("h", ".zencoder")], "tier": 3, "flags": ()},
    {"id": "neovate", "env": None, "markers": [("h", ".neovate")], "tier": 3, "flags": ()},
    {"id": "pochi", "env": None, "markers": [("h", ".pochi")], "tier": 3, "flags": ()},
    {"id": "promptscript", "env": None, "markers": [("c", ".promptscript"), ("c", "promptscript.yaml")], "tier": 3, "flags": ("cwd",)},
    {"id": "adal", "env": None, "markers": [("h", ".adal")], "tier": 3, "flags": ()},
    {"id": "universal", "env": None, "markers": [], "tier": 3, "flags": ("never",)},
]

AGENT_BY_ID = dict((a["id"], a) for a in AGENTS)
ALL_IDS: List[str] = [a["id"] for a in AGENTS]

# Tier-1 install targets (INSTALLER-PLAN section 6); order = TUI menu.
TIER1_ORDER = [
    "claude-code", "codex", "opencode", "devin", "cursor",
    "gemini-cli", "github-copilot", "pi", "omp",
    "roo", "augment", "kilo", "droid", "deepagents", "cline", "crush",
    "amp", "goose", "zed", "openhands", "warp", "junie", "posit-assistant",
    "zcode", "minimax-code", "openclaw", "kimi-code-cli", "qwen-code",
    "trae", "antigravity", "kiro-cli", "qoder", "grok",
]
TIER1_SET = set(TIER1_ORDER)
# Every family member reads project-root AGENTS.md by default; project
# scope installs ONE shared ./AGENTS.md block for all of them.
FAMILY_IDS = ["codex", "opencode", "pi", "omp", "devin", "cursor",
              "roo", "augment", "kilo", "droid", "deepagents", "cline",
              "crush", "amp", "goose", "zed", "openhands", "warp",
              "junie", "posit-assistant", "zcode", "minimax-code",
              "kimi-code-cli", "qwen-code", "antigravity", "kiro-cli",
              "qoder", "grok"]
DISPLAY = {
    "claude-code": "Claude Code",
    "codex": "Codex",
    "opencode": "OpenCode",
    "pi": "Pi",
    "omp": "Oh My Pi",
    "devin": "Devin",
    "cursor": "Cursor",
    "gemini-cli": "Gemini CLI",
    "github-copilot": "GitHub Copilot",
    "roo": "Roo Code",
    "augment": "Augment Code",
    "kilo": "Kilo Code",
    "droid": "Droid",
    "deepagents": "Deep Agents",
    "cline": "Cline",
    "crush": "Crush",
    "amp": "Amp",
    "goose": "Goose",
    "zed": "Zed",
    "openhands": "OpenHands",
    "warp": "Warp",
    "junie": "Junie",
    "posit-assistant": "Posit Assistant",
    "zcode": "ZCode",
    "minimax-code": "MiniMax Code",
    "openclaw": "OpenClaw",
    "kimi-code-cli": "Kimi Code",
    "qwen-code": "Qwen Code",
    "trae": "Trae",
    "antigravity": "Antigravity",
    "kiro-cli": "Kiro",
    "qoder": "Qoder",
    "grok": "Grok Build",
}
# Drop-file frontmatter per agent (INSTALLER-PLAN section 4.2).
DROP_FRONTMATTER = {
    "augment": "",
    "claude-code": "",
    "cline": "",
    "cursor": "---\nalwaysApply: true\n---\n",
    "devin": "---\ntrigger: always_on\n---\n",
    "github-copilot": '---\napplyTo: "**"\n---\n',
    "kilo": "",
    "openhands": "",
    "roo": "",
    "trae": "---\nalwaysApply: true\n---\n",
    "kiro-cli": "",
    "qoder": "",
    "grok": "",
}

# ---------------------------------------------------------------------------
# Output helpers (ASCII-only console output everywhere)
# ---------------------------------------------------------------------------


class _Out(object):
    quiet = False
    json_mode = False


OUT = _Out()


def say(msg=""):
    if not OUT.quiet and not OUT.json_mode:
        print(msg)


def err(msg):
    print("error: " + msg, file=sys.stderr)


class TargetError(Exception):
    """Per-target failure: recorded, target skipped, others continue."""


class SourceError(Exception):
    """Source rules file could not be loaded."""


# ---------------------------------------------------------------------------
# Path bases (env overrides affect path resolution only)
# ---------------------------------------------------------------------------


def home_base():
    if os.name == "nt":
        v = os.environ.get("USERPROFILE")
    else:
        v = os.environ.get("HOME")
    if v:
        return Path(v)
    return Path.home()


def xdg_base():
    v = os.environ.get("XDG_CONFIG_HOME")
    if v:
        return Path(v)
    return home_base() / ".config"


def appdata_base():
    v = os.environ.get("APPDATA")
    if v:
        return Path(v)
    if os.name == "nt":
        return home_base() / "AppData" / "Roaming"
    return None


def flatpak_xdg_base():
    v = os.environ.get("FLATPAK_XDG_CONFIG_HOME")
    return Path(v) if v else None


def _env_dir(env_name, default_rel):
    """Agent root dir: env override replaces the whole dir, else home/rel."""
    v = os.environ.get(env_name) if env_name else None
    if v:
        return Path(v)
    return home_base() / default_rel


def claude_dir():
    return _env_dir("CLAUDE_CONFIG_DIR", ".claude")


def codex_dir():
    return _env_dir("CODEX_HOME", ".codex")


def devin_dirs():
    """User-scope Devin dirs: every existing marker dir, else platform default.

    Multi-marker rule (section 6): when both %APPDATA%/devin and
    ~/.config/devin exist, BOTH get an AGENTS.md.
    """
    appd = appdata_base()
    cands = []
    if os.name == "nt":
        if appd is not None:
            cands.append(appd / "devin")
        cands.append(xdg_base() / "devin")
    else:
        cands.append(xdg_base() / "devin")
        if appd is not None:
            cands.append(appd / "devin")
    seen = []
    for d in cands:
        if d not in seen:
            seen.append(d)
    existing = [d for d in seen if d.is_dir()]
    if existing:
        return existing
    return [seen[0]]


def goose_config_dir():
    """Goose config dir: %APPDATA%/Block/goose on Windows, XDG goose
    elsewhere - goose uses the etcetera crate's native per-platform
    strategy (AppData on Windows, XDG everywhere else)."""
    if os.name == "nt":
        # appdata_base() is None only on POSIX; mirror its own nt
        # fallback so the checker sees a Path here too.
        appd = appdata_base() or home_base() / "AppData" / "Roaming"
        return appd / "Block" / "goose"
    return xdg_base() / "goose"


def zed_dirs():
    """User-scope Zed dirs: every existing marker dir, else platform default.

    Multi-marker rule (section 6), devin precedent: Zed reads
    <config>/AGENTS.md and its config dir lives in up to three places
    (XDG, %APPDATA%/Zed on Windows, Flatpak); when several exist, ALL
    get an AGENTS.md. Needs Zed >= 1.4.0 (the old rules/ dir was removed
    in 1.4.0) - no runtime version check is possible; the floor is
    documented in the plan findings only.
    """
    appd = appdata_base()
    flat = flatpak_xdg_base()
    cands = []
    if os.name == "nt":
        if appd is not None:
            cands.append(appd / "Zed")
        cands.append(xdg_base() / "zed")
    else:
        cands.append(xdg_base() / "zed")
        if appd is not None:
            cands.append(appd / "Zed")
    if flat is not None:
        cands.append(flat / "zed")
    seen = []
    for d in cands:
        if d not in seen:
            seen.append(d)
    existing = [d for d in seen if d.is_dir()]
    if existing:
        return existing
    return [seen[0]]


# ---------------------------------------------------------------------------
# Detection engine (section 5)
# ---------------------------------------------------------------------------


def _eve_present(cwd):
    agent_dir = cwd / "agent"
    if not agent_dir.is_dir():
        return False
    pkg = cwd / "package.json"
    if not pkg.is_file():
        return False
    try:
        data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
    except ValueError:
        return False
    if not isinstance(data, dict):
        return False
    for key in ("dependencies", "devDependencies"):
        deps = data.get(key)
        if isinstance(deps, dict) and "eve" in deps:
            return True
    return False


def detect_agents(cwd=None):
    """Returns a list of dicts: id, tier, flags, paths, cwd_only."""
    home = home_base()
    xdg = xdg_base()
    appd = appdata_base()
    flat = flatpak_xdg_base()
    cwd = Path(cwd) if cwd else Path.cwd()
    results = []
    for ag in AGENTS:
        if "never" in ag["flags"]:
            continue
        matched = []
        cwd_matched = False
        home_matched = False
        if "content" in ag["flags"] and ag["id"] == "eve":
            if _eve_present(cwd):
                matched.append(cwd / "agent")
                cwd_matched = True
        else:
            override = os.environ.get(ag["env"]) if ag["env"] else None
            seen = set()
            for base, rel in ag["markers"]:
                if base == "h":
                    p = Path(override) if override else home / rel
                elif base == "x":
                    p = xdg / rel
                elif base == "a":
                    if appd is None:
                        continue
                    p = appd / rel
                elif base == "f":
                    if flat is None:
                        continue
                    p = flat / rel
                elif base == "c":
                    p = cwd / rel
                else:  # "p" absolute
                    p = Path(rel)
                key = str(p).lower()
                if key in seen:
                    continue
                seen.add(key)
                try:
                    exists = p.exists()
                except OSError:
                    exists = False
                if exists:
                    matched.append(p)
                    if base == "c":
                        cwd_matched = True
                    elif base == "h":
                        home_matched = True
        if matched:
            results.append({
                "id": ag["id"],
                "tier": ag["tier"],
                "flags": ag["flags"],
                "paths": matched,
                "cwd_only": cwd_matched and not home_matched,
            })
    return results


def close_matches(name):
    return difflib.get_close_matches(name, ALL_IDS, n=3, cutoff=0.5)


# ---------------------------------------------------------------------------
# Source loading (P2.1; D1: no version parsing anywhere)
# ---------------------------------------------------------------------------


class Source(object):
    def __init__(self, data, label):
        self.data = data
        self.label = label
        self.sha256 = hashlib.sha256(data).hexdigest()
        self.sha256_short = self.sha256[:7]
        self.size = len(data)

    @property
    def size_label(self):
        return "%.1f KB" % (self.size / 1024.0)


def _fetch_url(url):
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            data = resp.read()
    except Exception as exc:  # urllib wraps socket/HTTP/URL errors; one bucket
        raise SourceError("failed to fetch %s: %s" % (url, exc))
    if not data:
        raise SourceError("fetched source is empty: %s" % url)
    return data


def _pin_check(source, sha256_pin):
    """P5.1: with --sha256 set, verify the fetched bytes BEFORE any target
    can execute; a mismatch raises SourceError so nothing was written."""
    if sha256_pin and source.sha256 != sha256_pin.lower():
        raise SourceError(
            "sha256 mismatch for %s: expected %s..., got %s..."
            % (source.label, sha256_pin[:12], source.sha256[:12]))
    return source


def load_source(source_arg, sha256_pin=None):
    """Resolution order: --source URL|PATH, bundled ./BEHAVE.md, CANONICAL_URL.

    P5.1: a --sha256 pin applies to URL fetches only; combined with any
    local source (explicit path or the bundled fallback) it errors loudly,
    and against a fetched source a mismatch aborts before any write.
    """
    if sha256_pin and source_arg and "://" not in source_arg:
        # The pin exists to protect network fetches; loud beats silent.
        raise SourceError("--sha256 applies only to URL sources; %s is a "
                          "local path" % source_arg)
    if source_arg:
        if "://" in source_arg:
            return _pin_check(
                Source(_fetch_url(source_arg), source_arg), sha256_pin)
        p = Path(source_arg).expanduser()
        try:
            data = p.read_bytes()
        except OSError as exc:
            raise SourceError("failed to read source file %s: %s" % (p, exc))
        if not data:
            raise SourceError("source file is empty: %s" % p)
        return Source(data, str(p))
    bundled = Path(__file__).resolve().parent / "BEHAVE.md"
    if bundled.is_file():
        if sha256_pin:
            # Same loud rule: the bundled file is local, nothing to pin.
            raise SourceError("--sha256 applies only to URL sources; the "
                              "bundled %s is local (pass --source URL)"
                              % bundled.name)
        try:
            data = bundled.read_bytes()
        except OSError as exc:
            raise SourceError("failed to read bundled %s: %s" % (bundled, exc))
        if data:
            return Source(data, "bundled %s" % bundled.name)
    return _pin_check(
        Source(_fetch_url(CANONICAL_URL), CANONICAL_URL), sha256_pin)


# ---------------------------------------------------------------------------
# Inline engine (P2.3 / P2.4)
# ---------------------------------------------------------------------------
# Junction rule (section 4.1 step 4): the block is followed by exactly one
# blank line before the old first content line; install normalizes leading
# blank lines of the remainder to that single separator, remove consumes the
# block plus at most one blank line - making install/remove exact inverses
# and double-runs byte-idempotent for ordinary content.


def _begin_line(block_id):
    return ("<!-- BEGIN %s - installed by install.py; --remove uninstalls -->"
            % block_id)


def _end_line(block_id):
    return "<!-- END %s -->" % block_id


def block_bytes(block_id, content):
    begin = _begin_line(block_id).encode("ascii") + b"\n"
    body = content
    if body and not body.endswith(b"\n"):
        body = body + b"\n"
    end = _end_line(block_id).encode("ascii") + b"\n"
    return begin + body + end


def _strip_pattern(block_id):
    bid = re.escape(block_id.encode("ascii"))
    return re.compile(
        b"<!-- BEGIN " + bid + b" [^\r\n]*-->\r?\n?"
        b".*?"
        b"<!-- END " + bid + b" -->\r?\n?(?:\r?\n)?",
        re.DOTALL,
    )


_LEADING_BLANKS = re.compile(rb"(?:[ \t]*(?:\r\n|\n))*")


def strip_inline_blocks(data, block_id):
    return _strip_pattern(block_id).sub(b"", data)


def inline_begin_prefix(block_id):
    return ("<!-- BEGIN %s " % block_id).encode("ascii")


def has_inline_block(path, block_id):
    try:
        raw = path.read_bytes()
    except OSError:
        return False
    return inline_begin_prefix(block_id) in raw


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".behave-tmp-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, str(path))
    except OSError:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def upsert_inline(path, block_id, content):
    """Prepends/replaces the marked block. Returns a size warning or None."""
    try:
        raw = path.read_bytes() if path.exists() else b""
    except OSError as exc:
        raise TargetError(str(exc))
    bom = b""
    if raw.startswith(BOM):
        bom = BOM
        raw = raw[len(BOM):]
    stripped = strip_inline_blocks(raw, block_id)
    m = _LEADING_BLANKS.match(stripped)
    core = stripped[m.end():] if m is not None else stripped
    block = block_bytes(block_id, content)
    if core:
        new_body = block + b"\n" + core
        if not new_body.endswith(b"\n"):
            new_body = new_body + b"\n"
    else:
        new_body = block
    result = bom + new_body
    warning = None
    if len(result) > SIZE_WARN_BYTES:
        warning = ("%s is %d bytes (> 30 KiB); Codex caps combined "
                   "AGENTS.md at 32 KiB - proceeding anyway" % (path, len(result)))
    try:
        atomic_write(path, result)
    except OSError as exc:
        raise TargetError("cannot write %s: %s" % (path, exc))
    return warning


def remove_inline(path, block_id):
    """Returns 'absent' | 'deleted' | 'stripped'."""
    if not path.exists():
        return "absent"
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise TargetError("cannot read %s: %s" % (path, exc))
    stripped = strip_inline_blocks(raw, block_id)
    if stripped == raw:
        return "absent"
    probe = stripped[len(BOM):] if stripped.startswith(BOM) else stripped
    if probe.strip(b" \t\r\n\x0b\x0c") == b"":
        try:
            path.unlink()
        except OSError as exc:
            raise TargetError("cannot delete %s: %s" % (path, exc))
        return "deleted"
    try:
        atomic_write(path, stripped)
    except OSError as exc:
        raise TargetError("cannot write %s: %s" % (path, exc))
    return "stripped"


# ---------------------------------------------------------------------------
# Drop engine (P2.5)
# ---------------------------------------------------------------------------


def drop_marker_bytes(block_id):
    return ("<!-- installed by install.py (%s); --remove deletes this file -->\n"
            % block_id).encode("ascii")


def write_drop(path, agent_id, block_id, content):
    fm = DROP_FRONTMATTER.get(agent_id, "").encode("ascii")
    data = fm + drop_marker_bytes(block_id) + content
    try:
        atomic_write(path, data)
    except OSError as exc:
        raise TargetError("cannot write %s: %s" % (path, exc))


def drop_has_marker(path, block_id):
    try:
        raw = path.read_bytes()
    except OSError:
        return False
    return drop_marker_bytes(block_id) in raw


def cursor_user_warning():
    """Limitation note for user-scope Cursor drops: Cursor loads
    ~/.cursor/rules only when the opened project is inside the home
    directory (it walks up from the project dir to discover it)."""
    return ("Cursor loads ~/.cursor/rules only when the opened project is "
            "inside your home directory (resolved home: %s); projects "
            "elsewhere will not load it - use project scope (shared "
            "AGENTS.md) for those" % home_base())


# ---------------------------------------------------------------------------
# Plain copy engine (P2.6, D3)
# ---------------------------------------------------------------------------


def write_copy(dest_dir, source, confirm=None):
    """Writes BEHAVE.md; provenance guard (confirm() may allow a drift
    overwrite; no callback = always refuse); returns 'created'|'updated'."""
    dest = dest_dir / "BEHAVE.md"
    existed = dest.exists()
    if existed:
        try:
            cur = dest.read_bytes()
        except OSError as exc:
            raise TargetError("cannot read %s: %s" % (dest, exc))
        if hashlib.sha256(cur).hexdigest() != source.sha256:
            if confirm is None:
                raise TargetError(
                    "existing BEHAVE.md does not match the source; "
                    "rename it or pass --source")
            if not confirm():
                raise TargetError(
                    "existing BEHAVE.md differs from the source; kept")
    try:
        atomic_write(dest, source.data)
    except OSError as exc:
        raise TargetError("cannot write %s: %s" % (dest, exc))
    return "updated" if existed else "created"


# ---------------------------------------------------------------------------
# Plan builder (P2.7)
# ---------------------------------------------------------------------------


def find_git_root(start):
    p = Path(start).resolve()
    while True:
        if (p / ".git").exists():
            return p
        if p.parent == p:
            return None
        p = p.parent


def _mk_target(agents, path, mode, drop_agent=None, shared=False,
               gitignore=False, kind=None):
    return {
        "agents": list(agents),
        "agent": ",".join(agents),
        "path": Path(path),
        "mode": mode,
        "drop_agent": drop_agent,
        "shared": shared,
        "gitignore": gitignore,
        "kind": kind or mode,
    }


def claude_file_exists(project_dir):
    return ((project_dir / "CLAUDE.md").exists()
            or (project_dir / ".claude" / "CLAUDE.md").exists())


def claude_project_target(variant, project_dir):
    if variant == "root":
        return project_dir / "CLAUDE.md", "inline"
    if variant == "dot-claude":
        return project_dir / ".claude" / "CLAUDE.md", "inline"
    if variant == "local":
        return project_dir / "CLAUDE.local.md", "inline"
    return project_dir / ".claude" / "rules" / "behave.md", "drop"


def build_install_plan(agents, scope, variant, claude_mode, project_dir,
                       block_id):
    """Returns (targets, notes). agents: tier-1 ids only."""
    targets = []
    notes = []
    if scope == "local":
        for a in agents:
            if a != "claude-code":
                notes.append(
                    "warn: local scope supports Claude Code only; skipping %s"
                    % a)
        if "claude-code" not in agents:
            notes.append("warn: nothing installable in local scope "
                         "(Claude Code only)")
            return targets, notes
        p, m = claude_project_target("local", project_dir)
        targets.append(_mk_target(["claude-code"], p, m,
                                  drop_agent="claude-code", gitignore=True))
        return targets, notes

    if scope == "user":
        for a in agents:
            if a == "claude-code":
                if claude_mode == "inline":
                    targets.append(_mk_target(
                        ["claude-code"], claude_dir() / "CLAUDE.md", "inline"))
                else:
                    targets.append(_mk_target(
                        ["claude-code"],
                        claude_dir() / "rules" / "behave.md", "drop",
                        drop_agent="claude-code"))
            elif a == "codex":
                targets.append(_mk_target(
                    ["codex"], codex_dir() / "AGENTS.md", "inline"))
            elif a == "opencode":
                targets.append(_mk_target(
                    ["opencode"], xdg_base() / "opencode" / "AGENTS.md",
                    "inline"))
            elif a == "pi":
                targets.append(_mk_target(
                    ["pi"], home_base() / ".pi" / "agent" / "AGENTS.md",
                    "inline"))
            elif a == "omp":
                targets.append(_mk_target(
                    ["omp"], home_base() / ".omp" / "agent" / "AGENTS.md",
                    "inline"))
            elif a == "devin":
                for d in devin_dirs():
                    targets.append(_mk_target(
                        ["devin"], d / "AGENTS.md", "inline"))
            elif a == "cursor":
                targets.append(_mk_target(
                    ["cursor"], home_base() / ".cursor" / "rules" / "behave.mdc",
                    "drop", drop_agent="cursor"))
            elif a == "gemini-cli":
                targets.append(_mk_target(
                    ["gemini-cli"], home_base() / ".gemini" / "GEMINI.md",
                    "inline"))
            elif a == "github-copilot":
                targets.append(_mk_target(
                    ["github-copilot"],
                    home_base() / ".copilot" / "instructions" /
                    "behave.instructions.md",
                    "drop", drop_agent="github-copilot"))
            elif a == "roo":
                targets.append(_mk_target(
                    ["roo"], home_base() / ".roo" / "rules" / "behave.md",
                    "drop", drop_agent="roo"))
            elif a == "augment":
                targets.append(_mk_target(
                    ["augment"], home_base() / ".augment" / "rules" /
                    "behave.md", "drop", drop_agent="augment"))
            elif a == "kilo":
                targets.append(_mk_target(
                    ["kilo"], home_base() / ".kilocode" / "rules" /
                    "behave.md", "drop", drop_agent="kilo"))
            elif a == "droid":
                targets.append(_mk_target(
                    ["droid"], home_base() / ".factory" / "AGENTS.md",
                    "inline"))
            elif a == "deepagents":
                targets.append(_mk_target(
                    ["deepagents"], home_base() / ".deepagents" / "agent" /
                    "AGENTS.md", "inline"))
            elif a == "cline":
                # cline's SDK loader reads ~/.cline/rules among its global
                # rules search paths; chosen over Documents/Cline/Rules
                # because it matches the ~/.cline detection marker and
                # needs no Documents-dir resolver.
                targets.append(_mk_target(
                    ["cline"], home_base() / ".cline" / "rules" /
                    "behave.md", "drop", drop_agent="cline"))
            elif a == "crush":
                # CRUSH.md is the user's own cross-project instructions
                # file (like GEMINI.md): inline block at the top so
                # existing content survives - never a whole-file drop.
                # crush loads <config>/crush/CRUSH.md by default, where
                # config = $XDG_CONFIG_HOME or ~/.config on ALL platforms.
                targets.append(_mk_target(
                    ["crush"], xdg_base() / "crush" / "CRUSH.md",
                    "inline"))
            elif a == "amp":
                # amp hardcodes $HOME/.config on every platform
                # (including Windows) and does not honor
                # XDG_CONFIG_HOME, so home_base()/".config" - NOT
                # xdg_base().
                targets.append(_mk_target(
                    ["amp"], home_base() / ".config" / "amp" / "AGENTS.md",
                    "inline"))
            elif a == "goose":
                targets.append(_mk_target(
                    ["goose"], goose_config_dir() / "AGENTS.md",
                    "inline"))
            elif a == "zed":
                for d in zed_dirs():
                    targets.append(_mk_target(
                        ["zed"], d / "AGENTS.md", "inline"))
            elif a == "openhands":
                # OpenHands CLI hardwires load_user_skills=True and
                # always loads trigger-less .md files from
                # ~/.agents/skills/ (the modern dir; legacy
                # ~/.openhands/{skills,microagents}/ also read - marker
                # ~/.openhands stays detection-only).
                targets.append(_mk_target(
                    ["openhands"], home_base() / ".agents" / "skills" /
                    "behave.md", "drop", drop_agent="openhands"))
            elif a == "warp":
                # ~/.agents/AGENTS.md is warp's ONLY registered global
                # rulefile (docs.warp.dev + warp source
                # GlobalRuleSource::Agents) AND a de-facto shared
                # cross-agent file (cline, droid, goose, kimi-code read
                # it too) - the marked block is idempotent, so it serves
                # every reader.
                targets.append(_mk_target(
                    ["warp"], home_base() / ".agents" / "AGENTS.md",
                    "inline"))
            elif a == "junie":
                # documented for Junie CLI (%USERPROFILE%\.junie\AGENTS.md);
                # the IDE plugin loads project scope only - caveat
                # documented in TODO-LEFT findings. Project scope rides
                # the shared ./AGENTS.md family block, NOT
                # .junie/AGENTS.md: that file is EXCLUSIVE and would
                # suppress the root AGENTS.md + playbook + rules.
                targets.append(_mk_target(
                    ["junie"], home_base() / ".junie" / "AGENTS.md",
                    "inline"))
            elif a == "posit-assistant":
                # Posit Assistant reads ~/.posit/assistant/AGENTS.md as
                # user memory (every session, no trust prompt); legacy
                # ~/.positai is auto-migrated by the app on first
                # launch, so the ~/.posit marker suffices - the legacy
                # dir is never a second install target.
                targets.append(_mk_target(
                    ["posit-assistant"],
                    home_base() / ".posit" / "assistant" / "AGENTS.md",
                    "inline"))
            elif a == "zcode":
                # zcode reads ~/.zcode/AGENTS.md at task start (appended
                # first into the prompt); the /Applications/ZCode.app
                # registry marker is presence-only detection (the app
                # bundle loads no rules file) - ~/.zcode is the single
                # user target.
                targets.append(_mk_target(
                    ["zcode"], home_base() / ".zcode" / "AGENTS.md",
                    "inline"))
            elif a == "minimax-code":
                # ~/.minimax/AGENTS.md is read by the shipped desktop
                # bundle but UNDOCUMENTED (TODO-LEFT findings) - wire
                # nothing on hope; project scope rides the shared
                # ./AGENTS.md family block.
                notes.append("warn: minimax-code has no verified "
                             "user-wide target; skipping (project "
                             "scope only)")
            elif a == "openclaw":
                # OpenClaw runs a personal workspace model - it loads
                # ~/.openclaw/workspace/AGENTS.md (workspace bootstrap,
                # injected every session) but does NOT read project
                # ./AGENTS.md, so openclaw is intentionally NOT in
                # FAMILY_IDS; legacy ~/.clawdbot / ~/.moltbot are
                # inert after migration - detection-only markers.
                targets.append(_mk_target(
                    ["openclaw"],
                    home_base() / ".openclaw" / "workspace" / "AGENTS.md",
                    "inline"))
            elif a == "kimi-code-cli":
                # ~/.kimi-code/AGENTS.md is kimi-code's documented
                # global memory (loadAgentsMdForRoots, default-on);
                # the ~/.kimi marker detects the OLD Python Kimi CLI -
                # a different tool that loads no user rules file - and
                # stays detection-only.
                targets.append(_mk_target(
                    ["kimi-code-cli"],
                    home_base() / ".kimi-code" / "AGENTS.md",
                    "inline"))
            elif a == "qwen-code":
                # qwen-code loads ~/.qwen/QWEN.md every conversation
                # (memoryDiscovery.ts: the global context file is
                # always checked, created by the user or /memory).
                # QWEN_HOME env override exists but detection/install
                # use the plain home path. Project scope rides the
                # shared ./AGENTS.md family block (AGENTS.md is in
                # the default context filename list).
                targets.append(_mk_target(
                    ["qwen-code"], home_base() / ".qwen" / "QWEN.md",
                    "inline"))
            elif a == "trae":
                # ~/.trae/user_rules.md is the Trae IDE's global rules
                # file (docs.trae.ai/ide/rules: "Global rules take
                # effect in all projects"; the IDE Rules UI creates
                # this exact file) - inline at the top so existing
                # user rules survive. Windows: %userprofile%/.trae.
                targets.append(_mk_target(
                    ["trae"], home_base() / ".trae" / "user_rules.md",
                    "inline"))
            elif a == "antigravity":
                # antigravity reads the SAME global file as gemini-cli
                # ("Global rules live in ~/.gemini/GEMINI.md and are
                # applied across all workspaces" - antigravity.google
                # /docs/ide/rules + /docs/rules-workflows). Shared-file
                # case, warp ~/.agents/AGENTS.md precedent: the marked
                # block is idempotent, so selecting both agents writes
                # one block; --remove cleans it for both (the removal
                # candidate lists gemini-cli AND antigravity).
                targets.append(_mk_target(
                    ["antigravity"], home_base() / ".gemini" / "GEMINI.md",
                    "inline"))
            elif a == "kiro-cli":
                # ~/.kiro/steering/ is Kiro's global steering dir -
                # "Kiro will automatically load these files in chat
                # sessions" (kiro.dev/docs/steering); on the CLI,
                # inclusion modes are not supported at all, and on the
                # IDE the default inclusion is always, so a bare drop
                # file needs no frontmatter. Global steering applies
                # to IDE + CLI only (not Web/Mobile). Project scope
                # rides the shared ./AGENTS.md family block (root
                # AGENTS.md is "always included", all surfaces).
                targets.append(_mk_target(
                    ["kiro-cli"], home_base() / ".kiro" / "steering" /
                    "behave.md", "drop", drop_agent="kiro-cli"))
            elif a == "qoder":
                # User-level rules at ~/.qoder/rules/ apply to every
                # project and "when no loading-related frontmatter is
                # configured, rules are always active by default"
                # (docs.qoder.com/cli/memory - documented, unlike the
                # qwen-code equivalent). ~/.qoder/AGENTS.md is the
                # other user surface; the drop file keeps behave in
                # its own file. Project scope rides the shared
                # ./AGENTS.md family block ("AGENTS.md is the default
                # context file name", loaded at session start inside
                # a trusted workspace).
                targets.append(_mk_target(
                    ["qoder"], home_base() / ".qoder" / "rules" /
                    "behave.md", "drop", drop_agent="qoder"))
            elif a == "grok":
                # Grok Build (xAI, binary `grok`) scans $GROK_HOME (or
                # ~/.grok) unconditionally: named files + rules/*.md
                # at the home root, no off switch (agents_md.rs
                # L187-302; docs.x.ai/build/features/project-rules).
                # rules/*.md bodies are frontmatter-stripped, so a
                # bare drop works. Project scope rides the shared
                # ./AGENTS.md family block (repo-root-to-cwd chain,
                # deeper files win). CAVEAT: the third-party
                # superagent-ai/grok-cli also writes ~/.grok (no
                # GROK_HOME) - the marker can false-positive; GROK_HOME
                # is the disambiguator (kept, marker/target divergence
                # precedent).
                targets.append(_mk_target(
                    ["grok"], home_base() / ".grok" / "rules" /
                    "behave.md", "drop", drop_agent="grok"))
        return targets, notes

    # project scope
    fam = [a for a in agents if a in FAMILY_IDS]
    if fam:
        if claude_file_exists(project_dir):
            notes.append(
                "Note: this project has a Claude file; Claude Code ignores "
                "AGENTS.md and no bridge is offered - skipping the AGENTS.md "
                "path (pick the claude family to reach Claude Code).")
        elif set(fam) == {"devin"} and not (project_dir / "AGENTS.md").exists():
            targets.append(_mk_target(
                ["devin"], project_dir / ".devin" / "rules" / "behave.md",
                "drop", drop_agent="devin"))
        else:
            targets.append(_mk_target(
                FAMILY_IDS, project_dir / "AGENTS.md", "inline", shared=True))
    if "claude-code" in agents:
        p, m = claude_project_target(variant, project_dir)
        t = _mk_target(["claude-code"], p, m, drop_agent="claude-code")
        if variant == "local":
            t["gitignore"] = True
        targets.append(t)
    if "gemini-cli" in agents:
        targets.append(_mk_target(
            ["gemini-cli"], project_dir / "GEMINI.md", "inline"))
    if "github-copilot" in agents:
        targets.append(_mk_target(
            ["github-copilot"],
            project_dir / ".github" / "copilot-instructions.md", "inline"))
    if "openclaw" in agents:
        # user-scope-only agent: OpenClaw's personal workspace model
        # never reads project ./AGENTS.md (see the user-scope branch)
        notes.append("warn: openclaw is user-scope only (personal "
                     "workspace); skipping")
    if "trae" in agents:
        # trae reads root AGENTS.md/CLAUDE.md only behind an import
        # toggle (Settings > Rules > Import), so it is NOT a family
        # agent; the native .trae/rules/ drop is always-on via
        # alwaysApply (docs.trae.ai/ide/rules).
        targets.append(_mk_target(
            ["trae"], project_dir / ".trae" / "rules" / "behave.md",
            "drop", drop_agent="trae"))
    return targets, notes


def gitignore_step(project_dir, filename):
    """Appends filename to <project_dir>/.gitignore when a repo exists."""
    root = find_git_root(project_dir)
    if root is None:
        return ("note: no git repo above %s; skipped the gitignore step for %s"
                % (project_dir, filename))
    gi = project_dir / ".gitignore"
    lines = []
    if gi.exists():
        try:
            lines = gi.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            lines = []
    if filename in [ln.strip() for ln in lines]:
        return "note: %s is already gitignored" % filename
    try:
        with open(str(gi), "a", encoding="utf-8", newline="\n") as fh:
            if lines and lines[-1].strip() != "":
                fh.write("\n")
            fh.write(filename + "\n")
        return "note: added %s to %s" % (filename, gi)
    except OSError as exc:
        return "note: could not update .gitignore: %s" % exc


# ---------------------------------------------------------------------------
# Target execution + reports
# ---------------------------------------------------------------------------


def execute_targets(targets, source, block_id, project_dir=None):
    results = []
    for t in targets:
        entry = {
            "agent": t["agent"],
            "target": t["path"].as_posix(),
            "mode": t["mode"],
            "status": "skipped",
            "warning": None,
            "error": None,
        }
        try:
            existed = t["path"].exists()
            if t["mode"] == "drop":
                write_drop(t["path"], t["drop_agent"], block_id, source.data)
                entry["status"] = "upserted" if existed else "created"
                detail = "rules file rewritten" if existed else "rules file created"
                if t["drop_agent"] == "cursor":
                    warning = cursor_user_warning()
                    entry["warning"] = (
                        warning if entry["warning"] is None
                        else entry["warning"] + "; " + warning)
                    say("  warning: %s" % warning)
            else:
                warning = upsert_inline(t["path"], block_id, source.data)
                entry["status"] = "upserted" if existed else "created"
                detail = "block upserted" if existed else "file created with block"
                if warning:
                    entry["warning"] = warning
                    say("  warning: %s" % warning)
            say("  ok    %-28s %s: %s" % (t["agent"], detail, t["path"]))
            if t["gitignore"]:
                note = gitignore_step(project_dir, t["path"].name)
                if note:
                    say("  " + note)
            results.append(entry)
        except TargetError as exc:
            entry["error"] = str(exc)
            err("target failed (%s): %s" % (t["agent"], exc))
            results.append(entry)
    return results


def restart_hints(agents):
    lines = []
    if "claude-code" in agents:
        lines.append("  - Claude Code: start a new session; verify via "
                     "/context (Memory files).")
    fam_restart = [a for a in FAMILY_IDS if a in agents and a != "cursor"]
    if fam_restart:
        # one grouped line for the AGENTS.md family; cursor keeps its own
        names = " / ".join(DISPLAY.get(a, a) for a in FAMILY_IDS
                           if a != "cursor")
        lines.append("  - %s: restart them (Codex rebuilds its chain "
                     "every run)." % names)
    if "cursor" in agents:
        lines.append("  - Cursor: restart the app (rules apply to Agent/Chat).")
    if "gemini-cli" in agents:
        lines.append("  - Gemini CLI: restart the session.")
    if "github-copilot" in agents:
        lines.append("  - GitHub Copilot: restart the CLI / reload the "
                     "editor window.")
    if lines:
        say("Done - restart your agents to pick up changes:")
        for ln in lines:
            say(ln)


def stale_hint(written_paths, project_dir, block_id):
    """After any install: hint at marked blocks left in other locations."""
    findings = scan_removal(None, None, None, project_dir, block_id)
    count = 0
    for f in findings:
        if f["path"] in written_paths:
            continue
        say("also found: %s; run --remove to clean" % (f["path"],))
        count += 1
        if count >= 5:
            break


# ---------------------------------------------------------------------------
# Removal scanner (P2.8)
# ---------------------------------------------------------------------------


def scan_removal(agent_filter, scope_filter, variant_filter, project_dir,
                 block_id):
    """Candidate targets bearing our markers. agent_filter/scope_filter/
    variant_filter may be None (= all)."""
    candidates = []

    def add(path, mode, agents, drop_agent=None, variant=None):
        if agent_filter and not (set(agents) & set(agent_filter)):
            return
        if variant_filter and variant and variant != variant_filter:
            return
        candidates.append({
            "agents": list(agents),
            "agent": ",".join(agents),
            "path": Path(path),
            "mode": mode,
            "drop_agent": drop_agent,
            "variant": variant,
            "shared": list(agents) == FAMILY_IDS,
        })

    if scope_filter in (None, "user"):
        add(claude_dir() / "CLAUDE.md", "inline", ["claude-code"])
        add(claude_dir() / "rules" / "behave.md", "drop", ["claude-code"],
            drop_agent="claude-code")
        add(codex_dir() / "AGENTS.md", "inline", ["codex"])
        add(xdg_base() / "opencode" / "AGENTS.md", "inline", ["opencode"])
        add(home_base() / ".pi" / "agent" / "AGENTS.md", "inline", ["pi"])
        add(home_base() / ".omp" / "agent" / "AGENTS.md", "inline", ["omp"])
        for d in devin_dirs():
            add(d / "AGENTS.md", "inline", ["devin"])
        add(home_base() / ".cursor" / "rules" / "behave.mdc", "drop",
            ["cursor"], drop_agent="cursor")
        # shared ~/.gemini/GEMINI.md: gemini-cli + antigravity (and the
        # antigravity-cli reader) - one candidate, both agents, one block
        add(home_base() / ".gemini" / "GEMINI.md", "inline",
            ["gemini-cli", "antigravity"])
        add(home_base() / ".copilot" / "instructions" / "behave.instructions.md",
            "drop", ["github-copilot"], drop_agent="github-copilot")
        add(home_base() / ".roo" / "rules" / "behave.md", "drop", ["roo"],
            drop_agent="roo")
        add(home_base() / ".augment" / "rules" / "behave.md", "drop",
            ["augment"], drop_agent="augment")
        add(home_base() / ".kilocode" / "rules" / "behave.md", "drop",
            ["kilo"], drop_agent="kilo")
        add(home_base() / ".factory" / "AGENTS.md", "inline", ["droid"])
        add(home_base() / ".deepagents" / "agent" / "AGENTS.md", "inline",
            ["deepagents"])
        add(home_base() / ".cline" / "rules" / "behave.md", "drop",
            ["cline"], drop_agent="cline")
        add(xdg_base() / "crush" / "CRUSH.md", "inline", ["crush"])
        add(home_base() / ".config" / "amp" / "AGENTS.md", "inline",
            ["amp"])
        add(goose_config_dir() / "AGENTS.md", "inline", ["goose"])
        for d in zed_dirs():
            add(d / "AGENTS.md", "inline", ["zed"])
        add(home_base() / ".agents" / "skills" / "behave.md", "drop",
            ["openhands"], drop_agent="openhands")
        add(home_base() / ".agents" / "AGENTS.md", "inline", ["warp"])
        add(home_base() / ".junie" / "AGENTS.md", "inline", ["junie"])
        add(home_base() / ".posit" / "assistant" / "AGENTS.md", "inline",
            ["posit-assistant"])
        add(home_base() / ".zcode" / "AGENTS.md", "inline", ["zcode"])
        add(home_base() / ".openclaw" / "workspace" / "AGENTS.md",
            "inline", ["openclaw"])
        add(home_base() / ".kimi-code" / "AGENTS.md", "inline",
            ["kimi-code-cli"])
        add(home_base() / ".qwen" / "QWEN.md", "inline", ["qwen-code"])
        add(home_base() / ".trae" / "user_rules.md", "inline", ["trae"])
        add(home_base() / ".kiro" / "steering" / "behave.md", "drop",
            ["kiro-cli"], drop_agent="kiro-cli")
        add(home_base() / ".qoder" / "rules" / "behave.md", "drop",
            ["qoder"], drop_agent="qoder")
        add(home_base() / ".grok" / "rules" / "behave.md", "drop",
            ["grok"], drop_agent="grok")

    if scope_filter in (None, "project", "local"):
        d = Path(project_dir) if project_dir is not None else Path.cwd()
        add(d / "CLAUDE.md", "inline", ["claude-code"], variant="root")
        add(d / ".claude" / "CLAUDE.md", "inline", ["claude-code"],
            variant="dot-claude")
        add(d / "CLAUDE.local.md", "inline", ["claude-code"], variant="local")
        add(d / ".claude" / "rules" / "behave.md", "drop", ["claude-code"],
            drop_agent="claude-code", variant="rules")
        add(d / "AGENTS.md", "inline", FAMILY_IDS)
        add(d / ".devin" / "rules" / "behave.md", "drop", ["devin"],
            drop_agent="devin")
        # legacy cleanup: older installers dropped .cursor/rules/behave.mdc
        # in projects (cursor now uses the shared AGENTS.md family block)
        add(d / ".cursor" / "rules" / "behave.mdc", "drop", ["cursor"],
            drop_agent="cursor")
        add(d / ".github" / "copilot-instructions.md", "inline",
            ["github-copilot"])
        add(d / "GEMINI.md", "inline", ["gemini-cli"])
        add(d / ".trae" / "rules" / "behave.md", "drop", ["trae"],
            drop_agent="trae")

    findings = []
    for cand in candidates:
        p = cand["path"]
        if not p.exists():
            continue
        if cand["mode"] == "inline":
            if not has_inline_block(p, block_id):
                continue
        else:
            if not drop_has_marker(p, block_id):
                continue
        findings.append(cand)
    return findings


def execute_removal(findings, block_id):
    results = []
    for f in findings:
        entry = {
            "agent": f["agent"],
            "target": f["path"].as_posix(),
            "mode": f["mode"],
            "status": "removed",
            "warning": None,
            "error": None,
        }
        try:
            if f["mode"] == "inline":
                res = remove_inline(f["path"], block_id)
                if res == "deleted":
                    say("  removed block; file empty -> deleted %s" % f["path"])
                else:
                    say("  removed block from %s" % f["path"])
                if f["shared"]:
                    say("    (served %s)" % f["agent"])
            else:
                f["path"].unlink()
                say("  removed %s" % f["path"])
            results.append(entry)
        except (OSError, TargetError) as exc:
            entry["error"] = str(exc)
            err("remove failed (%s): %s" % (f["path"], exc))
            results.append(entry)
    return results


# ---------------------------------------------------------------------------
# Headless CLI (P3.1)
# ---------------------------------------------------------------------------

EXAMPLES_TEXT = """\
examples:
  python install.py --all-detected --scope user --yes
  python install.py --agent claude-code --scope project --claude-variant rules --yes
  python install.py --agent codex,opencode,pi,devin --scope project --project-dir . --yes
  python install.py --copy-only --project-dir .
  python install.py --remove --yes
  python install.py --remove --agent claude-code --scope user --yes
  python install.py --interactive --agent claude-code --scope project

notes:
  - any flags without --interactive run headless; writes need --yes
    (--copy-only is exempt and runs without --yes)
  - zero arguments launch the interactive flow when stdin is a terminal
"""


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        print("usage error: %s" % message, file=sys.stderr)
        sys.exit(1)


def build_parser():
    p = _Parser(
        prog="install.py",
        description="Install BEHAVE.md rules into AI coding agents "
                    "(inline blocks, rules-dir drop files, or plain copies).",
        epilog=EXAMPLES_TEXT,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--agent", action="append", metavar="ID[,ID...]",
                   help="target agents (repeatable, comma-separated); "
                        "ids are listed by --list")
    p.add_argument("--all-detected", action="store_true",
                   help="install into every supported agent found on this "
                        "machine")
    p.add_argument("--scope", choices=["user", "project", "local", "auto"],
                   default="auto",
                   help="where the rules apply; auto = project if the "
                        "target dir is inside a git repo, else user "
                        "(default: auto)")
    p.add_argument("--claude-variant",
                   choices=["root", "dot-claude", "local", "rules"],
                   default=None,
                   help="project-scope Claude target file (default: rules; "
                        "--scope local implies local)")
    p.add_argument("--claude-mode", choices=["inline", "rules"],
                   default="rules",
                   help="user-scope Claude style: drop into the rules dir "
                        "(default) or inline block in ~/.claude/CLAUDE.md")
    p.add_argument("--source", metavar="URL|PATH", default=None,
                   help="rules file source (default: bundled BEHAVE.md next "
                        "to install.py; falls back to fetching the "
                        "canonical URL)")
    p.add_argument("--sha256", metavar="HEX", default=None,
                   help="expected sha256 of rules fetched from a URL "
                        "source; aborts before any write on mismatch "
                        "(URL sources only)")
    p.add_argument("--block-id", default="behave",
                   help="marker id used in BEGIN/END comments (default: "
                        "behave); --remove needs the same id")
    p.add_argument("--project-dir", metavar="PATH", default=None,
                   help="target directory for project scope (default: "
                        "current directory)")
    p.add_argument("--copy-only", action="store_true",
                   help="write BEHAVE.md into --project-dir and touch "
                        "nothing else; not tracked by --remove; does not "
                        "require --yes")
    p.add_argument("--remove", action="store_true",
                   help="uninstall: scan all known targets (narrow with "
                        "--agent/--scope/--claude-variant), list findings, "
                        "remove them (needs --yes in headless mode)")
    p.add_argument("--interactive", action="store_true",
                   help="launch the interactive TUI; other flags act as "
                        "pre-selections (--json/--quiet are ignored there)")
    p.add_argument("--ascii", action="store_true",
                   help="launch the interactive TUI with the "
                        "numbered-prompt navigation (no arrow-key "
                        "menus) - implies --interactive, easier to "
                        "script")
    p.add_argument("--list", action="store_true",
                   help="print detected agents and all known ids, then exit")
    p.add_argument("--json", action="store_true",
                   help="machine-readable results on stdout; silences "
                        "banners")
    p.add_argument("--yes", action="store_true",
                   help="assume yes; required for headless writes (except "
                        "--copy-only)")
    p.add_argument("--quiet", action="store_true", help="only errors")
    return p


def _parse_requested_agents(args):
    requested = []
    for chunk in (args.agent or []):
        for part in chunk.split(","):
            part = part.strip()
            if part and part not in requested:
                requested.append(part)
    return requested


def _validate_agents(requested):
    unknown = [a for a in requested if a not in AGENT_BY_ID]
    for u in unknown:
        matches = close_matches(u)
        hint = ("; closest matches: %s" % ", ".join(matches)) if matches else ""
        err("unknown agent id '%s'%s" % (u, hint))
    return not unknown


def _project_dir_of(args):
    if args.project_dir:
        return Path(args.project_dir).expanduser()
    return Path.cwd()


def _block_json(source, block_id):
    d = {"id": block_id}
    if source is not None:
        d["sha256"] = source.sha256
        d["sha256_short"] = source.sha256_short
    return d


def cmd_list(args):
    det = detect_agents()
    print("Detected agents (%d):" % len(det))
    if not det:
        print("  (none)")
    for d in det:
        note = ""
        if d["id"] == "windsurf":
            note = "  (deprecated IDE; upgrade to Devin Desktop)"
        elif d["cwd_only"]:
            note = "  (cwd marker; report-only)"
        elif d["id"] not in TIER1_SET:
            note = "  (no install support)"
        paths = ", ".join(str(p) for p in d["paths"])
        print("  %-16s %s%s" % (d["id"], paths, note))
    print("All known ids (%d):" % len(AGENTS))
    print("  " + ", ".join(ALL_IDS))
    return 0


def cmd_install(args):
    requested = _parse_requested_agents(args)
    if not _validate_agents(requested):
        return 2
    project_dir = _project_dir_of(args)
    scope = args.scope or "auto"
    if scope == "auto":
        base = Path(args.project_dir).expanduser() if args.project_dir \
            else Path.cwd()
        scope = "project" if find_git_root(base) else "user"

    agents = [a for a in requested if a in TIER1_SET]
    for a in requested:
        if a not in TIER1_SET:
            say("note: %s has no install support yet (detect-only); "
                "skipping" % a)
    if args.all_detected:
        det = detect_agents()
        unsupported_detected = []
        for d in det:
            if d["id"] in TIER1_SET:
                if d["id"] not in agents:
                    agents.append(d["id"])
            elif d["id"] != "windsurf":
                unsupported_detected.append(d["id"])
        ws = [d for d in det if d["id"] == "windsurf"]
        if ws:
            say("note: windsurf detected (deprecated IDE; upgrade to Devin "
                "Desktop)")
        if unsupported_detected:
            say("note: detected without install support: %s"
                % ", ".join(sorted(unsupported_detected)))
    if not agents:
        if requested:
            err("no install support for: %s (detect-only); nothing to do"
                % ", ".join(requested))
        elif args.all_detected:
            err("no supported agents detected on this machine")
        else:
            err("no agents specified; pass --agent ID or --all-detected")
        return 2

    # Resolve the source BEFORE any writes (exit 3, no partial writes).
    try:
        source = load_source(args.source, args.sha256)
    except SourceError as exc:
        err(str(exc))
        return 3

    if scope == "local" and args.claude_variant not in (None, "local"):
        err("usage error: --scope local only supports --claude-variant local")
        return 1
    variant = args.claude_variant or ("local" if scope == "local" else "rules")
    claude_mode = args.claude_mode or "rules"

    targets, notes = build_install_plan(
        agents, scope, variant, claude_mode, project_dir, args.block_id)
    for n in notes:
        say(n)

    results = []
    if not targets:
        say("nothing to install")
    else:
        if not args.yes:
            err("confirmation missing: headless writes need --yes "
                "(--copy-only is exempt)")
            return 5
        results = execute_targets(targets, source, args.block_id, project_dir)
        written = [r for r in results if not r["error"]]
        ok_paths = set()
        touched = []
        for t, r in zip(targets, results):
            if not r["error"]:
                ok_paths.add(t["path"])
                touched.extend(t["agents"])
        if written:
            stale_hint(ok_paths, project_dir, args.block_id)
            restart_hints(touched)
            say("Re-run to update; python install.py --remove to uninstall.")

    if args.json:
        print(json.dumps({
            "block": _block_json(source, args.block_id),
            "targets": results,
            "copies": [],
        }))
    for r in results:
        if r["error"]:
            return 4
    return 0


def cmd_copy(args):
    try:
        source = load_source(args.source, args.sha256)
    except SourceError as exc:
        err(str(exc))
        return 3
    dest_dir = _project_dir_of(args)
    entry = {"target": (dest_dir / "BEHAVE.md").as_posix(),
             "status": "skipped", "error": None}
    code = 0
    try:
        entry["status"] = write_copy(dest_dir, source)
        say("  ok    plain copy %s" % (dest_dir / "BEHAVE.md"))
        say("Plain copies are yours: not tracked by --remove.")
    except TargetError as exc:
        entry["error"] = str(exc)
        err(str(exc))
        code = 4
    if args.json:
        print(json.dumps({
            "block": _block_json(source, args.block_id),
            "targets": [],
            "copies": [entry],
        }))
    return code


def cmd_remove(args):
    requested = _parse_requested_agents(args)
    if not _validate_agents(requested):
        return 2
    project_dir = _project_dir_of(args)
    scope_filter = args.scope if args.scope in ("user", "project", "local") \
        else None
    variant_filter = args.claude_variant or (
        "local" if scope_filter == "local" else None)
    findings = scan_removal(requested or None, scope_filter, variant_filter,
                            project_dir, args.block_id)
    if not findings:
        say("nothing installed; nothing to remove")
        if args.json:
            print(json.dumps({
                "block": _block_json(None, args.block_id),
                "targets": [],
                "copies": [],
            }))
        return 0
    say("Found installed rules:")
    for f in findings:
        say("  %-40s (%s; %s)" % (str(f["path"]), f["agent"], f["mode"]))
    if not args.yes:
        err("confirmation missing: pass --yes to remove (headless mode)")
        return 5
    results = execute_removal(findings, args.block_id)
    if args.json:
        print(json.dumps({
            "block": _block_json(None, args.block_id),
            "targets": results,
            "copies": [],
        }))
    for r in results:
        if r["error"]:
            return 4
    return 0


# ---------------------------------------------------------------------------
# Interactive TUI (P3.3) + EOF guard (P3.2)
# ---------------------------------------------------------------------------


class StdinReader(object):
    """All TUI input flows through one daemon thread (single stdin consumer).

    EOF-guard design (P3.2), with no isatty / mintty sniffing anywhere:
    for zero-argument runs we must distinguish "stdin is already at EOF"
    (pipe, CI, NUL device -> clean exit 1) from "stdin is an interactive
    terminal" (-> run the TUI) without blocking forever and without
    consuming input the TUI needs.  A read(1) on an EOF'd stream returns
    b"" immediately; on an interactive terminal it blocks.  So the read(1)
    happens on a helper thread and we wait briefly:

      - finished with b"" or an error -> EOF -> "no interactive terminal",
        exit 1 (no traceback, no hang)
      - finished with a byte -> data is available (typed ahead or piped);
        the byte is kept and the TUI continues, reading the rest of the
        line(s) through the same thread (input is never lost)
      - still blocked after the timeout -> interactive terminal -> TUI;
        the pending read(1) becomes the first byte of the first answer

    Every later prompt line is served by the same thread, so nothing else
    ever reads stdin.  threading/queue (stdlib) are imported lazily to
    keep the module import surface exactly as specified in the plan.

    All reads use os.read() on the raw file descriptor, never
    sys.stdin.buffer: BufferedReader.read()/readline() hold the buffer
    lock across the blocking console read, and if the daemon thread is
    still blocked there when main() returns, interpreter shutdown cannot
    acquire the lock to finalize stdin -> "Fatal Python error:
    _enter_buffered_busy ... possibly due to daemon threads" followed by
    a segfault (observed on Windows/mintty).  os.read() owns no io lock,
    so a thread blocked in it at exit is harmless.

    P5.2 (TUI rung 2, the arrow-key widget) reconciliation of the
    single-consumer rule with per-key reading: the widget READS THROUGH
    THIS SAME THREAD ("takes over stdin entirely" is impossible here -
    a thread already blocked inside a read cannot be cancelled, and the
    zero-arg EOF probe starts the thread before any prompt exists).  So
    _setup_raw_source() switches THIS thread's key source at
    construction time when stdin is a real TTY/console: termios cbreak
    + os.read(fd, 1) per key on POSIX, msvcrt.getwch inside the thread
    on a real Windows console (os.read on a console returns cooked
    lines only after Enter).  In that raw mode the thread queues decoded
    KEY EVENTS (_decode_key_bytes / _wch_key) instead of lines;
    readline() assembles lines from the same events, echoing manually
    because cbreak/getwch disable terminal echo.  Non-TTY stdin (pipes,
    CI, NUL, the mintty pty) keeps the plain os.read byte loop below
    byte-identical - the EOF-probe semantics the zero-arg run depends
    on - and the widget never engages there: the numbered prompt stays.
    """

    def __init__(self, probe_timeout=None):
        import queue as queue_mod
        import threading
        self._queue = queue_mod.Queue()
        self._probe_eof = False
        self._first = None
        self._pushback = None
        self._raw = False           # P5.2: per-key source active (widget-capable)
        self._no_widget = False     # --ascii: keep _raw, skip the widget
        self._getwch = None         # real Windows console: msvcrt.getwch
        self._restore_attrs = None  # POSIX cbreak: (fd, attrs) to restore
        self._raw_eof = False       # raw source saw EOF (readline bookkeeping)
        try:
            fd = sys.stdin.fileno()
        except (AttributeError, OSError, ValueError):
            fd = None
        self._fd = fd
        if fd is None:
            self._probe_eof = True
            self._thread = None
            return
        # P5.2: the key source must be chosen BEFORE the thread starts;
        # once its first read is blocking it cannot be cancelled or
        # switched from a prompt.
        self._setup_raw_source(fd)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if probe_timeout is not None:
            self._thread.join(probe_timeout)
            if not self._thread.is_alive():
                if self._first in (None, b""):
                    self._probe_eof = True
            # else: read still blocking -> interactive terminal -> TUI

    def _setup_raw_source(self, fd):
        """Switch this reader's thread to a per-key source, real TTYs only.

        POSIX real TTY -> termios cbreak (ICANON and ECHO cleared, ISIG
        kept so Ctrl-C still works), restored by restore().  Windows REAL
        console (kernel32 GetConsoleMode accepts the stdin handle - pipes
        and the mintty pty fail this check, which is the desired safe
        fallback) -> msvcrt.getwch inside the thread: os.read on a
        console returns cooked lines only after Enter.  Any failure in
        here leaves the plain os.read byte loop in charge and disables
        the widget for the whole run - the numbered prompt is the
        contract; never crash, never hang.
        """
        try:
            if not os.isatty(fd):
                return  # pipe / NUL / pty: probe + line semantics must stay
            if os.name == "nt":
                import ctypes
                import msvcrt
                mode = ctypes.c_uint32()
                handle = msvcrt.get_osfhandle(fd)
                if not ctypes.windll.kernel32.GetConsoleMode(
                        handle, ctypes.byref(mode)):
                    return  # not a real console (mintty pty, pipe, redirect)
                self._getwch = msvcrt.getwch
            else:
                import termios
                attrs = termios.tcgetattr(fd)
                raw = list(attrs)
                raw[3] = raw[3] & ~(termios.ICANON | termios.ECHO)
                termios.tcsetattr(fd, termios.TCSANOW, raw)
                self._restore_attrs = (fd, attrs)
            self._raw = True
        except Exception:
            # Raw mode is an opt-in enhancement, never a requirement:
            # on any failure the numbered menu serves this run instead.
            self._getwch = None
            self._restore_attrs = None
            self._raw = False

    def _read_byte(self, fd):
        if self._pushback is not None:
            b, self._pushback = self._pushback, None
            return b
        return os.read(fd, 1)

    def _run(self):
        fd = self._fd
        if fd is None:
            self._queue.put(None)
            return
        if self._raw:
            # Per-key source (real TTY/console only) - see class docstring.
            getwch = self._getwch
            if getwch is not None:
                self._run_keys_console(getwch)
            else:
                self._run_keys_tty(fd)
            return
        pending = b""
        while True:
            try:
                b = self._read_byte(fd)
            except Exception:
                b = b""
            if self._first is None:
                self._first = b
            if b == b"":
                if pending:
                    self._queue.put(pending)
                self._queue.put(None)
                return
            if b == b"\n":
                self._queue.put(pending + b"\n")
                pending = b""
                continue
            if b == b"\r":
                # CRLF is one terminator: peek for the LF half; a lone
                # CR terminates too, and its follower is pushed back.
                try:
                    nxt = self._read_byte(fd)
                except Exception:
                    nxt = b""
                if nxt == b"\n":
                    self._queue.put(pending + b"\r\n")
                    pending = b""
                    continue
                self._queue.put(pending + b"\r")
                pending = b""
                if nxt == b"":
                    self._queue.put(None)
                    return
                self._pushback = nxt
                continue
            pending = pending + b

    def probe_saw_eof(self):
        return self._probe_eof

    def _run_keys_console(self, getwch):
        """Per-key loop for a real Windows console: msvcrt.getwch runs on
        THIS thread (the single stdin consumer); os.read would block
        until Enter because the console hands it cooked lines only.
        Special keys arrive as a \\x00/\\xe0 prefix plus a code byte."""
        codes = {"H": "up", "P": "down", "K": "left", "M": "right",
                 "G": "home", "O": "end", "S": "delete"}
        while True:
            try:
                ch = getwch()
            except Exception:
                ch = "\x1a"
            if self._first is None:
                self._first = b"" if ch == "\x1a" else b"x"
            if ch == "\x1a":  # Ctrl-Z: the console's EOF gesture
                self._queue.put(None)
                return
            if ch in ("\x00", "\xe0"):
                try:
                    code = getwch()
                except Exception:
                    self._queue.put(None)
                    return
                if codes.get(code):
                    self._queue.put(codes[code])
                continue
            self._queue.put(_wch_key(ch))

    def _run_keys_tty(self, fd):
        """Per-key loop for a real POSIX TTY in cbreak: os.read(fd, 1)
        returns each key press unechoed.  Escape sequences are decoded
        after the fact; a select() peek separates a lone Esc from the
        start of a sequence (blocking for the rest of a sequence would
        hang a lone-Esc press)."""
        import select
        buf = b""
        while True:
            try:
                b = os.read(fd, 1)
            except Exception:
                b = b""
            if self._first is None:
                self._first = b
            if b == b"":
                self._queue.put(None)
                return
            buf = buf + b
            events, rest = _decode_key_bytes(buf)
            for ev in events:
                if ev == "eof":  # Ctrl-D byte: cbreak delivers it as data
                    self._queue.put(None)
                    return
                self._queue.put(ev)
            buf = rest
            if buf.startswith(b"\x1b"):
                ready, _, _ = select.select([fd], [], [], 0.05)
                if not ready:
                    # Nothing followed within 50 ms: treat as a lone Esc
                    # and drop the unfinished sequence - re-delivering its
                    # bytes as text would corrupt typed input.
                    self._queue.put("esc")
                    buf = b""

    def raw_keys(self):
        """True when this reader produces per-key events, i.e. stdin was
        a real TTY/console at construction and raw mode held - the only
        condition under which the arrow-key widget may engage.  --ascii
        clears this via _no_widget so EVERY prompt falls back to the
        numbered grammar from the start."""
        return self._raw and not self._no_widget

    def read_key(self):
        """Next key event for the widget; produced by the same daemon
        thread that serves readline() (the 5.2.2 rule: the widget reads
        through the StdinReader, never around it)."""
        if self._raw_eof:
            raise EOFError("stdin is closed")
        ev = self._queue.get()
        if ev is None:
            self._raw_eof = True
            raise EOFError("stdin is closed")
        return ev

    def restore(self):
        """Undo the cbreak switch (POSIX).  run_tui() calls this in a
        finally so the user's terminal is ALWAYS left cooked, whatever
        way the TUI exits."""
        saved = self._restore_attrs
        self._restore_attrs = None
        if saved is None:
            return
        fd, attrs = saved
        try:
            import termios
            termios.tcsetattr(fd, termios.TCSAFLUSH, attrs)
        except Exception as exc:
            err("could not restore terminal mode: %s" % exc)

    def readline(self):
        if not self._raw:
            item = self._queue.get()
            if item is None:
                raise EOFError("stdin is closed")
            return item.decode("utf-8", "replace").rstrip("\r\n")
        # Raw source: assemble a line from key events.  cbreak/getwch
        # disable terminal echo, so typing is echoed here, including
        # backspace; 'q'/'quit' handling stays in _inp, as before.
        buf = ""
        while True:
            if self._raw_eof:
                raise EOFError("stdin is closed")
            ev = self._queue.get()
            if ev is None:
                self._raw_eof = True
                if buf:
                    return buf
                raise EOFError("stdin is closed")
            if ev == "enter":
                sys.stdout.write("\n")
                sys.stdout.flush()
                return buf
            if ev == "backspace":
                if buf:
                    buf = buf[:-1]
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
                continue
            if ev == "interrupt":
                raise KeyboardInterrupt
            ch = " " if ev == "space" else ev
            if isinstance(ch, str) and len(ch) == 1 and ch.isprintable():
                buf = buf + ch
                sys.stdout.write(ch)
                sys.stdout.flush()


class QuitTUI(Exception):
    pass


def _inp(reader, prompt):
    if prompt:
        print(prompt, end="")
        sys.stdout.flush()
    ans = reader.readline()
    if ans.strip().lower() in ("q", "quit"):
        raise QuitTUI()
    return ans


def _confirm(reader, assume_yes, prompt="Proceed? [y/N] (q quits) "):
    if assume_yes:
        print("%sy (--yes)" % prompt)
        return True
    while True:
        ans = _inp(reader, prompt).strip().lower()
        if ans in ("y", "yes"):
            return True
        if ans in ("", "n", "no"):
            return False


def _parse_selection(answer, n):
    """Returns 'default' | 'all' | 'list' | sorted index list | None."""
    answer = answer.strip().lower()
    if answer == "":
        return "default"
    if answer == "a":
        return "all"
    if answer == "l":
        return "list"
    picked = set()
    for tok in answer.split(","):
        tok = tok.strip()
        if not tok:
            continue
        head, dash, tail = tok.partition("-")
        if dash and head.strip().isdigit() and tail.strip().isdigit():
            lo, hi = int(head), int(tail)
            if 1 <= lo <= hi <= n:
                picked.update(range(lo, hi + 1))
                continue
        elif tok.isdigit():
            v = int(tok)
            if 1 <= v <= n:
                picked.add(v)
                continue
        return None
    return sorted(picked) if picked else None


# ---------------------------------------------------------------------------
# Arrow-key widget (P5.2, TUI rung 2) - stdlib only; the numbered prompt
# stays the contract on every path (Esc, non-TTY, or any setup failure).
# ---------------------------------------------------------------------------

# Key events for the widget / raw readline, as produced by the decoders
# below: "up" "down" "left" "right" "home" "end" "pgup" "pgdn" "delete"
# "enter" "esc" "space" "backspace" "interrupt" "eof", or a 1-char
# printable string (typed input).

_ESC_CSI_FINAL = {
    b"A": "up", b"B": "down", b"C": "right", b"D": "left",
    b"H": "home", b"F": "end",
}
_ESC_TILDE = {
    b"1": "home", b"3": "delete", b"4": "end", b"5": "pgup", b"6": "pgdn",
}


def _decode_key_bytes(data):
    """Pure decoder: console byte stream -> (key events, undecoded tail).

    Handles the ANSI grammar a terminal emits in cbreak mode: CSI
    sequences (ESC [ params final), SS3 (ESC O final), and single bytes
    (CR/LF -> enter, DEL/BS -> backspace, space, Ctrl-D -> eof, printable
    ASCII -> the character itself).  The tail is returned undecoded when
    it holds an incomplete escape sequence - the caller decides (via its
    select peek) whether more bytes may follow or it is a lone Esc.
    ESC followed by any other byte yields "esc" plus that byte decoded
    on its own (the Alt-key convention).
    """
    events = []
    i = 0
    n = len(data)
    while i < n:
        b = data[i:i + 1]
        if b == b"\x1b":
            if i + 1 >= n:
                return events, data[i:]
            kind = data[i + 1:i + 2]
            if kind == b"[":
                j = i + 2
                params = b""
                while j < n and (data[j:j + 1].isdigit()
                                 or data[j:j + 1] == b";"):
                    params = params + data[j:j + 1]
                    j += 1
                if j >= n:
                    return events, data[i:]  # sequence not finished yet
                final = data[j:j + 1]
                if params:
                    head = params.split(b";", 1)[0]
                    if final == b"~" and head in _ESC_TILDE:
                        events.append(_ESC_TILDE[head])
                    elif final in _ESC_CSI_FINAL:
                        # modified key (ctrl/shift + arrow etc): the plain
                        # key is the useful reading; modifiers are noise
                        events.append(_ESC_CSI_FINAL[final])
                elif final in _ESC_CSI_FINAL:
                    events.append(_ESC_CSI_FINAL[final])
                elif final == b"~":
                    pass  # unknown tilde code: consumed, nothing to report
                i = j + 1
                continue
            if kind == b"O":
                if i + 2 >= n:
                    return events, data[i:]
                final = data[i + 2:i + 3]
                if final in _ESC_CSI_FINAL:
                    events.append(_ESC_CSI_FINAL[final])
                i = i + 3
                continue
            events.append("esc")
            i += 1  # the byte after ESC is decoded on its own pass
            continue
        if b in (b"\r", b"\n"):
            events.append("enter")
        elif b in (b"\x7f", b"\x08"):
            events.append("backspace")
        elif b == b" ":
            events.append("space")
        elif b == b"\x04":
            events.append("eof")
        else:
            events.append(b.decode("latin-1"))
        i += 1
    return events, b""


def _wch_key(ch):
    """Pure decoder: one msvcrt.getwch character -> key event name."""
    if ch in ("\r", "\n"):
        return "enter"
    if ch == " ":
        return "space"
    if ch in ("\b", "\x7f"):
        return "backspace"
    if ch == "\x1b":
        return "esc"
    if ch == "\x03":
        return "interrupt"
    return ch


def _vt_ok():
    """True when ANSI cursor sequences may drive the widget redraw.

    Windows: try to enable VT processing on the console via kernel32
    SetConsoleMode (ctypes, stdlib); the flag stays enabled for the
    process - it only changes how the console parses our own output.
    POSIX: a real TTY whose TERM is not empty/dumb.  On any failure or
    non-TTY stdout the widget falls back to plain re-printing below the
    previous block; ANSI is never emitted anywhere else.
    """
    try:
        if not sys.stdout.isatty():
            return False
        if os.name == "nt":
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_uint32()
            if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                return False
            enable_vt = 0x0004
            if mode.value & enable_vt:
                return True
            return bool(kernel32.SetConsoleMode(
                handle, mode.value | enable_vt))
        return os.environ.get("TERM", "") not in ("", "dumb")
    except Exception:
        return False


_MENU_AGAIN = object()  # on_text result: redisplay the widget and keep going
_BACK = object()  # wizard back-navigation: Esc walks to the previous
                 # menu (owner canary round 2).  The numbered prompt is
                 # a capability fallback for terminals without arrow
                 # support - never a mid-work mode switch


def _menu_write(vt, prev_count, lines):
    """(Re)draw the widget block - the only place ANSI escapes appear."""
    out = sys.stdout
    if vt and prev_count:
        out.write("\x1b[%dA\r" % prev_count)
    for ln in lines:
        out.write(ln + ("\x1b[K\n" if vt else "\n"))
    out.flush()


def _menu_block(title, rows, pos, checked, multi, footer, buf, status,
                vt=False):
    """The widget's rendered lines: title, item rows with a '>' cursor
    (and [x]/[ ] marks in multi mode), footer, and one status/typed
    line - raw mode has no terminal echo, so the typed buffer must be
    visible here."""
    # (owner, canary round 3 follow-up) Precompute items and width
    # so every VT-cursor bar pads one space past the widest row line
    # in this menu
    items = []
    width = 0
    for i, row in enumerate(rows):
        parts = row.split("\n")
        lead = ">" if i == pos else " "
        if multi:
            item = ["%s [%c] %s" % (lead, "x" if checked[i] else " ",
                                   parts[0])]
        else:
            item = ["%s %s" % (lead, parts[0])]
        for extra in parts[1:]:
            item.append("  " + extra)
        items.append(item)
        width = max(width, max(len(ln) for ln in item) + 1)
    lines = list(title)
    for i, item in enumerate(items):
        if vt and i == pos:
            # reverse video for the whole cursor row (owner, canary
            # round 3): the highlight IS the cursor; the '>' lead stays
            # for non-VT fallbacks where no escape is safe to emit;
            # ljust(width) makes every bar equally wide (owner
            # follow-up: uniform bars please the eye)
            lines.extend("\x1b[7m%s\x1b[27m" % ln.ljust(width)
                         for ln in item)
        else:
            lines.extend(item)
    if footer:
        lines.append(footer)
    tail = status or ("typed: " + buf if buf else "")
    if tail:
        lines.append("  " + tail)
    return lines


def _arrow_menu(reader, title, rows, multi=False, checked=(),
                footer="", on_text=None, empty_msg=None):
    """The rung-2 menu widget: same items as the numbered prompt, plus a
    cursor.  Up/Down move, Space toggles [x] (multi), Enter accepts,
    Backspace edits, printable keys build a typed buffer submitted to
    on_text on Enter (the prompt's EXISTING answer grammar - numbered
    input is never removed), Esc surfaces to the caller, which walks
    BACK to the previous menu.  All keys
    come from reader.read_key(): the StdinReader thread stays the single
    stdin consumer (5.2.2 - see its docstring).

    Returns ("done", value): the cursor index (single choice), the
    checked bool list (multi), or on_text's value for a typed buffer;
    or ("esc", None)."""
    vt = _vt_ok()
    pos = 0
    # multi: keep the CALLER's list object, not a copy - the agent
    # picker's l-expansion mutates rows/checked in place from on_text
    # and relies on this loop seeing the same lists next redraw.
    checked = checked if multi else []
    buf = ""
    status = ""
    prev = 0
    while True:
        block = _menu_block(title, rows, pos, checked, multi, footer,
                            buf, status, vt)
        _menu_write(vt, prev, block)
        prev = len(block)
        key = reader.read_key()
        if key == "up":
            pos = (pos - 1) % len(rows)
        elif key == "down":
            pos = (pos + 1) % len(rows)
        elif key == "enter":
            if buf:
                value = on_text(buf) if on_text is not None else buf
                if value is _MENU_AGAIN:
                    buf = ""
                    status = ""
                    prev = 0  # on_text printed below the block: full redraw
                    continue
                return ("done", value)
            if multi and not any(checked):
                status = empty_msg or "nothing is checked"
                continue
            if multi:
                return ("done", checked)
            return ("done", pos)
        elif key == "esc":
            return ("esc", None)
        elif key == "backspace":
            if buf:
                buf = buf[:-1]
                status = ""
        elif key == "interrupt":
            raise KeyboardInterrupt
        elif key == "space":
            if multi:
                checked[pos] = not checked[pos]
                status = ""
            # single-choice answers never contain a space; drop it
        elif isinstance(key, str) and len(key) == 1 and key.isprintable():
            buf = buf + key
            status = ""
        # every other event (left/right/home/end/...) is a no-op here


def _widget_choice(reader, title, rows, footer, invalid_msg, parse_text,
                   row_keys):
    """Single-choice widget shared by the scope/family/variant prompts:
    Up/Down + Enter picks a row; typed buffers go through parse_text -
    the prompt's existing acceptance grammar (returns the answer, None
    when not a valid answer yet, raises QuitTUI for q/quit).  Returns
    None when the user pressed Esc - the BACK signal: the caller
    walks to the previous menu.

    row_keys is parallel to rows and holds each row's canonical typed
    answer (its (x) letter).  _arrow_menu returns the raw cursor index
    on Enter-with-empty-buffer; mapping that index through parse_text
    HERE means pressing Enter on a row behaves exactly like typing its
    key - one answer grammar, two input surfaces, no second code path
    to drift.  Before this mapping existed the raw index leaked out
    (arrow-selecting "(u)ser" handed the caller the integer 0, which
    never equals "user", so scope routing always fell to project)."""
    def on_text(buf):
        value = parse_text(buf)
        if value is None:
            print(invalid_msg)
            return _MENU_AGAIN
        return value

    kind, value = _arrow_menu(reader, title, rows, footer=footer,
                              on_text=on_text)
    if kind == "esc":
        return None
    if isinstance(value, int):
        value = parse_text(row_keys[value])
    return value


def _target_label(t):
    if t["shared"]:
        # derived, not hardcoded: the family grows and hardcodes went
        # stale before (omp was missing from this label)
        return " / ".join(DISPLAY.get(a, a) for a in FAMILY_IDS)
    return " / ".join([str(DISPLAY.get(a, a)) for a in t["agents"]])


def _preview_targets(targets, project_dir):
    print()
    print("What will change - read this part:")
    print("  Your own instructions keep MORE weight, not less:")
    for t in targets:
        if t["kind"] == "copy":
            print("  - plain copy: %s" % t["path"])
            print("    (no markers, no agent file touched; not tracked by "
                  "--remove; yours to edit)")
            continue
        existed = t["path"].exists()
        if t["mode"] == "drop":
            print("  - %s: new file %s" % (_target_label(t), t["path"]))
            print("    (%s; the rules dir is created if missing)"
                  % DROP_CONSENT)
            if t["drop_agent"] == "cursor":
                print("    (loads only for projects inside your home dir; "
                      "for other projects use project scope)")
        elif existed:
            print("  - %s: rules block AT THE TOP of %s"
                  % (_target_label(t), t["path"]))
            print("    (%s)" % INLINE_CONSENT)
        else:
            print("  - %s: create %s with the rules block"
                  % (_target_label(t), t["path"]))
            print("    (%s)" % INLINE_CONSENT)
        if t["gitignore"]:
            print("    (local file; will be gitignored when a git repo "
                  "exists)")


def _summary_after_install(results, targets, project_dir, block_id,
                           source_label):
    ok_paths = set()
    touched = []
    for t, r in zip(targets, results):
        if not r["error"]:
            ok_paths.add(t["path"])
            touched.extend(t["agents"])
    if any(not r["error"] for r in results):
        stale_hint(ok_paths, project_dir, block_id)
        restart_hints(touched)
        say("Re-run to update; python install.py --remove to uninstall.")


def _agent_menu_row(pos, aid, det_map):
    d = det_map.get(aid)
    path = str(d["paths"][0]) if d else "-"
    return "%2d  %-17s %s" % (pos, DISPLAY[aid], path)


def _pick_agents_widget(reader, tier1, prechecked_ids, det_map, visible):
    """Multi-select widget for the agent picker - and the menu itself:
    the rows ARE the scan report (position, display name, detected
    path or "-"), one list instead of a pre-printed scan dump plus a
    second display-name menu.  The default view is the detected
    agents only; typing l expands the SAME menu in place to every
    supported agent.  visible is the caller's list and is mutated in
    place by that expansion (the in-place protocol below explains
    why).  Enter with an empty buffer submits the checked rows;
    typed buffers go through the same _parse_selection grammar as the
    numbered prompt.  Returns None when the user pressed Esc - the
    caller walks back to the previous menu."""
    pre = set(prechecked_ids)
    rows = [_agent_menu_row(i, a, det_map)
            for i, a in enumerate(visible, 1)]
    checked = [a in pre for a in visible]

    def expand():
        # in-place protocol: rows/checked/visible are rewritten, not
        # rebound, because _arrow_menu holds these exact list objects
        # until it returns; _MENU_AGAIN then forces its full redraw.
        # The cursor index stays valid - the list only ever grows -
        # though it may land on a different row after renumbering.
        visible[:] = tier1
        rows[:] = [_agent_menu_row(i, a, det_map)
                   for i, a in enumerate(visible, 1)]
        checked[:] = [a in pre for a in visible]

    def on_text(buf):
        if buf.strip().lower() in ("q", "quit"):
            raise QuitTUI()
        res = _parse_selection(buf, len(visible))
        if res == "list":
            expand()
            return _MENU_AGAIN
        if res == "all":
            return list(tier1)
        if res == "default":
            if pre:
                return [a for a in tier1 if a in pre]
            print("nothing is pre-checked (no supported agents detected); "
                  "pick numbers or 'a'")
            return _MENU_AGAIN
        if res is None:
            print("not understood: use numbers (1), ranges (1-4), lists "
                  "(1,3), a, l, q, or Enter")
            return _MENU_AGAIN
        return [visible[i - 1] for i in res]

    kind, value = _arrow_menu(
        reader,
        ["Install into which agents?  (Space toggles [x]; Enter = the "
         "checked items;",
         "typed numbers / a / l / q still work; Esc = back to the "
         "previous menu)"],
        rows, multi=True, checked=checked,
        footer="  or type numbers (3), ranges (4-7), lists (2,5), "
               "a, l, q + Enter",
        on_text=on_text,
        empty_msg="nothing is checked: Space toggles rows, or type 'a' + "
                  "Enter for all")
    if kind == "esc":
        return None
    if isinstance(value, list) and value and isinstance(value[0], bool):
        return [a for a, c in zip(visible, value) if c]
    return value


def _pick_agents(reader, prechecked_ids, det_map):
    tier1 = list(TIER1_ORDER)
    # visible is mutated in place by the widget's l-expansion so the
    # rows the user sees and the numbers they type never disagree.
    visible = [a for a in tier1 if a in det_map]
    if not visible:
        # zero detections: an empty widget would crash the cursor
        # cycling (modulo len(rows) of zero rows) - show the full
        # supported list instead
        print("  no supported agents detected; showing all %d"
              % len(tier1))
        visible[:] = tier1
    if reader.raw_keys():
        chosen = _pick_agents_widget(reader, tier1, prechecked_ids,
                                     det_map, visible)
        if chosen is not None:
            return chosen
        # Esc = back to the scope menu.  The numbered loop below runs
        # ONLY when this terminal has no arrow-key support at all - a
        # capability fallback, never a mid-work mode switch.
        return _BACK
    while True:
        n = len(visible)
        for i, a in enumerate(visible, 1):
            print("  " + _agent_menu_row(i, a, det_map))
        ans = _inp(
            reader,
            "Install into which agents? [1-%d] (e.g. 3 or 2,5 or 4-7; "
            "Enter = checked/detected, a = all %d, l = show all, "
            "q = quit)\n> " % (n, len(tier1)))
        res = _parse_selection(ans, n)
        if res == "list":
            visible[:] = tier1
            continue
        if res == "all":
            return list(tier1)
        if res == "default":
            if prechecked_ids:
                return [a for a in tier1 if a in prechecked_ids]
            print("nothing is pre-checked (no supported agents detected); "
                  "pick numbers or 'a'")
            continue
        if res is None:
            print("not understood: use numbers (1), ranges (1-4), lists "
                  "(1,3), a, l, q, or Enter")
            continue
        return [visible[i - 1] for i in res]


def _tui_user(args, reader, source):
    print()
    print("Scanning for installed agents...")
    det = detect_agents()
    det_map = dict((d["id"], d) for d in det)
    # TIER1 agents are never cwd-flagged, so plain det_map membership
    # is the detected test here; the agent menu below IS the report.
    prechecked = set(aid for aid in TIER1_ORDER if aid in det_map)
    others = sorted(d["id"] for d in det
                    if d["id"] not in TIER1_SET and d["id"] != "windsurf")
    if others:
        print("  also detected (no install support yet): %s" % ", ".join(others))
    if "windsurf" in det_map:
        print("  windsurf is a deprecated IDE; upgrade to Devin Desktop "
              "(devin carries the install targets)")
    print("  (%d supported agents - l shows the rest; %d known agents "
          "total, see --list; unsupported ones are reported, never "
          "installed)" % (len(TIER1_ORDER), len(AGENTS)))
    requested = [a for a in _parse_requested_agents(args) if a in TIER1_SET]
    prechecked.update(requested)

    chosen = _pick_agents(reader, prechecked, det_map)
    if chosen is _BACK:
        return _BACK
    if not chosen:
        print("nothing selected; nothing written")
        return 0
    targets, notes = build_install_plan(
        chosen, "user", None, args.claude_mode or "rules", None, args.block_id)
    for nt in notes:
        print(nt)
    if not targets:
        print("nothing to install")
        return 0
    _preview_targets(targets, None)
    print()
    if not _confirm(reader, args.yes):
        print("aborted; nothing written")
        return 0
    results = execute_targets(targets, source, args.block_id, None)
    _summary_after_install(results, targets, None, args.block_id,
                           source.label)
    for r in results:
        if r["error"]:
            return 4
    return 0


def _tui_pick_variant(reader, pre_variant, project_dir):
    sep = os.sep
    entries = [
        ("1", "CLAUDE.md", "inline; project-wide, committed, team-shared",
         project_dir / "CLAUDE.md", "root"),
        ("2", ".claude%sCLAUDE.md" % sep, "inline; documented equivalent of 1",
         project_dir / ".claude" / "CLAUDE.md", "dot-claude"),
        ("3", "CLAUDE.local.md", "inline; loads last (final word); gitignored",
         project_dir / "CLAUDE.local.md", "local"),
        ("4", ".claude%srules%s" % (sep, sep),
         "drop behave.md; same tier as 1/2; cleanest removal",
         project_dir / ".claude" / "rules" / "behave.md", "rules"),
    ]

    def print_menu():
        print("Which Claude file? Official load order (higher = read "
              "earlier each session;")
        print("managed policy and your ~/.claude%sCLAUDE.md come before all "
              "of these):" % sep)
        for num, name, desc, path, var in entries:
            tag = "[exists]" if path.exists() else "[missing]"
            print("  (%s) %-18s - %-46s %s" % (num, name, desc, tag))
        print("  (q) %-18s - exit without changing anything" % "quit")

    pre_map = dict((e[4], e[0]) for e in entries)
    if pre_variant and pre_variant in pre_map:
        print_menu()
        ans = pre_map[pre_variant]
        print("> (%s) (pre-selected via flags)" % ans)
        return pre_variant
    if reader.raw_keys():
        rows = []
        keys = []
        for num, name, desc, path, var in entries:
            tag = "[exists]" if path.exists() else "[missing]"
            rows.append("(%s) %-18s - %-46s %s" % (num, name, desc, tag))
            keys.append(num)
        rows.append("(q) %-18s - exit without changing anything" % "quit")
        keys.append("q")

        def parse_text(buf):
            s = buf.strip()
            if s.lower() in ("q", "quit"):
                raise QuitTUI()
            for num, name, desc, path, var in entries:
                if s.strip("()") == num:
                    return var
            return None

        var = _widget_choice(
            reader,
            ["Which Claude file? Official load order (higher = read "
             "earlier each session;",
             "managed policy and your ~/.claude%sCLAUDE.md come before "
             "all of these):" % sep],
            rows,
            footer="",
            invalid_msg="  pick 1-4 (q quits)",
            parse_text=parse_text,
            row_keys=keys)
        return var  # None = Esc = back to the family menu
    print_menu()
    while True:
        ans = _inp(reader, "> ").strip()
        for num, name, desc, path, var in entries:
            if ans.strip("()") == num:
                return var
        print("  pick 1-4 (q quits)")


def _tui_pick_family(reader, forced=None):
    if forced:
        return forced

    def parse_text(buf):
        ans = buf.strip().lower()
        if ans in ("q", "quit"):
            raise QuitTUI()
        if ans in ("a", "agents.md", "agents"):
            return "a"
        if ans in ("c", "claude.md", "claude"):
            return "c"
        if ans in ("g", "gemini.md", "gemini"):
            return "g"
        if ans in ("j", "just copy", "copy"):
            return "j"
        return None

    rows = [
        "(a)gents.md - one marked block at the TOP of AGENTS.md "
        "(created if missing).\n"
        "                Serves Codex + OpenCode + Pi + Devin + Cursor "
        "+ every other AGENTS.md reader in this repo.\n"
        "                Same consent wording: block first, your own "
        "instructions after - yours keep more weight.",
        "(c)laude.md - the Claude Code family; pick the exact file next.",
        "(g)emini.md - GEMINI.md (Gemini CLI reads ONLY this name).",
        "(j)ust copy - write BEHAVE.md here; nothing else is touched; "
        "use it however you like\n"
        "                (not tracked by --remove).",
        "(q)uit      - exit without changing anything",
    ]
    if reader.raw_keys():
        fam = _widget_choice(
            reader, ["Which family?"], rows,
            footer="",
            invalid_msg="  answer a, c, g, j or q",
            parse_text=parse_text,
            row_keys=["a", "c", "g", "j", "q"])
        return fam  # None = Esc = back to the scope menu
    print("Which family?")
    print("  (a)gents.md - one marked block at the TOP of AGENTS.md "
          "(created if missing).")
    print("                Serves Codex + OpenCode + Pi + Devin + Cursor "
          "+ every other AGENTS.md reader in this repo.")
    print("                Same consent wording: block first, your own "
          "instructions after - yours keep more weight.")
    print("  (c)laude.md - the Claude Code family; pick the exact file next.")
    print("  (g)emini.md - GEMINI.md (Gemini CLI reads ONLY this name).")
    print("  (j)ust copy - write BEHAVE.md here; nothing else is touched; "
          "use it however you like")
    print("                (not tracked by --remove).")
    print("  (q)uit      - exit without changing anything")
    while True:
        ans = _inp(reader, "> ").strip().lower()
        if ans in ("a", "agents.md", "agents"):
            return "a"
        if ans in ("c", "claude.md", "claude"):
            return "c"
        if ans in ("g", "gemini.md", "gemini"):
            return "g"
        if ans in ("j", "just copy", "copy"):
            return "j"
        print("  answer a, c, g, j or q")


def _tui_project(args, reader, source, pre_variant):
    project_dir = _project_dir_of(args)
    print()
    print("Project directory: %s" % project_dir)
    requested = [a for a in _parse_requested_agents(args) if a in TIER1_SET]
    fam_of = {}
    for a in requested:
        if a == "claude-code":
            fam_of[a] = "c"
        elif a in FAMILY_IDS:
            fam_of[a] = "a"
        elif a == "gemini-cli":
            fam_of[a] = "g"
    extras = [a for a in requested if a == "github-copilot"]
    fams = set(fam_of.values())
    forced = fams.pop() if len(fams) == 1 else None

    targets = []
    while True:  # wizard loop: Esc walks BACK one menu (canary round 2)
        fam = _tui_pick_family(reader, forced)
        forced = None
        if fam is None:
            return _BACK
        if fam == "a" and claude_file_exists(project_dir):
            print("  This project already has a Claude file; Claude Code "
                  "ignores AGENTS.md,")
            print("  and no import bridge is offered. Pick the claude "
                  "family to reach Claude Code.")
            continue
        if fam == "a":
            targets.append(_mk_target(
                FAMILY_IDS, project_dir / "AGENTS.md", "inline",
                shared=True))
        elif fam == "c":
            variant = _tui_pick_variant(reader, pre_variant, project_dir)
            if variant is None:
                targets = []
                continue  # Esc at the variant menu: back to family
            p, m = claude_project_target(variant, project_dir)
            t = _mk_target(["claude-code"], p, m,
                           drop_agent="claude-code")
            if variant == "local":
                t["gitignore"] = True
            targets.append(t)
        elif fam == "g":
            targets.append(_mk_target(
                ["gemini-cli"], project_dir / "GEMINI.md", "inline"))
        elif fam == "j":
            targets.append(_mk_target([], project_dir / "BEHAVE.md", "copy",
                                      kind="copy"))
        break
    for a in extras:
        targets.append(_mk_target(
            ["github-copilot"],
            project_dir / ".github" / "copilot-instructions.md",
            "inline"))

    _preview_targets(targets, project_dir)
    print()
    if not _confirm(reader, args.yes):
        print("aborted; nothing written")
        return 0

    copy_targets = [t for t in targets if t["kind"] == "copy"]
    real_targets = [t for t in targets if t["kind"] != "copy"]
    results = []
    if real_targets:
        results = execute_targets(real_targets, source, args.block_id,
                                  project_dir)
    for t in copy_targets:
        try:
            status = write_copy(
                project_dir, source,
                confirm=lambda: _confirm(
                    reader, args.yes,
                    "existing BEHAVE.md differs from the source; "
                    "overwrite? [y/N] (q quits) "))
            print("  ok    plain copy %s (%s)" % (t["path"], status))
            print("  Plain copies are yours: not tracked by --remove.")
            results.append({"agent": "", "target": t["path"].as_posix(),
                            "mode": "copy", "status": status,
                            "warning": None, "error": None})
        except TargetError as exc:
            err(str(exc))
            results.append({"agent": "", "target": t["path"].as_posix(),
                            "mode": "copy", "status": "skipped",
                            "warning": None, "error": str(exc)})
    _summary_after_install(results, real_targets, project_dir,
                           args.block_id, source.label)
    for r in results:
        if r["error"]:
            return 4
    return 0


def _tui_remove(args, reader):
    project_dir = _project_dir_of(args)
    requested = _parse_requested_agents(args)
    if not _validate_agents(requested):
        return 2
    findings = scan_removal(requested or None, None, None, project_dir,
                            args.block_id)
    print()
    if not findings:
        print("nothing installed; nothing to remove")
        return 0
    print("Found installed rules:")
    for f in findings:
        print("  %-40s (%s; %s)" % (str(f["path"]), f["agent"], f["mode"]))
    print()
    if not _confirm(reader, args.yes, "Remove these? [y/N] (q quits) "):
        print("aborted; nothing removed")
        return 0
    results = execute_removal(findings, args.block_id)
    for r in results:
        if r["error"]:
            return 4
    return 0


def run_tui(args, zero_args=False):
    OUT.quiet = False
    OUT.json_mode = False
    reader = StdinReader(probe_timeout=0.3 if zero_args else None)
    reader._no_widget = getattr(args, "ascii", False)
    if zero_args and reader.probe_saw_eof():
        print("no interactive terminal; run --help for parameters or pass "
              "flags for headless")
        return 1
    try:
        rc = _tui_flow(args, reader)
        if not isinstance(rc, int):
            # _BACK sentinel: unreachable by construction (the
            # _tui_flow wizard loop re-asks scope instead of
            # returning it), but a sentinel must never reach
            # sys.exit - guaranteed here for the type checker
            # and any future refactor alike
            rc = 0
        return rc
    except QuitTUI:
        print()
        print("quit; nothing written")
        return 0
    except EOFError:
        print()
        print("aborted: no input available; nothing written")
        return 1
    except KeyboardInterrupt:
        # Ctrl-C: ISIG still delivers the signal on POSIX cbreak; the
        # Windows console path delivers it as an "interrupt" key event.
        print()
        print("interrupted; nothing written")
        return 1
    finally:
        # P5.2: leave a cbreak'd terminal cooked on EVERY exit path.
        reader.restore()


def _tui_flow(args, reader):
    if args.remove:
        return _tui_remove(args, reader)
    try:
        source = load_source(args.source, args.sha256)
    except SourceError as exc:
        err(str(exc))
        return 3
    print("BEHAVE.md installer  (sha256 %s..., %s; source: %s)"
          % (source.sha256_short, source.size_label, source.label))
    pre_scope = None
    if args.scope in ("user", "project", "local"):
        pre_scope = args.scope
    while True:
        # the scope ask lives INSIDE the wizard loop so _BACK
        # re-renders this menu - the wizard start - instead of
        # silently re-dispatching the previous branch
        if pre_scope is None:
            if reader.raw_keys():

                def parse_scope(buf):
                    a = buf.strip().lower()
                    if a in ("q", "quit"):
                        raise QuitTUI()
                    if a in ("u", "user"):
                        return "user"
                    if a in ("p", "proj", "project"):
                        return "project"
                    return None

                pre_scope = _widget_choice(
                    reader,
                    ["Where should the rules apply?"],
                    ["(u)ser    - all your projects, into the agents you pick",
                     "(p)roject - this directory only (cwd: %s)" % Path.cwd(),
                     "(q)uit    - exit without changing anything"],
                    footer="",
                    invalid_msg="  answer u, p or q",
                    parse_text=parse_scope,
                    row_keys=["u", "p", "q"])
                if pre_scope is None:
                    # Esc at the root menu == (q)uit (owner, canary
                    # round 3): nothing lies before this menu, so
                    # back-navigation and quit are the same act here
                    raise QuitTUI()
            if pre_scope is None:
                print()
                print("Where should the rules apply?")
                print("  (u)ser    - all your projects, into the agents you pick")
                print("  (p)roject - this directory only (cwd: %s)" % Path.cwd())
                print("  (q)uit    - exit without changing anything")
                while True:
                    a = _inp(reader, "> ").strip().lower()
                    if a in ("u", "user"):
                        pre_scope = "user"
                        break
                    if a in ("p", "proj", "project"):
                        pre_scope = "project"
                        break
                    print("  answer u, p or q")
        if pre_scope == "user":
            r = _tui_user(args, reader, source)
        else:
            pre_variant = ("local" if pre_scope == "local"
                           else args.claude_variant)
            r = _tui_project(args, reader, source, pre_variant)
        if r is _BACK:
            # Esc walked all the way back: re-ask the scope menu (the
            # wizard start), never a swap to the numbered prompt
            pre_scope = None
            continue
        return r


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    has_help = any(a in ("-h", "--help") for a in argv)
    if has_help and len(argv) > 1:
        print("usage error: cannot combine --help with other parameters",
              file=sys.stderr)
        return 1
    args = build_parser().parse_args(argv)

    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", args.block_id):
        err("usage error: --block-id must be alphanumeric with ._- "
            "(got '%s')" % args.block_id)
        return 1

    if args.interactive or args.ascii:
        # --ascii implies the TUI (owner, canary round 3 follow-up):
        # it picks the navigation STYLE, so alone it must launch
        # the same interactive flow --interactive does
        return run_tui(args, zero_args=False)
    if not argv:
        return run_tui(args, zero_args=True)
    OUT.quiet = args.quiet
    OUT.json_mode = args.json
    if args.list:
        return cmd_list(args)
    if args.remove:
        return cmd_remove(args)
    if args.copy_only:
        return cmd_copy(args)
    return cmd_install(args)


if __name__ == "__main__":
    sys.exit(main())
