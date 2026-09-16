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

import sys

# before the other imports: on Py2, urllib.request dies first; and this
# can only fire while the whole file stays Py2-parseable (no f-strings)
if sys.version_info < (3, 6):
    sys.exit("error: Python 3.6 or newer required, you have %s"
             % sys.version.split()[0])

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
from typing import Any, Callable, Dict, List, Union

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
# Agent detection table (INSTALLER-PLAN section 5)
# ---------------------------------------------------------------------------
# Marker bases:
#   "h" home dir (agent root; env override replaces the whole agent dir)
#   "x" XDG config base ($XDG_CONFIG_HOME or ~/.config)
#   "a" %APPDATA%
#   "f" $FLATPAK_XDG_CONFIG_HOME
#   "p" absolute path (as-is)
AGENTS: List[Dict[str, Any]] = [
    {"id": "aider-desk", "env": None, "markers": [("h", ".aider-desk")]},
    {"id": "amp", "env": None, "markers": [("x", "amp")]},
    {"id": "antigravity", "env": None, "markers": [("h", ".gemini/antigravity")]},
    {"id": "antigravity-cli", "env": None, "markers": [("h", ".gemini/antigravity-cli")]},
    {"id": "augment", "env": None, "markers": [("h", ".augment")]},
    {"id": "bob", "env": None, "markers": [("h", ".bob")]},
    {"id": "claude-code", "env": "CLAUDE_CONFIG_DIR", "markers": [("h", ".claude")]},
    {"id": "openclaw", "env": None, "markers": [("h", ".openclaw"), ("h", ".clawdbot"), ("h", ".moltbot")]},
    {"id": "cline", "env": None, "markers": [("h", ".cline")]},
    # codebuff: the CLI writes ~/.config/manicode (legacy vendor name;
    # rebranding traces codebuff -> freebuff in the source);
    # FREEBUFF_CONFIG_DIR exists but the plain path is used, and
    # ~/.codebuff is NOT written - x-marker like opencode/crush.
    {"id": "codebuff", "env": None, "markers": [("x", "manicode")]},
    {"id": "codewhale", "env": "CODEWHALE_HOME", "markers": [("h", ".codewhale")]},
    {"id": "codex", "env": "CODEX_HOME", "markers": [("h", ".codex"), ("p", "/etc/codex")]},
    {"id": "command-code", "env": None, "markers": [("h", ".commandcode")]},
    {"id": "cortex", "env": None, "markers": [("h", ".snowflake/cortex")]},
    {"id": "crush", "env": None, "markers": [("h", ".config/crush")]},
    {"id": "cursor", "env": None, "markers": [("h", ".cursor")]},
    {"id": "deepagents", "env": None, "markers": [("h", ".deepagents")]},
    # deepseek-harness: home = $DSH_HOME || ~/.dsh (home-paths
    # DSH_HOME_DIR_NAME; homedir()/.dsh everywhere, no APPDATA variant);
    # DSH_HOME is registered as a detection override only - install
    # uses the plain path (reasonix/qwen-code precedent).
    {"id": "deepseek-harness", "env": "DSH_HOME", "markers": [("h", ".dsh")]},
    {"id": "devin", "env": None, "markers": [("x", "devin"), ("a", "devin")]},
    {"id": "droid", "env": None, "markers": [("h", ".factory")]},
    # forgecode: FORGE_CONFIG override exists but detection/install use
    # the plain ~/.forge path; the legacy ~/forge dir is presence-only,
    # not a marker.
    {"id": "forgecode", "env": None, "markers": [("h", ".forge")]},
    {"id": "gemini-cli", "env": None, "markers": [("h", ".gemini")]},
    {"id": "github-copilot", "env": None, "markers": [("h", ".copilot")]},
    # goose: the ("a", "Block/goose") marker matches the install target -
    # Windows detection missed goose while it was XDG-only (goose stores
    # config under %APPDATA%\Block\goose there, not under ~/.config).
    {"id": "goose", "env": None, "markers": [("x", "goose"), ("a", "Block/goose")]},
    {"id": "grok", "env": "GROK_HOME", "markers": [("h", ".grok")]},
    # hermes-agent: HERMES_HOME override exists but detection/install
    # use the plain ~/.hermes path (qwen-code precedent); the Windows
    # native default is %LOCALAPPDATA%\hermes - marker stays ~/.hermes.
    {"id": "hermes-agent", "env": "HERMES_HOME", "markers": [("h", ".hermes")]},
    {"id": "jcode", "env": "JCODE_HOME", "markers": [("h", ".jcode")]},
    {"id": "junie", "env": None, "markers": [("h", ".junie")]},
    {"id": "kilo", "env": None, "markers": [("h", ".kilocode")]},
    # kimchi: entry.ts hardcodes homedir()/.config/kimchi/harness and
    # force-sets its env vars (KIMCHI_CODING_AGENT_DIR etc. - overrides
    # are clobbered), so no env is registered; the plain home path is
    # the only real target (amp .config precedent - home_base(), not
    # XDG; %USERPROFILE%\.config\kimchi on Windows, no APPDATA).
    {"id": "kimchi", "env": None, "markers": [("h", ".config/kimchi")]},
    {"id": "kimi-code-cli", "env": None, "markers": [("h", ".kimi-code"), ("h", ".kimi")]},
    {"id": "kiro-cli", "env": None, "markers": [("h", ".kiro")]},
    {"id": "mistral-vibe", "env": "VIBE_HOME", "markers": [("h", ".vibe")]},
    # xum: the vendor (Coder) renamed cmux -> mux -> xum (shux pending);
    # the npm "mux" package is a forwarding shim. xum auto-migrates
    # ~/.mux to ~/.xum on startup - legacy marker kept as secondary
    # detection.
    {"id": "xum", "env": None, "markers": [("h", ".xum"), ("h", ".mux")]},
    {"id": "omp", "env": None, "markers": [("h", ".omp/agent")]},
    {"id": "opencode", "env": None, "markers": [("x", "opencode")]},
    {"id": "openhands", "env": None, "markers": [("h", ".openhands")]},
    {"id": "pi", "env": None, "markers": [("h", ".pi/agent")]},
    {"id": "posit-assistant", "env": None, "markers": [("h", ".posit/assistant"), ("h", ".positai")]},
    {"id": "qoder", "env": None, "markers": [("h", ".qoder")]},
    # qoder-cn: QODERCN_CONFIG_DIR override exists but detection/install
    # use the plain ~/.qoder-cn path.
    {"id": "qoder-cn", "env": None, "markers": [("h", ".qoder-cn")]},
    {"id": "qwen-code", "env": None, "markers": [("h", ".qwen")]},
    # reasonix: home = REASONIX_HOME env (detection override only) ||
    # REASONIX_STATE_HOME || ~/.reasonix (Unix, literal homedir) /
    # %APPDATA%\reasonix (Windows) - the APPDATA marker fixes Windows
    # detection (devin/goose "a" marker precedent); install uses the
    # plain platform path, never the env (qwen-code precedent).
    {"id": "reasonix", "env": "REASONIX_HOME", "markers": [("a", "reasonix"), ("h", ".reasonix")]},
    {"id": "rovodev", "env": None, "markers": [("h", ".rovodev")]},
    {"id": "roo", "env": None, "markers": [("h", ".roo")]},
    {"id": "tabnine-cli", "env": None, "markers": [("h", ".tabnine")]},
    {"id": "trae", "env": None, "markers": [("h", ".trae")]},
    {"id": "trae-cn", "env": None, "markers": [("h", ".trae-cn")]},
    {"id": "warp", "env": None, "markers": [("h", ".warp")]},
    {"id": "zed", "env": None, "markers": [("x", "zed"), ("a", "Zed"), ("f", "zed")]},
    {"id": "zcode", "env": None, "markers": [("h", ".zcode"), ("p", "/Applications/ZCode.app")]},
    # pochi: user-global rules = ~/.pochi/README.pochi.md ONLY (the
    # single fixed GlobalRules path, default-on every session;
    # AGENTS.md is NOT loaded at user level); at project level BOTH
    # README.pochi.md and AGENTS.md at cwd load - install writes only
    # the family AGENTS.md, never a project README.pochi.md.
    {"id": "pochi", "env": None, "markers": [("h", ".pochi")]},
]

