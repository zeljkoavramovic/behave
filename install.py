# Detection table derived from vercel-labs/skills
# https://github.com/vercel-labs/skills - Copyright (c) 2026 Vercel, Inc.
# Licensed under the MIT License; full text follows.
#
# MIT License
#
# Copyright (c) 2026 Vercel, Inc.
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
# flags: "cwd" (has cwd markers), "multi" (multi-marker agent),
#        "content" (package.json content check), "never" (pseudo entry),
#        "deprecated" (report-only deprecation notice)
AGENTS: List[Dict[str, Any]] = [
    {"id": "aider-desk", "env": None, "markers": [("h", ".aider-desk")], "tier": 3, "flags": ()},
    {"id": "amp", "env": None, "markers": [("x", "amp")], "tier": 2, "flags": ()},
    {"id": "antigravity", "env": None, "markers": [("h", ".gemini/antigravity")], "tier": 3, "flags": ()},
    {"id": "antigravity-cli", "env": None, "markers": [("h", ".gemini/antigravity-cli")], "tier": 3, "flags": ()},
    {"id": "astrbot", "env": None, "markers": [("c", "data/skills"), ("h", ".astrbot")], "tier": 3, "flags": ("cwd",)},
    {"id": "autohand-code", "env": "AUTOHAND_HOME", "markers": [("h", ".autohand")], "tier": 3, "flags": ()},
    {"id": "augment", "env": None, "markers": [("h", ".augment")], "tier": 2, "flags": ()},
    {"id": "bob", "env": None, "markers": [("h", ".bob")], "tier": 3, "flags": ()},
    {"id": "claude-code", "env": "CLAUDE_CONFIG_DIR", "markers": [("h", ".claude")], "tier": 1, "flags": ()},
    {"id": "openclaw", "env": None, "markers": [("h", ".openclaw"), ("h", ".clawdbot"), ("h", ".moltbot")], "tier": 3, "flags": ("multi",)},
    {"id": "cline", "env": None, "markers": [("h", ".cline")], "tier": 2, "flags": ()},
    {"id": "codearts-agent", "env": None, "markers": [("h", ".codeartsdoer")], "tier": 3, "flags": ()},
    {"id": "codebuddy", "env": None, "markers": [("c", ".codebuddy"), ("h", ".codebuddy")], "tier": 3, "flags": ("cwd",)},
    {"id": "codemaker", "env": None, "markers": [("h", ".codemaker")], "tier": 3, "flags": ()},
    {"id": "codestudio", "env": None, "markers": [("h", ".codestudio")], "tier": 3, "flags": ()},
    {"id": "codex", "env": "CODEX_HOME", "markers": [("h", ".codex"), ("p", "/etc/codex")], "tier": 1, "flags": ()},
    {"id": "command-code", "env": None, "markers": [("h", ".commandcode")], "tier": 3, "flags": ()},
    {"id": "continue", "env": None, "markers": [("c", ".continue"), ("h", ".continue")], "tier": 3, "flags": ("cwd",)},
    {"id": "cortex", "env": None, "markers": [("h", ".snowflake/cortex")], "tier": 3, "flags": ()},
    {"id": "crush", "env": None, "markers": [("h", ".config/crush")], "tier": 2, "flags": ()},
    {"id": "cursor", "env": None, "markers": [("h", ".cursor")], "tier": 1, "flags": ()},
    {"id": "deepagents", "env": None, "markers": [("h", ".deepagents")], "tier": 2, "flags": ()},
    {"id": "devin", "env": None, "markers": [("x", "devin"), ("a", "devin")], "tier": 1, "flags": ()},
    {"id": "dexto", "env": None, "markers": [("h", ".dexto")], "tier": 3, "flags": ()},
    {"id": "droid", "env": None, "markers": [("h", ".factory")], "tier": 2, "flags": ()},
    {"id": "eve", "env": None, "markers": [], "tier": 3, "flags": ("content", "cwd")},
    {"id": "firebender", "env": None, "markers": [("h", ".firebender")], "tier": 3, "flags": ()},
    {"id": "forgecode", "env": None, "markers": [("h", ".forge")], "tier": 3, "flags": ()},
    {"id": "gemini-cli", "env": None, "markers": [("h", ".gemini")], "tier": 1, "flags": ()},
    {"id": "github-copilot", "env": None, "markers": [("h", ".copilot")], "tier": 1, "flags": ()},
    {"id": "goose", "env": None, "markers": [("x", "goose")], "tier": 2, "flags": ()},
    {"id": "grok", "env": "GROK_HOME", "markers": [("h", ".grok")], "tier": 3, "flags": ()},
    {"id": "hermes-agent", "env": "HERMES_HOME", "markers": [("h", ".hermes")], "tier": 3, "flags": ()},
    {"id": "inference-sh", "env": None, "markers": [("h", ".inferencesh")], "tier": 3, "flags": ()},
    {"id": "jazz", "env": None, "markers": [("h", ".jazz"), ("c", ".jazz")], "tier": 3, "flags": ()},
    {"id": "junie", "env": None, "markers": [("h", ".junie")], "tier": 2, "flags": ()},
    {"id": "iflow-cli", "env": None, "markers": [("h", ".iflow")], "tier": 3, "flags": ()},
    {"id": "kilo", "env": None, "markers": [("h", ".kilocode")], "tier": 2, "flags": ()},
    {"id": "kimchi", "env": None, "markers": [("h", ".config/kimchi")], "tier": 3, "flags": ()},
    {"id": "kimi-code-cli", "env": None, "markers": [("h", ".kimi-code"), ("h", ".kimi")], "tier": 3, "flags": ("multi",)},
    {"id": "kiro-cli", "env": None, "markers": [("h", ".kiro")], "tier": 3, "flags": ()},
    {"id": "kode", "env": None, "markers": [("h", ".kode")], "tier": 3, "flags": ()},
    {"id": "lingma", "env": None, "markers": [("h", ".lingma")], "tier": 3, "flags": ()},
    {"id": "loaf", "env": None, "markers": [("h", ".loaf")], "tier": 3, "flags": ()},
    {"id": "mcpjam", "env": None, "markers": [("h", ".mcpjam")], "tier": 3, "flags": ()},
    {"id": "minimax-code", "env": None, "markers": [("h", ".minimax"), ("p", "/Applications/MiniMax Code.app")], "tier": 3, "flags": ("multi",)},
    {"id": "mistral-vibe", "env": "VIBE_HOME", "markers": [("h", ".vibe")], "tier": 3, "flags": ()},
    {"id": "moxby", "env": None, "markers": [("h", ".moxby")], "tier": 3, "flags": ()},
    {"id": "mux", "env": None, "markers": [("h", ".mux")], "tier": 3, "flags": ()},
    {"id": "opencode", "env": None, "markers": [("x", "opencode")], "tier": 1, "flags": ()},
    {"id": "openhands", "env": None, "markers": [("h", ".openhands")], "tier": 2, "flags": ()},
    {"id": "ona", "env": None, "markers": [("h", ".ona")], "tier": 2, "flags": ()},
    {"id": "pi", "env": None, "markers": [("h", ".pi/agent")], "tier": 1, "flags": ()},
    {"id": "posit-assistant", "env": None, "markers": [("h", ".posit/assistant"), ("h", ".positai")], "tier": 3, "flags": ("multi",)},
    {"id": "qoder", "env": None, "markers": [("h", ".qoder")], "tier": 3, "flags": ()},
    {"id": "qoder-cn", "env": None, "markers": [("h", ".qoder-cn")], "tier": 3, "flags": ()},
    {"id": "qwen-code", "env": None, "markers": [("h", ".qwen")], "tier": 3, "flags": ()},
    {"id": "replit", "env": None, "markers": [("c", ".replit")], "tier": 3, "flags": ("cwd",)},
    {"id": "reasonix", "env": None, "markers": [("h", ".reasonix")], "tier": 3, "flags": ()},
    {"id": "rovodev", "env": None, "markers": [("h", ".rovodev")], "tier": 3, "flags": ()},
    {"id": "roo", "env": None, "markers": [("h", ".roo")], "tier": 2, "flags": ()},
    {"id": "tabnine-cli", "env": None, "markers": [("h", ".tabnine")], "tier": 3, "flags": ()},
    {"id": "terramind", "env": None, "markers": [("h", ".terramind")], "tier": 3, "flags": ()},
    {"id": "tinycloud", "env": None, "markers": [("h", ".tinycloud")], "tier": 3, "flags": ()},
    {"id": "trae", "env": None, "markers": [("h", ".trae")], "tier": 3, "flags": ()},
    {"id": "trae-cn", "env": None, "markers": [("h", ".trae-cn")], "tier": 3, "flags": ()},
    {"id": "warp", "env": None, "markers": [("h", ".warp")], "tier": 2, "flags": ()},
    {"id": "windsurf", "env": None, "markers": [("h", ".codeium/windsurf")], "tier": 3, "flags": ("deprecated",)},
    {"id": "zed", "env": None, "markers": [("x", "zed"), ("a", "Zed"), ("f", "zed")], "tier": 2, "flags": ()},
    {"id": "zcode", "env": None, "markers": [("h", ".zcode"), ("p", "/Applications/ZCode.app")], "tier": 3, "flags": ("multi",)},
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

# Tier-1 install targets (INSTALLER-PLAN section 6): the 8 v1 agents.
TIER1_ORDER = [
    "claude-code", "codex", "opencode", "devin", "cursor",
    "gemini-cli", "github-copilot", "pi",
]
TIER1_SET = set(TIER1_ORDER)
FAMILY_IDS = ["codex", "opencode", "pi", "devin"]  # shared ./AGENTS.md block
DISPLAY = {
    "claude-code": "Claude Code",
    "codex": "Codex",
    "opencode": "OpenCode",
    "pi": "Pi",
    "devin": "Devin",
    "cursor": "Cursor",
    "gemini-cli": "Gemini CLI",
    "github-copilot": "GitHub Copilot",
}
# Drop-file frontmatter per agent (INSTALLER-PLAN section 4.2).
DROP_FRONTMATTER = {
    "claude-code": "",
    "cursor": "---\nalwaysApply: true\n---\n",
    "devin": "---\ntrigger: always_on\n---\n",
    "github-copilot": '---\napplyTo: "**"\n---\n',
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


def load_source(source_arg):
    """Resolution order: --source URL|PATH, bundled ./BEHAVE.md, CANONICAL_URL."""
    if source_arg:
        if "://" in source_arg:
            return Source(_fetch_url(source_arg), source_arg)
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
        try:
            data = bundled.read_bytes()
        except OSError as exc:
            raise SourceError("failed to read bundled %s: %s" % (bundled, exc))
        if data:
            return Source(data, "bundled %s" % bundled.name)
    return Source(_fetch_url(CANONICAL_URL), CANONICAL_URL)


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


def block_content_sha_short(path, block_id):
    """Short sha256 of a marked block's body (for the stale hint)."""
    bid = re.escape(block_id.encode("ascii"))
    pat = re.compile(
        b"<!-- BEGIN " + bid + b" [^\r\n]*-->\r?\n(.*?)<!-- END " + bid + b" -->",
        re.DOTALL,
    )
    try:
        raw = path.read_bytes()
    except OSError:
        return "?"
    m = pat.search(raw)
    if not m:
        return "?"
    return hashlib.sha256(m.group(1)).hexdigest()[:7]


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


# ---------------------------------------------------------------------------
# Plain copy engine (P2.6, D3)
# ---------------------------------------------------------------------------


def write_copy(dest_dir, source):
    """Writes BEHAVE.md; provenance guard; returns 'created'|'updated'."""
    dest = dest_dir / "BEHAVE.md"
    existed = dest.exists()
    if existed:
        try:
            cur = dest.read_bytes()
        except OSError as exc:
            raise TargetError("cannot read %s: %s" % (dest, exc))
        if hashlib.sha256(cur).hexdigest() != source.sha256:
            raise TargetError(
                "existing BEHAVE.md does not match the source; "
                "rename it or pass --source")
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
    if "cursor" in agents:
        targets.append(_mk_target(
            ["cursor"], project_dir / ".cursor" / "rules" / "behave.mdc",
            "drop", drop_agent="cursor"))
    if "gemini-cli" in agents:
        targets.append(_mk_target(
            ["gemini-cli"], project_dir / "GEMINI.md", "inline"))
    if "github-copilot" in agents:
        targets.append(_mk_target(
            ["github-copilot"],
            project_dir / ".github" / "copilot-instructions.md", "inline"))
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
    if [a for a in ("codex", "opencode", "pi", "devin") if a in agents]:
        lines.append("  - Codex / OpenCode / Pi / Devin: restart them "
                     "(Codex rebuilds its chain every run).")
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
        short = block_content_sha_short(f["path"], block_id)
        say("also found: %s (sha %s); run --remove to clean"
            % (f["path"], short))
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
        for d in devin_dirs():
            add(d / "AGENTS.md", "inline", ["devin"])
        add(home_base() / ".cursor" / "rules" / "behave.mdc", "drop",
            ["cursor"], drop_agent="cursor")
        add(home_base() / ".gemini" / "GEMINI.md", "inline", ["gemini-cli"])
        add(home_base() / ".copilot" / "instructions" / "behave.instructions.md",
            "drop", ["github-copilot"], drop_agent="github-copilot")

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
        add(d / ".cursor" / "rules" / "behave.mdc", "drop", ["cursor"],
            drop_agent="cursor")
        add(d / ".github" / "copilot-instructions.md", "inline",
            ["github-copilot"])
        add(d / "GEMINI.md", "inline", ["gemini-cli"])

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
        source = load_source(args.source)
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
        source = load_source(args.source)
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
    """

    def __init__(self, probe_timeout=None):
        import queue as queue_mod
        import threading
        self._queue = queue_mod.Queue()
        self._probe_eof = False
        self._first = None
        buf = getattr(sys.stdin, "buffer", None)
        self._buf = buf
        if buf is None:
            self._probe_eof = True
            self._thread = None
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if probe_timeout is not None:
            self._thread.join(probe_timeout)
            if not self._thread.is_alive():
                if self._first in (None, b""):
                    self._probe_eof = True
            # else: read still blocking -> interactive terminal -> TUI

    def _run(self):
        buf = self._buf
        if buf is None:
            self._queue.put(None)
            return
        try:
            first = buf.read(1)
        except Exception:
            first = b""
        self._first = first
        if first == b"":
            self._queue.put(None)
            return
        pending = first
        while True:
            try:
                chunk = buf.readline()
            except Exception:
                chunk = b""
            if chunk == b"":
                if pending:
                    self._queue.put(pending)
                self._queue.put(None)
                return
            pending = pending + chunk
            if pending.endswith(b"\n") or pending.endswith(b"\r"):
                self._queue.put(pending)
                pending = b""

    def probe_saw_eof(self):
        return self._probe_eof

    def readline(self):
        item = self._queue.get()
        if item is None:
            raise EOFError("stdin is closed")
        return item.decode("utf-8", "replace").rstrip("\r\n")


def _inp(reader, prompt):
    if prompt:
        print(prompt, end="")
        sys.stdout.flush()
    return reader.readline()


def _confirm(reader, assume_yes, prompt="Proceed? [y/N] "):
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


def _target_label(t):
    if t["shared"]:
        return "Codex / OpenCode / Pi / Devin"
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


def _pick_agents(reader, prechecked_ids):
    tier1 = list(TIER1_ORDER)
    n = len(tier1)
    while True:
        ans = _inp(
            reader,
            "Install into which agents? [1-%d] (Enter = all detected, "
            "a = all known, l = list)\n> " % n)
        res = _parse_selection(ans, n)
        if res == "list":
            for i, ag in enumerate(AGENTS, 1):
                print("  %2d  %s" % (i, ag["id"]))
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
                  "(1,3), a, l, or Enter")
            continue
        return [tier1[i - 1] for i in res]


def _tui_user(args, reader, source):
    print()
    print("Scanning for installed agents...")
    det = detect_agents()
    det_map = dict((d["id"], d) for d in det)
    prechecked = set()
    for i, aid in enumerate(TIER1_ORDER, 1):
        d = det_map.get(aid)
        detected = d is not None and not d["cwd_only"]
        mark = "[x]" if detected else "[ ]"
        path = str(d["paths"][0]) if d else "-"
        print("  %s %2d  %-17s %s" % (mark, i, DISPLAY[aid], path))
        if detected:
            prechecked.add(aid)
    others = sorted(d["id"] for d in det
                    if d["id"] not in TIER1_SET and d["id"] != "windsurf")
    if others:
        print("  also detected (no install support yet): %s" % ", ".join(others))
    if "windsurf" in det_map:
        print("  windsurf is a deprecated IDE; upgrade to Devin Desktop "
              "(devin carries the install targets)")
    print("  (%d known agents total - l lists all; unsupported ones are "
          "reported, never installed)" % len(AGENTS))
    requested = [a for a in _parse_requested_agents(args) if a in TIER1_SET]
    for a in requested:
        prechecked.add(a)

    chosen = _pick_agents(reader, prechecked)
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
    print("Which Claude file? Official load order (higher = read earlier "
          "each session;")
    print("managed policy and your ~/.claude%sCLAUDE.md come before all of "
          "these):" % sep)
    for num, name, desc, path, var in entries:
        tag = "[exists]" if path.exists() else "[missing]"
        print("  %s  %-18s %-46s %s" % (num, name, desc, tag))
    pre_map = dict((e[4], e[0]) for e in entries)
    if pre_variant and pre_variant in pre_map:
        ans = pre_map[pre_variant]
        print("> %s (pre-selected via flags)" % ans)
        return pre_variant
    while True:
        ans = _inp(reader, "> ").strip()
        for num, name, desc, path, var in entries:
            if ans == num:
                return var
        print("  pick 1-4")


def _tui_pick_family(reader, forced=None):
    if forced:
        return forced
    print("Which family?")
    print("  (a)gents.md - one marked block at the TOP of AGENTS.md "
          "(created if missing).")
    print("                Serves Codex + OpenCode + Pi + Devin + every "
          "other AGENTS.md reader in this repo.")
    print("                Same consent wording: block first, your own "
          "instructions after - yours keep more weight.")
    print("  (c)laude.md - the Claude Code family; pick the exact file next.")
    print("  (g)emini.md - GEMINI.md (Gemini CLI reads ONLY this name).")
    print("  (j)ust copy - write BEHAVE.md here; nothing else is touched; "
          "use it however you like")
    print("                (not tracked by --remove).")
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
        print("  answer a, c, g or j")


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
    extras = [a for a in requested if a in ("cursor", "github-copilot")]
    fams = set(fam_of.values())
    forced = fams.pop() if len(fams) == 1 else None

    while True:
        fam = _tui_pick_family(reader, forced)
        forced = None
        if fam != "a" or not claude_file_exists(project_dir):
            break
        print("  This project already has a Claude file; Claude Code "
              "ignores AGENTS.md,")
        print("  and no import bridge is offered. Pick the claude family "
              "to reach Claude Code.")

    targets = []
    if fam == "a":
        targets.append(_mk_target(
            FAMILY_IDS, project_dir / "AGENTS.md", "inline", shared=True))
    elif fam == "c":
        variant = _tui_pick_variant(reader, pre_variant, project_dir)
        p, m = claude_project_target(variant, project_dir)
        t = _mk_target(["claude-code"], p, m, drop_agent="claude-code")
        if variant == "local":
            t["gitignore"] = True
        targets.append(t)
    elif fam == "g":
        targets.append(_mk_target(
            ["gemini-cli"], project_dir / "GEMINI.md", "inline"))
    elif fam == "j":
        targets.append(_mk_target([], project_dir / "BEHAVE.md", "copy",
                                  kind="copy"))
    for a in extras:
        if a == "cursor":
            targets.append(_mk_target(
                ["cursor"], project_dir / ".cursor" / "rules" / "behave.mdc",
                "drop", drop_agent="cursor"))
        elif a == "github-copilot":
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
            status = write_copy(project_dir, source)
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
    if not _confirm(reader, args.yes, "Remove these? [y/N] "):
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
    if zero_args and reader.probe_saw_eof():
        print("no interactive terminal; run --help for parameters or pass "
              "flags for headless")
        return 1
    try:
        return _tui_flow(args, reader)
    except EOFError:
        print()
        print("aborted: no input available; nothing written")
        return 1


def _tui_flow(args, reader):
    if args.remove:
        return _tui_remove(args, reader)
    try:
        source = load_source(args.source)
    except SourceError as exc:
        err(str(exc))
        return 3
    print("BEHAVE.md installer  (sha256 %s..., %s; source: %s)"
          % (source.sha256_short, source.size_label, source.label))
    pre_scope = None
    if args.scope in ("user", "project", "local"):
        pre_scope = args.scope
    if pre_scope is None:
        print()
        print("Where should the rules apply?")
        print("  (u)ser    - all your projects, into the agents you pick")
        print("  (p)roject - this directory only (cwd: %s)" % Path.cwd())
        while True:
            a = _inp(reader, "> ").strip().lower()
            if a in ("u", "user"):
                pre_scope = "user"
                break
            if a in ("p", "proj", "project"):
                pre_scope = "project"
                break
            print("  answer u or p")
    if pre_scope == "user":
        return _tui_user(args, reader, source)
    pre_variant = ("local" if pre_scope == "local" else args.claude_variant)
    return _tui_project(args, reader, source, pre_variant)


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

    if args.interactive:
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