AGENT_BY_ID = dict((a["id"], a) for a in AGENTS)
ALL_IDS: List[str] = [a["id"] for a in AGENTS]

# Tier-1 install targets (INSTALLER-PLAN section 6); order = TUI menu.
TIER1_ORDER = [
    "claude-code", "codex", "opencode", "devin", "cursor",
    "gemini-cli", "github-copilot", "pi", "omp",
    "roo", "augment", "kilo", "droid", "deepagents", "cline", "crush",
    "amp", "goose", "zed", "openhands", "warp", "junie", "posit-assistant",
    "zcode", "openclaw", "kimi-code-cli", "qwen-code",
    "trae", "antigravity", "kiro-cli", "qoder", "grok",
    "mistral-vibe",
    "rovodev",
    "bob",
    "trae-cn",
    "cortex",
    "antigravity-cli",
    "xum",
    "hermes-agent",
    "aider-desk",
    "forgecode",
    "command-code",
    "qoder-cn",
    "tabnine-cli",
    "codewhale",
    "jcode",
    "codebuff",
    "kimchi",
    "pochi",
    "reasonix",
    "deepseek-harness",
    ]
# Every family member reads project-root AGENTS.md by default; project
# scope installs ONE shared ./AGENTS.md block for all of them. Derived
# from TIER1_ORDER so a new agent joins the family by joining the roster
# (a parallel literal list went stale before: omp was missing from it).
#
# NOT family members (own project file or user-scope-only):
#   claude-code, github-copilot, tabnine-cli, trae/trae-cn -> own file
#   gemini-cli -> GEMINI.md only; openclaw -> never reads project
#   AGENTS.md (personal workspace model)
_NON_FAMILY = {"claude-code", "gemini-cli", "github-copilot", "openclaw",
               "tabnine-cli", "trae", "trae-cn"}
FAMILY_IDS = [a for a in TIER1_ORDER if a not in _NON_FAMILY]
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
    "openclaw": "OpenClaw",
    "kimi-code-cli": "Kimi Code",
    "qwen-code": "Qwen Code",
    "trae": "Trae",
    "antigravity": "Antigravity",
    "kiro-cli": "Kiro",
    "qoder": "Qoder",
    "grok": "Grok Build",
    "mistral-vibe": "Mistral Vibe",
    "rovodev": "Rovo Dev",
    "bob": "IBM Bob",
    "trae-cn": "Trae CN",
    "cortex": "Cortex Code",
    "antigravity-cli": "Antigravity CLI",
    "xum": "Xum",
    "hermes-agent": "Hermes Agent",
    "aider-desk": "AiderDesk",
    "forgecode": "ForgeCode",
    "command-code": "Command Code",
    "qoder-cn": "Qoder CN",
    "tabnine-cli": "Tabnine CLI",
    "codewhale": "Codewhale",
    "jcode": "jcode",
    "codebuff": "Codebuff",
    "kimchi": "Kimchi",
    "pochi": "Pochi",
    "reasonix": "Reasonix",
    "deepseek-harness": "DeepSeek Harness",
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
    "bob": "",
    "trae-cn": "---\nalwaysApply: true\n---\n",
    "aider-desk": "",
    "qoder-cn": "",
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
    # piped stdout is block-buffered while stderr streams immediately:
    # without this flush an error lands ABOVE the stdout lines it
    # belongs under in any merged capture (observed: usage error
    # printed before the banner)
    sys.stdout.flush()
    print("error: " + msg, file=sys.stderr, flush=True)


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


def _existing_dirs(cands):
    """Multi-marker rule (section 6): every existing dir from cands
    (deduped, order preserved), else the first candidate alone."""
    seen = []
    for d in cands:
        if d not in seen:
            seen.append(d)
    existing = [d for d in seen if d.is_dir()]
    return existing or [seen[0]]


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
    return _existing_dirs(cands)


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


def reasonix_home():
    """Reasonix home dir: %APPDATA%/reasonix on Windows, ~/.reasonix
    elsewhere (paths.go L47-67/L565-570: REASONIX_HOME ||
    REASONIX_STATE_HOME || the platform default - literal os.UserHomeDir
    on Unix, XDG legacy-read-only; AppData\\Roaming on Windows).
    REASONIX_HOME overrides detection only; install uses this plain
    platform path (qwen-code precedent, devin platform-split)."""
    if os.name == "nt":
        appd = appdata_base() or home_base() / "AppData" / "Roaming"
        return appd / "reasonix"
    return home_base() / ".reasonix"


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
    return _existing_dirs(cands)


# ---------------------------------------------------------------------------
# Detection engine (section 5)
# ---------------------------------------------------------------------------


def detect_agents():
    """Returns a list of dicts: id, paths."""
    home = home_base()
    xdg = xdg_base()
    appd = appdata_base()
    flat = flatpak_xdg_base()
    results = []
    for ag in AGENTS:
        matched = []
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
        if matched:
            results.append({
                "id": ag["id"],
                "paths": matched,
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


# User-scope install targets (INSTALLER-PLAN sections 4/6). ONE
# source for BOTH consumers - build_install_plan (install) and
# scan_removal (uninstall candidates) - so install and removal can
# never drift apart. Each row: id -> list of
# (path, mode, drop_agent, agents served); multi-marker agents
# (devin, zed) expand to every existing dir at call time.
# claude-code is NOT here: its user target depends on --claude-mode,
# so it keeps an explicit branch in build_install_plan and scan
# lists both of its files. Rows follow TIER1_ORDER.
_USER_TARGETS: Dict[str, Any] = {
    "codex": lambda: [(codex_dir() / "AGENTS.md", "inline", None, ["codex"])],
    "opencode": lambda: [(xdg_base() / "opencode" / "AGENTS.md", "inline", None, ["opencode"])],
    "pi": lambda: [(home_base() / ".pi" / "agent" / "AGENTS.md", "inline", None, ["pi"])],
    "omp": lambda: [(home_base() / ".omp" / "agent" / "AGENTS.md", "inline", None, ["omp"])],
    "devin": lambda: [(d / "AGENTS.md", "inline", None, ["devin"])
             for d in devin_dirs()],
    "cursor": lambda: [(home_base() / ".cursor" / "rules" / "behave.mdc", "drop", "cursor", ["cursor"])],
    "gemini-cli": lambda: [(home_base() / ".gemini" / "GEMINI.md", "inline", None, ["gemini-cli"])],
    "github-copilot": lambda: [(home_base() / ".copilot" / "instructions" / "behave.instructions.md", "drop", "github-copilot", ["github-copilot"])],
    "roo": lambda: [(home_base() / ".roo" / "rules" / "behave.md", "drop", "roo", ["roo"])],
    "augment": lambda: [(home_base() / ".augment" / "rules" / "behave.md", "drop", "augment", ["augment"])],
    "kilo": lambda: [(home_base() / ".kilocode" / "rules" / "behave.md", "drop", "kilo", ["kilo"])],
    "droid": lambda: [(home_base() / ".factory" / "AGENTS.md", "inline", None, ["droid"])],
    "deepagents": lambda: [(home_base() / ".deepagents" / "agent" / "AGENTS.md", "inline", None, ["deepagents"])],
    # cline's SDK loader reads ~/.cline/rules among its global
    # rules search paths; chosen over Documents/Cline/Rules
    # because it matches the ~/.cline detection marker and
    # needs no Documents-dir resolver.
    "cline": lambda: [(home_base() / ".cline" / "rules" / "behave.md", "drop", "cline", ["cline"])],
    # CRUSH.md is the user's own cross-project instructions
    # file (like GEMINI.md): inline block at the top so
    # existing content survives - never a whole-file drop.
    # crush loads <config>/crush/CRUSH.md by default, where
    # config = $XDG_CONFIG_HOME or ~/.config on ALL platforms.
    "crush": lambda: [(xdg_base() / "crush" / "CRUSH.md", "inline", None, ["crush"])],
    # amp hardcodes $HOME/.config on every platform
    # (including Windows) and does not honor
    # XDG_CONFIG_HOME, so home_base()/".config" - NOT
    # xdg_base().
    "amp": lambda: [(home_base() / ".config" / "amp" / "AGENTS.md", "inline", None, ["amp"])],
    "goose": lambda: [(goose_config_dir() / "AGENTS.md", "inline", None, ["goose"])],
    "zed": lambda: [(d / "AGENTS.md", "inline", None, ["zed"])
             for d in zed_dirs()],
    # OpenHands CLI hardwires load_user_skills=True and
    # always loads trigger-less .md files from
    # ~/.agents/skills/ (the modern dir; legacy
    # ~/.openhands/{skills,microagents}/ also read - marker
    # ~/.openhands stays detection-only).
    "openhands": lambda: [(home_base() / ".agents" / "skills" / "behave.md", "drop", "openhands", ["openhands"])],
    # ~/.agents/AGENTS.md is warp's ONLY registered global
    # rulefile (docs.warp.dev + warp source
    # GlobalRuleSource::Agents) AND a de-facto shared
    # cross-agent file (cline, droid, goose, kimi-code read
    # it too) - the marked block is idempotent, so it serves
    # every reader.
    "warp": lambda: [(home_base() / ".agents" / "AGENTS.md", "inline", None, ["warp"])],
    # documented for Junie CLI (%USERPROFILE%\.junie\AGENTS.md);
    # the IDE plugin loads project scope only - caveat
    # documented in TODO-LEFT findings. Project scope rides
    # the shared ./AGENTS.md family block, NOT
    # .junie/AGENTS.md: that file is EXCLUSIVE and would
    # suppress the root AGENTS.md + playbook + rules.
    "junie": lambda: [(home_base() / ".junie" / "AGENTS.md", "inline", None, ["junie"])],
    # Posit Assistant reads ~/.posit/assistant/AGENTS.md as
    # user memory (every session, no trust prompt); legacy
    # ~/.positai is auto-migrated by the app on first
    # launch, so the ~/.posit marker suffices - the legacy
    # dir is never a second install target.
    "posit-assistant": lambda: [(home_base() / ".posit" / "assistant" / "AGENTS.md", "inline", None, ["posit-assistant"])],
    # zcode reads ~/.zcode/AGENTS.md at task start (appended
    # first into the prompt); the /Applications/ZCode.app
    # registry marker is presence-only detection (the app
    # bundle loads no rules file) - ~/.zcode is the single
    # user target.
    "zcode": lambda: [(home_base() / ".zcode" / "AGENTS.md", "inline", None, ["zcode"])],
    # OpenClaw runs a personal workspace model - it loads
    # ~/.openclaw/workspace/AGENTS.md (workspace bootstrap,
    # injected every session) but does NOT read project
    # ./AGENTS.md, so openclaw is intentionally NOT in
    # FAMILY_IDS; legacy ~/.clawdbot / ~/.moltbot are
    # inert after migration - detection-only markers.
    "openclaw": lambda: [(home_base() / ".openclaw" / "workspace" / "AGENTS.md", "inline", None, ["openclaw"])],
    # ~/.kimi-code/AGENTS.md is kimi-code's documented
    # global memory (loadAgentsMdForRoots, default-on);
    # the ~/.kimi marker detects the OLD Python Kimi CLI -
    # a different tool that loads no user rules file - and
    # stays detection-only.
    "kimi-code-cli": lambda: [(home_base() / ".kimi-code" / "AGENTS.md", "inline", None, ["kimi-code-cli"])],
    # qwen-code loads ~/.qwen/QWEN.md every conversation
    # (memoryDiscovery.ts: the global context file is
    # always checked, created by the user or /memory).
    # QWEN_HOME env override exists but detection/install
    # use the plain home path. Project scope rides the
    # shared ./AGENTS.md family block (AGENTS.md is in
    # the default context filename list).
    "qwen-code": lambda: [(home_base() / ".qwen" / "QWEN.md", "inline", None, ["qwen-code"])],
    # ~/.trae/user_rules.md is the Trae IDE's global rules
    # file (docs.trae.ai/ide/rules: "Global rules take
    # effect in all projects"; the IDE Rules UI creates
    # this exact file) - inline at the top so existing
    # user rules survive. Windows: %userprofile%/.trae.
    "trae": lambda: [(home_base() / ".trae" / "user_rules.md", "inline", None, ["trae"])],
    # antigravity reads the SAME global file as gemini-cli
    # ("Global rules live in ~/.gemini/GEMINI.md and are
    # applied across all workspaces" - antigravity.google
    # /docs/ide/rules + /docs/rules-workflows). Shared-file
    # case, warp ~/.agents/AGENTS.md precedent: the marked
    # block is idempotent, so selecting both agents writes
    # one block; --remove cleans it for both (the removal
    # candidate lists gemini-cli AND antigravity).
    "antigravity": lambda: [(home_base() / ".gemini" / "GEMINI.md", "inline", None, ["antigravity"])],
    # ~/.kiro/steering/ is Kiro's global steering dir -
    # "Kiro will automatically load these files in chat
    # sessions" (kiro.dev/docs/steering); on the CLI,
    # inclusion modes are not supported at all, and on the
    # IDE the default inclusion is always, so a bare drop
    # file needs no frontmatter. Global steering applies
    # to IDE + CLI only (not Web/Mobile). Project scope
    # rides the shared ./AGENTS.md family block (root
    # AGENTS.md is "always included", all surfaces).
    "kiro-cli": lambda: [(home_base() / ".kiro" / "steering" / "behave.md", "drop", "kiro-cli", ["kiro-cli"])],
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
    "qoder": lambda: [(home_base() / ".qoder" / "rules" / "behave.md", "drop", "qoder", ["qoder"])],
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
    "grok": lambda: [(home_base() / ".grok" / "rules" / "behave.md", "drop", "grok", ["grok"])],
    # Mistral Vibe loads up to two AGENTS.md files into
    # context: the user-level ~/.vibe/AGENTS.md (or in
    # $VIBE_HOME if set) and the first project AGENTS.md
    # walking up from cwd, trusted folders only
    # (docs.mistral.ai/vibe/code/cli/agents; OSS repo
    # mistralai/mistral-vibe). VIBE_HOME exists but
    # detection/install use the plain home path (qwen-code
    # precedent). Project scope rides the shared
    # ./AGENTS.md family block.
    "mistral-vibe": lambda: [(home_base() / ".vibe" / "AGENTS.md", "inline", None, ["mistral-vibe"])],
    # Rovo Dev CLI memory: user-wide ~/.rovodev/AGENTS.md
    # ("applies to all your Rovo Dev CLI sessions") plus
    # project AGENTS.md + AGENTS.local.md per workspace
    # (support.atlassian.com/rovo/docs/
    # use-memory-in-rovo-dev-cli). Project scope rides the
    # shared ./AGENTS.md family block.
    "rovodev": lambda: [(home_base() / ".rovodev" / "AGENTS.md", "inline", None, ["rovodev"])],
    # IBM Bob rules: user-global ~/.bob/rules/*.md "Apply
    # automatically across all your projects" (plain text
    # files, recursive + alphabetical; no frontmatter
    # activation system documented - bare drop,
    # kiro-cli/qoder/grok precedent). Project scope rides
    # the shared ./AGENTS.md family block (root AGENTS.md
    # "Automatically loaded by default", opt-out only via
    # "bob-code.useAgentRules": false).
    "bob": lambda: [(home_base() / ".bob" / "rules" / "behave.md", "drop", "bob", ["bob"])],
    # Trae CN (docs.trae.cn/work_rules, TraeWork docs):
    # global rules live under ~/.trae-cn/user_rules/ - the
    # CN docs word it as a rules DIRECTORY (win
    # %userprofile%/.trae-cn/user_rules), unlike the intl
    # edition's single user_rules.md file; drop with
    # alwaysApply like the project rules. Root AGENTS.md is
    # toggle-gated + TraeWork-desktop-only -> NOT a family
    # agent (intl precedent).
    "trae-cn": lambda: [(home_base() / ".trae-cn" / "user_rules" / "behave.md", "drop", "trae-cn", ["trae-cn"])],
    # Snowflake Cortex Code (CoCo): user-scope instruction
    # files are searched in ~/.snowflake/cortex/ (primary;
    # the Custom instructions editor reads/writes
    # ~/.snowflake/cortex/AGENTS.md) - Desktop-documented;
    # the CLI documents project AGENTS.md but is silent on
    # user instruction files (TODO-LEFT findings caveat).
    # Project scope rides the shared ./AGENTS.md family
    # block (root AGENTS.md auto-discovered workspace root
    # -> git root, default on).
    "cortex": lambda: [(home_base() / ".snowflake" / "cortex" / "AGENTS.md", "inline", None, ["cortex"])],
    # Antigravity CLI (the Gemini CLI successor) keeps the
    # same context-file rules: "The agent automatically
    # consults and enforces your global constraints
    # located at ~/.gemini/GEMINI.md" and parses workspace
    # GEMINI.md + AGENTS.md (/docs/cli/gcli-migration,
    # "Context files and workspace rules"). Third
    # shared-file reader with gemini-cli + antigravity;
    # the marked block is idempotent and the removal
    # candidate lists all three. Project scope rides the
    # shared ./AGENTS.md family block.
    "antigravity-cli": lambda: [(home_base() / ".gemini" / "GEMINI.md", "inline", None, ["antigravity-cli"])],
    # xum (Coder; renamed cmux -> mux -> xum) reads
    # ~/.xum/AGENTS.md as its user instructions file; a
    # pre-existing file keeps its content below the marked
    # block (amp/droid precedent). Legacy ~/.mux is
    # auto-migrated by xum itself - detection-only marker.
    # Project scope rides the shared ./AGENTS.md family
    # block (first-match chain from cwd).
    "xum": lambda: [(home_base() / ".xum" / "AGENTS.md", "inline", None, ["xum"])],
    # Hermes Agent (Nous Research): ~/.hermes/SOUL.md is the
    # identity file loaded every session - inline block at
    # the top so existing content survives (create if
    # absent). HERMES_HOME exists but install uses the
    # plain path (qwen-code precedent); Windows native
    # default is %LOCALAPPDATA%\hermes - marker stays
    # ~/.hermes. Project scope rides the shared ./AGENTS.md
    # family block (AGENTS.md is in its project chain).
    "hermes-agent": lambda: [(home_base() / ".hermes" / "SOUL.md", "inline", None, ["hermes-agent"])],
    # AiderDesk (hotovo): user rules at ~/.aider-desk/rules/
    # are always active - no frontmatter system documented,
    # bare drop (kiro-cli/qoder/grok/bob precedent). Agent
    # mode auto-loads the root AGENTS.md, so project scope
    # rides the shared ./AGENTS.md family block.
    "aider-desk": lambda: [(home_base() / ".aider-desk" / "rules" / "behave.md", "drop", "aider-desk", ["aider-desk"])],
    # ForgeCode (Tailcall): ~/.forge/AGENTS.md is the global
    # instructions file - inline block at the top so
    # existing content survives. FORGE_CONFIG exists but
    # install uses the plain path; legacy ~/forge is
    # presence-only, not a marker. Project scope rides the
    # shared ./AGENTS.md family block.
    "forgecode": lambda: [(home_base() / ".forge" / "AGENTS.md", "inline", None, ["forgecode"])],
    # Command Code (Langbase): ~/.commandcode/AGENTS.md is
    # the global instructions file - inline block at the
    # top so existing content survives. Project scope rides
    # the shared ./AGENTS.md family block (<root>/AGENTS.md
    # is the default project context file).
    "command-code": lambda: [(home_base() / ".commandcode" / "AGENTS.md", "inline", None, ["command-code"])],
    # Qoder CLI CN mirrors the intl qoder exactly: user
    # rules at ~/.qoder-cn/rules/ are always active by
    # default - bare drop, no frontmatter (qoder
    # precedent). QODERCN_CONFIG_DIR exists but install
    # uses the plain path. Project scope rides the shared
    # ./AGENTS.md family block (the CN CLI reads project
    # AGENTS.md).
    "qoder-cn": lambda: [(home_base() / ".qoder-cn" / "rules" / "behave.md", "drop", "qoder-cn", ["qoder-cn"])],
    # Tabnine CLI: ~/.tabnine/agent/TABNINE.md is the
    # user-level instructions file (the agent/ dir is
    # created if absent) - inline block at the top so
    # existing content survives. Project scope writes its
    # OWN ./TABNINE.md target, NOT the shared AGENTS.md
    # family block - tabnine reads TABNINE.md, not
    # AGENTS.md (gemini-cli GEMINI.md precedent).
    "tabnine-cli": lambda: [(home_base() / ".tabnine" / "agent" / "TABNINE.md", "inline", None, ["tabnine-cli"])],
    # Codewhale (Hmbown; Rust CLI) checks the global
    # ~/.codewhale/AGENTS.md every session and merges it
    # with the project one - global prepended, project gets
    # the last word (source #1157) - so the marked block
    # rides at the top (amp/droid precedent; file created
    # if absent). Real $HOME path, NOT a
    # CODEWHALE_HOME-redirected one. Aggregate 48 KiB
    # instruction budget trims the broadest scope first -
    # the block stays small by design. Project scope rides
    # the shared ./AGENTS.md family block (AGENTS.md
    # canonical, CLAUDE.md fallbacks).
    "codewhale": lambda: [(home_base() / ".codewhale" / "AGENTS.md", "inline", None, ["codewhale"])],
    # jcode (1jehuang; Rust harness): ~/.jcode/
    # prompt-overlay.md is the jcode-scoped global - the
    # "Global Prompt Overlay", prepended to every session.
    # The bare ~/AGENTS.md is ALSO read globally but is
    # skipped as a shared cross-agent surface - the
    # overlay is chosen deliberately. JCODE_HOME exists
    # but detection/install use the plain home path
    # (qwen-code precedent). Project scope rides the
    # shared ./AGENTS.md family block (the default
    # chain).
    "jcode": lambda: [(home_base() / ".jcode" / "prompt-overlay.md", "inline", None, ["jcode"])],
    # Codebuff (npm CLI): user knowledge files are
    # ~/.AGENTS.md > ~/.CLAUDE.md - first found only,
    # case-insensitive, loaded every session (sdk
    # run-state.ts loadUserKnowledgeFiles); ~/.knowledge.md
    # left the priority list in current source despite the
    # docs. BARE home dotfile - first of its kind, but the
    # same inline-upsert mechanics: create ~/.AGENTS.md if
    # absent, preserve existing content, marked block at
    # the top. Project scope rides the shared ./AGENTS.md
    # family block (root AGENTS.md/CLAUDE.md injected as
    # "Project instructions").
    "codebuff": lambda: [(home_base() / ".AGENTS.md", "inline", None, ["codebuff"])],
    # Kimchi (CAST AI): the global context file
    # ~/.config/kimchi/harness/AGENTS.md is loaded EVERY
    # session, before project files (context-files.ts);
    # entry.ts hardcodes homedir()/.config/kimchi/harness
    # and force-sets its env vars, so overrides are
    # clobbered - no env registered, plain home path only
    # (amp precedent: home_base()/".config", NOT
    # xdg_base(); %USERPROFILE%\.config\kimchi on Windows,
    # no APPDATA). Project scope rides the shared
    # ./AGENTS.md family block (AGENTS.md/CLAUDE.md walk
    # cwd->root).
    "kimchi": lambda: [(home_base() / ".config" / "kimchi" / "harness" / "AGENTS.md", "inline", None, ["kimchi"])],
    # Pochi (TabbyML): ~/.pochi/README.pochi.md is the
    # single fixed GlobalRules path, default-on every
    # session, inline-merged, no truncation
    # (custom-rules.ts L14-16; hermes-agent precedent of
    # a non-AGENTS.md user file). AGENTS.md is NOT loaded
    # at user level. Windows: %USERPROFILE%\.pochi.
    # Project scope rides the shared ./AGENTS.md family
    # block (BOTH README.pochi.md and AGENTS.md at cwd
    # load; a project README.pochi.md is never written -
    # junie .junie/AGENTS.md precedent).
    "pochi": lambda: [(home_base() / ".pochi" / "README.pochi.md", "inline", None, ["pochi"])],
    # Reasonix (DeepSeek; esengine/DeepSeek-Reasonix):
    # <home>/REASONIX.md is the ScopeUser rules file,
    # loaded unconditionally at every boot into the
    # cache-stable system prefix (resolver.go L24/L121-132,
    # boot.go L650-657); REASONIX.md is canonical over the
    # also-accepted AGENTS.md/CLAUDE.md in the same dir -
    # the agent's own DocPath prefers an existing
    # REASONIX.md, so the block absorbs later agent
    # appends. Home: %APPDATA%\reasonix on Windows,
    # ~/.reasonix elsewhere (devin platform-split
    # precedent); REASONIX_HOME/REASONIX_STATE_HOME
    # overrides exist but the plain path is used
    # (qwen-code precedent); edits apply next session
    # (cache-stable). Project scope rides the shared
    # ./AGENTS.md family block (REASONIX.md/AGENTS.md/
    # CLAUDE.md + .local.md variants, git-root->cwd chain,
    # ALL matches load).
    "reasonix": lambda: [(reasonix_home() / "REASONIX.md", "inline", None, ["reasonix"])],
    # DeepSeek Harness (DeepSeek AI; CLI dsh): ~/.dsh/AGENTS.md
    # is the fixed user-global instruction file, loaded as
    # baseline before the first request by the
    # dsh-agent-instructions plugin - "dsh-base enables this
    # behavior by default" (package README; config.ts
    # dshHome "defaults to $DSH_HOME or ~/.dsh"). Byte
    # budget trims the broadest scope first, so the block
    # stays small (codewhale caveat precedent). DSH_HOME
    # override exists but the plain path is used
    # (qwen-code/reasonix precedent). Project scope rides
    # the shared ./AGENTS.md family block (AGENTS.md +
    # CLAUDE.md per dir + .local overlays, cwd->git-root
    # walk, every existing file loads).
    "deepseek-harness": lambda: [(home_base() / ".dsh" / "AGENTS.md", "inline", None, ["deepseek-harness"])],
}

def build_install_plan(agents, scope, variant, claude_mode, project_dir):
    """Returns (targets, notes)."""
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
                continue
            for path, mode, drop_agent, ags in _USER_TARGETS[a]():
                targets.append(_mk_target(ags, path, mode,
                                          drop_agent=drop_agent))
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
    if "tabnine-cli" in agents:
        # tabnine reads TABNINE.md, not AGENTS.md - its own project
        # target, NOT the shared family block (gemini-cli precedent)
        targets.append(_mk_target(
            ["tabnine-cli"], project_dir / "TABNINE.md", "inline"))
    if "github-copilot" in agents:
        targets.append(_mk_target(
            ["github-copilot"],
            project_dir / ".github" / "copilot-instructions.md", "inline"))
    if "openclaw" in agents:
        # user-scope-only agent: OpenClaw's personal workspace model
        # never reads project ./AGENTS.md (see the user-scope branch)
        notes.append("warn: openclaw is user-scope only (personal "
                     "workspace); skipping")
    if "trae" in agents or "trae-cn" in agents:
        # trae reads root AGENTS.md/CLAUDE.md only behind an import
        # toggle (Settings > Rules > Import), so it is NOT a family
        # agent; the native .trae/rules/ drop is always-on via
        # alwaysApply (docs.trae.ai/ide/rules). trae-cn reads the
        # SAME project rules dir (docs.trae.cn/work_rules) - one drop
        # serves both editions.
        targets.append(_mk_target(
            ["trae", "trae-cn"], project_dir / ".trae" / "rules" /
            "behave.md", "drop", drop_agent="trae"))
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
            say("  ok    %s: %s" % (detail, t["path"]))
            if t["gitignore"]:
                note = gitignore_step(project_dir, t["path"].name)
                if note:
                    say("  " + note)
            results.append(entry)
        except TargetError as exc:
            entry["error"] = str(exc)
            err("target failed: %s" % (exc,))
            results.append(entry)
    return results


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
        # shared files (the ~/.gemini/GEMINI.md triple: gemini-cli +
        # antigravity + antigravity-cli) collapse into ONE candidate
        # listing every reader - one block, one removal entry
        merged = {}
        for build in _USER_TARGETS.values():
            for path, mode, drop_agent, ags in build():
                key = (str(path), mode)
                if key in merged:
                    _p, _m, d0, a0 = merged[key]
                    merged[key] = (path, mode, d0 or drop_agent,
                                   a0 + [x for x in ags if x not in a0])
                else:
                    merged[key] = (path, mode, drop_agent, list(ags))
        # reasonix reads REASONIX.md from EITHER platform home (Windows
        # %APPDATA%\reasonix via reasonix_home(), Unix ~/.reasonix); the
        # table row carries the install path, the scan covers BOTH homes
        # so a platform switch or a stray marked file is always cleaned
        # (candidates only fire on existing files)
        rx_extra = [home_base() / ".reasonix" / "REASONIX.md"]
        appd_rx = appdata_base()
        if appd_rx is not None:
            rx_extra.append(appd_rx / "reasonix" / "REASONIX.md")
        for rx in rx_extra:
            key = (str(rx), "inline")
            if key not in merged:
                merged[key] = (rx, "inline", None, ["reasonix"])
        for path, mode, drop_agent, ags in merged.values():
            add(path, mode, ags, drop_agent=drop_agent)

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
        add(d / "TABNINE.md", "inline", ["tabnine-cli"])
        add(d / ".trae" / "rules" / "behave.md", "drop",
            ["trae", "trae-cn"], drop_agent="trae")

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
        paths = ", ".join(str(p) for p in d["paths"])
        print("  %-16s %s" % (d["id"], paths))
    det_ids = set(d["id"] for d in det)
    extra = [a for a in ALL_IDS if a not in det_ids]
    print("Additional supported agents (%d):" % len(extra))
    print("  " + (", ".join(extra) if extra else "(none)"))
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

    agents = list(requested)
    if args.all_detected:
        for d in detect_agents():
            if d["id"] not in agents:
                agents.append(d["id"])
    if not agents:
        if args.all_detected:
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
        agents, scope, variant, claude_mode, project_dir)
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
        _summary_after_install(results, targets, project_dir, args.block_id)

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
        err("confirmation missing, pass --yes to remove")
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
    if reader.raw_keys():
        # owner 2026-09-14: y/n/q are non-numbered answers, so they act
        # on the keypress like every widget key (no ENTER); ENTER takes
        # the [y/N] default (no).  The line grammar below stays for
        # pipe/--ascii and scripted stdin (raw_keys() False), where a
        # typed "y\n" is the only way to answer.
        print(prompt, end="")
        sys.stdout.flush()
        while True:
            k = reader.read_key()
            if k == "interrupt":
                raise KeyboardInterrupt
            if isinstance(k, str) and len(k) == 1 and k.lower() in "ynq":
                print(k)
                sys.stdout.flush()
                if k.lower() == "q":
                    raise QuitTUI()
                return k.lower() == "y"
            if k == "enter":
                print()
                return False
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
    if answer == "s":
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


def _menu_write(vt, prev_count, lines, sep=False):
    """(Re)draw the widget block - the only place ANSI escapes appear.
    sep prints one blank line first when this draw does NOT overwrite
    the previous one (non-VT fallback redraws; VT full redraws after
    an expansion or message reset prev_count) so stacked blocks stay
    visually apart."""
    out = sys.stdout
    if vt and prev_count:
        out.write("\x1b[%dA\r" % prev_count)
    elif sep:
        out.write("\n")
    for ln in lines:
        out.write(ln + ("\x1b[K\n" if vt else "\n"))
    out.flush()


def _menu_block(title, rows, pos, checked, multi, footer, buf, status,
                vt=False, marks=None):
    """The widget's rendered lines: title, item rows with a '>' cursor
    (and [x]/[ ] marks in multi mode), footer, and one status/typed
    line - raw mode has no terminal echo, so the typed buffer must be
    visible here.  marks, when given, is a bool list parallel to rows
    (multi only): a checked row whose agent is already installed
    renders [X] instead of [x]; an unchecked row always renders the
    plain [ ] - installed state never shows without the check."""
    # (owner, canary round 3 follow-up) Precompute items and width
    # so every VT-cursor bar pads one space past the widest row line
    # in this menu
    items = []
    width = 0
    for i, row in enumerate(rows):
        parts = row.split("\n")
        lead = ">" if i == pos else " "
        if multi:
            if checked[i]:
                box = "X" if marks is not None and marks[i] else "x"
            else:
                box = " "
            item = ["%s [%c] %s" % (lead, box, parts[0])]
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
        lines.extend(footer if isinstance(footer, list) else [footer])
    tail = status or ("typed: " + buf if buf else "")
    if tail:
        lines.append("  " + tail)
    return lines


def _arrow_menu(reader, title, rows, multi=False, checked=(),
                footer: Union[str, List[str],
                              Callable[[], Union[str, List[str]]]] = "",
                on_text=None, on_key=None, empty_msg=None, marks=None):
    """The rung-2 menu widget: same items as the numbered prompt, plus a
    cursor.  Up/Down move, Space toggles [x] (multi), Enter accepts,
    Backspace edits, printable keys build a typed buffer submitted to
    on_text on Enter (the prompt's EXISTING answer grammar - numbered
    input is never removed), Esc surfaces to the caller, which walks
    BACK to the previous menu.  on_key, when given, is offered every
    printable single char FIRST; returning True consumes it as an
    immediate command - acted on the keypress like Esc/Space/Enter,
    never buffered (the agent picker's S/L/Q, the letter answers of
    the single-choice menus); returning ("done", value) ends the menu
    with that value at once.  Only numbered answers stay
    type-then-Enter.  All keys
    come from reader.read_key(): the StdinReader thread stays the single
    stdin consumer (5.2.2 - see its docstring).

    Returns ("done", value): the cursor index (single choice), the
    checked bool list (multi), or on_text's value for a typed buffer;
    or ("esc", None).  footer may be a zero-arg callable - it is
    evaluated on every redraw so a menu whose state changes mid-flight
    (the agent picker's s-toggle) can reword its own hint; a callable
    may return a list of lines to render a hint block below the rows.
    marks (multi only) is passed through to _menu_block untouched -
    like checked it must stay the caller's exact list object, because
    the agent picker's l-expansion rewrites it in place."""
    vt = _vt_ok()
    pos = 0
    # multi: keep the CALLER's list object, not a copy - the agent
    # picker's l-expansion mutates rows/checked in place from on_text
    # and relies on this loop seeing the same lists next redraw.
    checked = checked if multi else []
    buf = ""
    status = ""
    prev = 0
    drawn = False
    while True:
        block = _menu_block(title, rows, pos, checked, multi,
                            footer() if callable(footer) else footer,
                            buf, status, vt, marks=marks)
        # a redraw that overwrites (VT cursor-up) needs no separator;
        # anything printed below the previous block gets one blank
        # line so the blocks do not touch (non-VT fallback, VT full
        # redraws after expansion/message)
        _menu_write(vt, prev, block, sep=drawn and not (vt and prev))
        drawn = True
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
            if on_key is not None:
                res = on_key(key)
                if res:
                    # immediate command consumed (S/L/Q in the agent
                    # picker, letter answers elsewhere): acted on the
                    # keypress like Esc/Space/Enter; it may have
                    # rewritten the rows (L-expansion), so full redraw
                    # and any partial buffer is dropped.  ("done",
                    # value) ends the menu with that answer at once.
                    buf = ""
                    status = ""
                    if isinstance(res, tuple):
                        return res
                    prev = 0
                    continue
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
    never equals "user", so scope routing always fell to project).
    Letter answers act on the keypress (owner 2026-09-14 - the ESC/
    ENTER class of keys): u/p/q, c/a/g/j/q fire at once; digits stay
    buffered and keep needing ENTER (the variant menu)."""
    def on_key(ch):
        if not ch.isalpha():
            return False
        value = parse_text(ch.lower())
        if value is None:
            return False
        return ("done", value)

    def on_text(buf):
        value = parse_text(buf)
        if value is None:
            print(invalid_msg)
            return _MENU_AGAIN
        return value

    kind, value = _arrow_menu(reader, title, rows, footer=footer,
                              on_text=on_text, on_key=on_key)
    if kind == "esc":
        return None
    if isinstance(value, int):
        value = parse_text(row_keys[value])
    return value


def _preview_targets(targets):
    print()
    for t in targets:
        if t["kind"] == "copy":
            print("  - plain copy: %s" % t["path"])
            print("    (no markers, no agent file touched; not tracked by "
                  "--remove; yours to edit)")
            continue
        existed = t["path"].exists()
        if t["mode"] == "drop":
            print("  - new file %s" % t["path"])
            print("    (%s; the rules dir is created if missing)"
                  % DROP_CONSENT)
            if t["drop_agent"] == "cursor":
                print("    (loads only for projects inside your home dir; "
                      "for other projects use project scope)")
        elif existed:
            print("  - rules block AT THE TOP of %s" % t["path"])
            print("    (%s)" % INLINE_CONSENT)
        else:
            print("  - create %s with the rules block" % t["path"])
            print("    (%s)" % INLINE_CONSENT)
        if t["gitignore"]:
            print("    (local file; will be gitignored when a git repo "
                  "exists)")


def _summary_after_install(results, targets, project_dir, block_id):
    ok_paths = set()
    for t, r in zip(targets, results):
        if not r["error"]:
            ok_paths.add(t["path"])
    if any(not r["error"] for r in results):
        stale_hint(ok_paths, project_dir, block_id)
        say("Done - restart your agents to pick up changes.")
        say("python install.py --remove to uninstall.")


def _agent_menu_row(pos, aid, det_map, installed=False):
    d = det_map.get(aid)
    path = str(d["paths"][0]) if d else "-"
    row = "%2d  %-17s %s" % (pos, DISPLAY[aid], path)
    # installed state has two renderings: the widget's [X] glyph on
    # the checkbox (this flag stays False there) and this text suffix
    # for the numbered fallback, whose rows have no checkboxes
    if installed:
        row += "  (installed)"
    return row


def _pick_agents_widget(reader, tier1, prechecked_ids, det_map, visible,
                        installed_ids=None):
    """Multi-select widget for the agent picker - and the menu itself:
    the rows ARE the scan report (position, display name, detected
    path or "-"), one list instead of a pre-printed scan dump plus a
    second display-name menu.  The default view is the detected
    agents only; pressing L expands the SAME menu in place to every
    supported agent.  visible is the caller's list and is mutated in
    place by that expansion (the in-place protocol below explains
    why).  Enter with an empty buffer submits the checked rows;
    S, L, Q act on the keypress itself (owner 2026-09-14 - the ESC/
    SPACE/ENTER class of keys, via _arrow_menu's on_key hook): S
    toggles select all / select none of the SHOWN rows only - it
    can never check (and install into) an agent that was not
    shown; L first expands the view when every supported agent is
    really wanted; Q quits.  Only the numbered answers (3, 4-7,
    2,5) stay type-then-ENTER through _parse_selection - with S/L/Q
    intercepted, a typed buffer can only ever hold numeric grammar.
    installed_ids is the set of agents that already carry our marker
    (user scope): a checked row for such an agent renders [X] instead
    of [x], so a re-run shows what is already in place; unchecked
    rows never show install state.  Returns None when the user
    pressed Esc - the caller walks back to the previous menu."""
    if installed_ids is None:
        installed_ids = set()
    pre = set(prechecked_ids)
    rows = [_agent_menu_row(i, a, det_map)
            for i, a in enumerate(visible, 1)]
    checked = [a in pre for a in visible]
    marks = [a in installed_ids for a in visible]

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
        marks[:] = [a in installed_ids for a in visible]

    def footer():
        # the hint block lives BELOW the rows (owner 2026-09-14);
        # line one rewords S with the checkbox state so it always
        # names what S would do NEXT; it also carries the [X] legend
        # for the installed-glyph
        state = "none" if checked and all(checked) else "all"
        return ["  SPACE toggles [x] ([X] = already installed), "
                "ENTER = install the checked items,",
                "  ESC = back, S = select %s, L = list all, Q = quit; "
                "Numbers (3), ranges (4-7) and lists (2,5) need ENTER"
                % state]

    def on_key(ch):
        # owner 2026-09-14: S/L/Q act on the keypress itself (the ESC/
        # SPACE/ENTER class) - never buffered; only numbered answers
        # (3, 4-7, 2,5) stay type-then-ENTER.  Q quits, L expands the
        # view in place, S toggles the SHOWN rows like one big Space
        # press (S used to be 'a' + ENTER, which returned every
        # supported agent, installing into - and leaving dirs behind
        # for - agents that were never detected; L + S still reaches
        # every supported agent when that is wanted).
        ch = ch.lower()
        if ch == "q":
            raise QuitTUI()
        if ch == "l":
            expand()
            return True
        if ch == "s":
            checked[:] = [not all(checked)] * len(visible)
            return True
        return False

    def on_text(buf):
        # on_key intercepts S/L/Q, so a buffer here can only ever hold
        # the numeric grammar - ranges/lists parse exactly like the
        # numbered prompt's ("default"/"all"/"list" are unreachable)
        res = _parse_selection(buf, len(visible))
        if res is None:
            print("not understood: use numbers (1), ranges (1-4), lists "
                  "(1,3)")
            return _MENU_AGAIN
        return [visible[i - 1] for i in res]

    kind, value = _arrow_menu(
        reader,
        [],
        rows, multi=True, checked=checked,
        footer=footer,
        on_text=on_text,
        on_key=on_key,
        empty_msg="nothing is checked: SPACE toggles rows, or press S to "
                  "select all shown",
        marks=marks)
    if kind == "esc":
        return None
    if isinstance(value, list) and value and isinstance(value[0], bool):
        return [a for a, c in zip(visible, value) if c]
    return value


def _pick_agents(reader, prechecked_ids, det_map, installed_ids=None):
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
    if installed_ids is None:
        installed_ids = set()
    if reader.raw_keys():
        chosen = _pick_agents_widget(reader, tier1, prechecked_ids,
                                     det_map, visible, installed_ids)
        if chosen is not None:
            return chosen
        # Esc = back to the scope menu.  The numbered loop below runs
        # ONLY when this terminal has no arrow-key support at all - a
        # capability fallback, never a mid-work mode switch.
        return _BACK
    while True:
        n = len(visible)
        for i, a in enumerate(visible, 1):
            print("  " + _agent_menu_row(i, a, det_map,
                                         installed=a in installed_ids))
        ans = _inp(
            reader,
            "Install into which agents? [1-%d] (e.g. 3 or 2,5 or 4-7; "
            "ENTER = checked/detected, s = select all shown, "
            "l = list all, q = quit)\n> " % n)
        res = _parse_selection(ans, n)
        if res == "list":
            visible[:] = tier1
            continue
        if res == "all":
            # widget parity (owner 2026-09-14): 's' selects the SHOWN
            # rows - never a hidden undetected agent.  The numbered
            # prompt is one-shot (no [x] state to flip), so selecting
            # none = typing only the numbers you want.
            return list(visible)
        if res == "default":
            if prechecked_ids:
                return [a for a in tier1 if a in prechecked_ids]
            print("nothing is pre-checked (no supported agents detected); "
                  "pick numbers or 's'")
            continue
        if res is None:
            print("not understood: use numbers (1), ranges (1-4), lists "
                  "(1,3), s, l, q, or ENTER")
            continue
        return [visible[i - 1] for i in res]


def _tui_user(args, reader, source):
    print()
    det = detect_agents()
    det_map = dict((d["id"], d) for d in det)
    print("Detected %d agents (out of %d supported, see --list)..."
          % (len(det), len(TIER1_ORDER)))
    # plain det_map membership is the detected test here; the agent
    # menu below IS the report.
    prechecked = set(aid for aid in TIER1_ORDER if aid in det_map)
    requested = _parse_requested_agents(args)
    prechecked.update(requested)
    # already-installed agents (user scope): the picker renders their
    # checked rows as [X] so a re-run shows what is in place
    installed_ids = set()
    for f in scan_removal(None, "user", None, None, args.block_id):
        installed_ids.update(f["agents"])

    chosen = _pick_agents(reader, prechecked, det_map, installed_ids)
    if chosen is _BACK:
        return _BACK
    if not chosen:
        print("nothing selected; nothing written")
        return 0
    targets, notes = build_install_plan(
        chosen, "user", None, args.claude_mode or "rules", None)
    for nt in notes:
        print(nt)
    if not targets:
        print("nothing to install")
        return 0
    _preview_targets(targets)
    print()
    if not _confirm(reader, args.yes):
        print("aborted; nothing written")
        return 0
    results = execute_targets(targets, source, args.block_id, None)
    _summary_after_install(results, targets, None, args.block_id)
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

    def parse_text(buf):
        s = buf.strip()
        if s.lower() in ("q", "quit"):
            raise QuitTUI()
        for num, name, desc, path, var in entries:
            if s.strip("()") == num:
                return var
        return None

    if reader.raw_keys():
        rows = []
        keys = []
        for num, name, desc, path, var in entries:
            tag = "[exists]" if path.exists() else "[missing]"
            rows.append("(%s) %-18s - %-46s %s" % (num, name, desc, tag))
            keys.append(num)
        rows.append("(q) %-18s - exit without changing anything" % "quit")
        keys.append("q")

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
        var = parse_text(_inp(reader, "> "))
        if var is not None:
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
        fam = parse_text(_inp(reader, "> "))
        if fam is not None:
            return fam
        print("  answer a, c, g, j or q")


def _tui_project_flagged(reader, source, requested, pre_variant, project_dir,
                         args, scope="project"):
    """Flags pre-selected agents: resolve targets through
    build_install_plan, exactly like the headless run.  The family
    wizard's a/c/g/j menu cannot represent tabnine-cli, trae or a
    copilot-only selection, which made those agents vanish into a
    menu that installed something else.  The wizard itself stays
    for the zero-flags flow, where the user is genuinely choosing
    a family.  scope passes straight through, so interactive local
    warn-skips non-Claude agents like headless --scope local."""
    if (scope == "project" and "claude-code" in requested
            and pre_variant is None):
        pre_variant = _tui_pick_variant(reader, None, project_dir)
        if pre_variant is None:
            return _BACK
    targets, notes = build_install_plan(
        requested, scope, pre_variant or "rules",
        args.claude_mode or "rules", project_dir)
    for nt in notes:
        print(nt)
    if not targets:
        print("nothing to install")
        return 0
    _preview_targets(targets)
    print()
    if not _confirm(reader, args.yes):
        print("aborted; nothing written")
        return 0
    results = execute_targets(targets, source, args.block_id, project_dir)
    _summary_after_install(results, targets, project_dir, args.block_id)
    for r in results:
        if r["error"]:
            return 4
    return 0


def _tui_project(args, reader, source, pre_variant, scope="project"):
    project_dir = _project_dir_of(args)
    print()
    print("Project directory: %s" % project_dir)
    requested = _parse_requested_agents(args)
    if not _validate_agents(requested):
        return 2
    if scope == "local":
        # local is claude-only in the headless run; interactive gets
        # the same plan (non-claude agents warn-skipped, variant
        # forced to CLAUDE.local.md) - with no agent flags it
        # defaults to claude-code so the zero-flags flow still
        # has something to preview
        return _tui_project_flagged(reader, source,
                                    requested or ["claude-code"],
                                    "local", project_dir, args, "local")
    if requested:
        return _tui_project_flagged(reader, source, requested, pre_variant,
                                    project_dir, args, scope)
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

    _preview_targets(targets)
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
                           args.block_id)
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
    if pre_scope == "local" and args.claude_variant not in (None, "local"):
        err("usage error: --scope local only supports --claude-variant local")
        return 1

    def parse_scope(buf):
        a = buf.strip().lower()
        if a in ("q", "quit"):
            raise QuitTUI()
        if a in ("u", "user"):
            return "user"
        if a in ("p", "proj", "project"):
            return "project"
        return None

    while True:
        # the scope ask lives INSIDE the wizard loop so _BACK
        # re-renders this menu - the wizard start - instead of
        # silently re-dispatching the previous branch
        if pre_scope is None:
            if reader.raw_keys():
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
                    pre_scope = parse_scope(_inp(reader, "> "))
                    if pre_scope is not None:
                        break
                    print("  answer u, p or q")
        if pre_scope == "user":
            r = _tui_user(args, reader, source)
        else:
            pre_variant = ("local" if pre_scope == "local"
                           else args.claude_variant)
            proj_scope = "local" if pre_scope == "local" else "project"
            r = _tui_project(args, reader, source, pre_variant, proj_scope)
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
