# AI Behaving Instructions That Actually Work

[![Website](https://img.shields.io/website?url=https%3A%2F%2Fzeljkoavramovic.github.io%2Fbehave%2F&label=landing%20page)](https://zeljkoavramovic.github.io/behave/)

One file. Zero dependencies. Discipline every AI coding session.

## Overview

Instructions that make AI coding assistants actually behave, so every coding session becomes more disciplined, more predictable, and more productive.

The ideas come from **[Andrej Karpathy's](https://x.com/karpathy/status/2015883857489522876)** observations on LLM coding pitfalls (**[Multica adaptation](https://github.com/multica-ai/andrej-karpathy-skills)**), and from **[David Scott Bernstein's](https://github.com/ThePassionateProgrammer/knowledge-base-starter)** partnership-driven working-agreement style. From there it grew into something more systematic, tuned for real projects.

~~A **[single-page walkthrough](https://zeljkoavramovic.github.io/behave/)** adds visual diagrams, side navigation, a before/after comparison, a feature comparison table, an FAQ, and one-click install commands.~~

Supports **Claude Code**, **Codex**, **Cursor**, **OpenCode**, **Kilo Code**, **Cline**, **Antigravity**, **Pi**, **DeepSeek Harness**, **ZCode**, **OpenClaw**, **Hermes**, and 40 other agents. The installer lets you choose from the list of auto-detected agents and asks whether you want a global install or a project-directory install. Depending on the kind of agent, installer drops the behaving instructions file into the agent's rules directory, or injects into `CLAUDE.md`, `AGENTS.md`, or `GEMINI.md`. No dependencies, one file, and simple deinstallation if needed.

## The problem it solves

AI coding assistants, left unchecked, tend to:

- Start coding before clarifying ambiguous requirements
- Add unrequested features, abstractions, and "improvements"
- Expand scope mid-task, refactor while fixing or "improve" while adding
- Silently rename files, change APIs, or rewrite working code
- Skip verification until after the mistake is already in the diff
- Suppress errors without telling you
- Push to version control or delete files without warning
- Run destructive CLI commands or modify secrets with no safety gate
- Ship incomplete or stub implementations and call them done
- Pick arbitrarily when rules conflict, choosing helpfulness over safety

This file encodes behavioral contracts that prevent all of these.

## Key features

### Four core coding principles

The framework rests on four disciplines: think before coding, prefer simplicity, make surgical changes, and define success through verification. Everything else builds on these four.

### Collaborative working model

The human brings domain knowledge and architectural intent. The AI brings speed, pattern recognition, critique, and exploration. The AI is expected to refine ideas collaboratively and wait for an explicit boundary before building.

### Order of precedence

When rules conflict, the AI knows exactly which wins. Hard stops override everything unless explicitly authorized; explicit instruction overrides defaults; correctness and safety override elegance or speed.

### Three named operating modes

- **default mode**: make the smallest correct change that satisfies the request
- **ambiguity mode**: stop and ask when uncertainty affects behavior, interfaces, data, safety, or irreversible work
- **cleanup mode**: broader simplification and deletion are allowed only when explicitly requested

That gives the AI an operating model instead of leaving behavior to chance.

### Wording conventions (Must / Should / May)

RFC-style rule weight removes ambiguity. `Must/Never` means mandatory, `Should/Prefer` means strong default, and `May` means optional.

### Shared vocabulary / interpretation layer

The file defines terms like *trivial task*, *minor ambiguity*, *harmful pattern*, and *working code* so the user and the AI share vocabulary from the start.

### Scope control for existing code

This is the most practical protection in the file. It prevents the AI from touching adjacent code, silently expanding scope, rewriting working systems, or using cleanup as an excuse to change unrelated areas.

### Hard stops with rule citation and authorization gate

When the AI cannot proceed, it does not just stop. It explains which rule caused the stop, so there is an audit trail around dangerous actions like destructive CLI commands, secret modification, silent signature changes, swallowed errors, or incomplete delivery, and it does not proceed until you authorize an exception.

### Verification by task type with manual fallback

Different work requires different proof:

- **Bug fix**: reproduce the failing case, then make it pass
- **New feature**: verify the public interface, not internals
- **Refactor**: verify observable behavior before and after
- **No automated tests**: define manual verification steps explicitly before proceeding

### Broken baseline handling

If the baseline is already broken, the AI must say so before making changes, define success relative to the existing state, and avoid pretending the whole system is verified when unrelated failures remain.

### Structured post-task report

After any non-trivial task, the AI reports:
- What changed
- What was verified
- What remains unverified
- Problems noticed but intentionally left untouched

### Documentation philosophy and rules

Documentation gets the same discipline as code. Explain the why. Update docs when behavior changes. Skip comments that just repeat the code, because they rot faster than the code they describe.

## Fully agnostic by design

This file works regardless of your:

| Dimension | Agnostic |
|---|---|
| Programming language | ✅ Python, C, JS, TypeScript, C#, Java, Pascal, Rust… |
| Framework | ✅ React, Django, Qt, bare-metal… |
| Library | ✅ No dependencies referenced |
| AI tool | ✅ 52 agents directly supported, adaptable to any instruction-file agent |
| OS | ✅ Windows, Linux, macOS |
| Domain | ✅ Web, embedded, desktop, scripts, data |
| Project type | ✅ New projects, legacy code, refactors |
| Verification method | ✅ Automated tests, manual validation, reproducible checks, baseline comparison |

Put project-specific stack details in a project-level instruction file. Keep the global file universal.

## How it comes together

```mermaid
flowchart TB
    K["[Karpathy]
- Think before coding
- Simplicity first
- Surgical changes
- Goal-driven execution"]

    B["[Bernstein]
- Collaborative framing
- Refine before building
- Respect for working code
- Simplicity without dogma
- Documentation philosophy"]

    A["[Avramovic]
- Order of precedence
- Operating modes
- Must/Should/May semantics
- Shared vocabulary / interpretation layer
- Hard stops
- Verification framework
- Broken-baseline handling
- Structured post-task reporting
- Documentation rules"]

    C["[CLAUDE.md / AGENTS.md / GEMINI.md]
Unified behavior framework
for safer, smaller, verifiable AI coding changes"]

    K --> C
    B --> C
    A --> C
```

## How it differs from the originals

| Feature | Karpathy | Bernstein | This repo |
|---|---|---|---|
| Core coding rules | ✅ | partial | ✅ inherited + refined |
| Collaborative partnership framing | ❌ | ✅ | ✅ inherited + refined |
| Order of precedence | ❌ | ❌ | ✅ new |
| Operating modes | ❌ | ❌ | ✅ new |
| Must/Should/May wording conventions | ❌ | ❌ | ✅ new |
| Shared vocabulary / interpretation layer | ❌ | ❌ | ✅ new |
| Existing-code scope discipline | partial | partial | ✅ formalized |
| Hard stops with rule citation | ❌ | ❌ | ✅ new |
| Hard-stop explanation protocol | ❌ | ❌ | ✅ new |
| Verification by task type | ❌ | partial | ✅ formalized |
| Verification fallback to manual steps | ❌ | ❌ | ✅ new |
| Broken-baseline handling | ❌ | ❌ | ✅ new |
| Structured post-task reporting | ❌ | ❌ | ✅ new |
| Dedicated documentation rules | ❌ | partial | ✅ formalized |
| Full multi-dimensional agnosticism | partial | partial | ✅ made explicit |

## Installation

The repo ships two files. `BEHAVE.md` is the rules file itself - pure Markdown, zero dependencies, one file you could also copy by hand. `install.py` is the installer - a single cross-platform Python script, standard library only (Python 3.6 or newer), which writes the rules into the right file with the right name for each agent.

### Installer (recommended)

Any OS with Python - runs straight from the repo, nothing is left in your directory:

```bash
python -c "import urllib.request; exec(compile(urllib.request.urlopen('https://raw.githubusercontent.com/zeljkoavramovic/behave/master/install.py').read(), 'install.py', 'exec'), {'__file__': 'install.py', '__name__': '__main__'})"
```

Use `python`, `python3`, or `py` per your platform; append any documented flags after the closing quote (for example `--list`, or `--remove --yes` to uninstall). No registry, no account, no npm - one Python script, standard library only, Python 3.6 or newer.

Prefer a local copy of the script? Windows (PowerShell): `iwr "https://raw.githubusercontent.com/zeljkoavramovic/behave/master/install.py" -OutFile install.py; python install.py` - Linux / macOS: `curl -fsSL https://raw.githubusercontent.com/zeljkoavramovic/behave/master/install.py -o install.py && python3 install.py`

The installer asks where the rules should apply (all your projects or just this one), auto-detects your installed agents, shows exactly what will change, and asks before writing.

**Supported agents list (52):**

Claude Code, Codex, OpenCode, Pi, Oh My Pi, Devin, Cursor, Gemini CLI, GitHub Copilot, Roo Code, Augment Code, Kilo Code, Droid, Deep Agents, Cline, Crush, Amp, Goose, Zed, OpenHands, Warp, Junie, Posit Assistant, ZCode, OpenClaw, Kimi Code, Qwen Code, Trae, Antigravity, Kiro, Qoder, Grok Build, Mistral Vibe, Rovo Dev, IBM Bob, Trae CN, Cortex Code, Antigravity CLI, Xum, Hermes Agent, AiderDesk, ForgeCode, Command Code, Qoder CN, Tabnine CLI, Codewhale, jcode, Codebuff, Kimchi, Pochi, Reasonix, and DeepSeek Harness

Run `python install.py --list` to see every agent it detects on your machine. For headless or CI use, see `python install.py --help`. In the agent picker, a checked row for an agent that already has the rules installed shows `[X]` instead of `[x]` - the mark follows the checkbox as you toggle it, and re-running with it checked updates the existing install. Terminals without arrow-key support (or piped input) get the same cue in the numbered fallback as an `(installed)` suffix on the row.

**What the installer writes** (and why re-running is safe):

- **Inline mode**: a marked block (`<!-- BEGIN behave ... -->` down to `<!-- END behave -->`) at the TOP of the agent's memory file (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, and friends). Everything you already had survives below the block, and a re-run replaces only the block itself.
- **Drop mode**: a standalone rules file the installer owns, placed in the agent's rules directory (for example `~/.claude/rules/behave.md`); removal deletes the file.
- **Plain copy**: `--copy-only` writes a bare `BEHAVE.md` and touches nothing else.

For Claude Code at user scope the default is the drop file `~/.claude/rules/behave.md`; pass `--claude-mode inline` for a marked block inside `~/.claude/CLAUDE.md` instead.

**Updating and uninstalling**: update = re-run the installer (`python install.py --all-detected --yes` refreshes every agent it finds on the machine). Uninstall = `python install.py --remove` - it scans every location it knows, shows what it found, and removes only its own block or file.

**Headless and CI**: any flags make the run non-interactive, and writes then need `--yes` (`--copy-only` is exempt). Useful flags: `--all-detected`, `--agent ID[,ID...]` (ids from `--list`), `--scope user|project|local` (default `auto`: project inside a git repo, else user), `--json` for machine-readable output, `--source URL|PATH` with `--sha256 HEX` to pin a fetched rules file to an exact hash (the run aborts before any write on mismatch; URL sources only), `--copy-only` for a plain copy, and `--ascii` for the numbered-prompt interactive mode. Exit codes: `0` success, `1` usage error or interactive abort (no TTY, EOF, interrupt), `2` unknown or missing agent, `3` source failure, `4` a target failed, `5` confirmation missing.

The repo distributes `BEHAVE.md`. When copying manually into an agent, the filename matters: Claude Code reads `CLAUDE.md`, Gemini CLI reads `GEMINI.md`, most other tools read `AGENTS.md`. The installer handles the naming automatically; manual users must rename.

Cross-agent bonus: Devin and VS Code GitHub Copilot also read `~/.claude/CLAUDE.md` and `~/.claude/rules/`, so a Claude Code install reaches those agents for free. Oh My Pi (omp), Pi's maintained successor, keeps its own config root - `~/.omp/agent/AGENTS.md` - and does not read OpenCode's global file by default, so the installer gives it a dedicated target.

One watch-list item: Gemini CLI does not read `AGENTS.md` by default today (tracked in [google-gemini/gemini-cli issue #28227](https://github.com/google-gemini/gemini-cli/issues/28227)). If Google ships default `AGENTS.md` loading, gemini-cli joins the shared `AGENTS.md` family and the installer will treat it like Codex, OpenCode, Pi, Oh My Pi, and Devin.

### Manual install (no Python)

Copy the file directly. Unlike the installer, this replaces the whole target file, so an existing `~/.claude/CLAUDE.md` is backed up to `CLAUDE.backup.md` before being overwritten. The result carries no installer markers: `--remove` cannot see or clean it, and a later installer run adds its marked block on top rather than adopting the file.

**Windows (PowerShell):**

```powershell
mkdir -Force "$HOME\.claude" > $null; cp "$HOME\.claude\CLAUDE.md" "$HOME\.claude\CLAUDE.backup.md" 2>$null; iwr "https://raw.githubusercontent.com/zeljkoavramovic/behave/master/BEHAVE.md" -OutFile "$HOME\.claude\CLAUDE.md"
```

**Linux / macOS:**

```bash
mkdir -p ~/.claude; cp ~/.claude/CLAUDE.md ~/.claude/CLAUDE.backup.md 2>/dev/null; curl -fsSL https://raw.githubusercontent.com/zeljkoavramovic/behave/master/BEHAVE.md -o ~/.claude/CLAUDE.md
```

~~If `~/.claude/CLAUDE.md` already exists, it is backed up to `CLAUDE.backup.md` before being overwritten.~~

Works natively with **Claude Code** and **OpenCode**. For other AI coding tools, follow that tool's instruction file convention (for example `AGENTS.md` or `GEMINI.md`). The content is the same; the filename depends on the tool. Prefer the installer even alongside a manual copy: it is idempotent, and only the files it writes are tracked by `--remove`.

## Related projects

- **[Agentic Design Patterns](https://zeljkoavramovic.github.io/agentic-design-patterns/)**: an interactive tutorial on patterns for building intelligent AI systems. It covers core patterns (prompt chaining, routing, parallelization, tool use, code-then-execute, dynamic scaffolding), reasoning and strategy patterns (reflection, planning, reasoning techniques, parallel fusion, prioritization, exploration and discovery), orchestration patterns (multi-agent collaboration, goal setting and monitoring, inter-agent communication, awareness, resource-aware optimization), infrastructure and state patterns (memory management, learning and adaptation, model context protocol, knowledge retrieval and RAG, evaluation and monitoring, session isolation), and reliability and control patterns (the stop hook, exception handling and recovery, human-in-the-loop, the Ralph Wiggum loop, guardrails and safety, spec-first agent). Each pattern comes with a description, diagram, when-to-use guidance, where it fits in the bigger picture, pros and cons, and real-world examples. A visual relationship diagram shows how the patterns interconnect.

## Credits

- **[Andrej Karpathy](https://x.com/karpathy/status/2015883857489522876)** - observations on LLM coding pitfalls
- **[Multica](https://github.com/multica-ai/andrej-karpathy-skills)** - CLAUDE.md adaptation of Karpathy's principles
- **[David Scott Bernstein](https://github.com/ThePassionateProgrammer)** - partnership-driven working-agreement style
- **[Zeljko Avramovic](https://github.com/zeljkoavramovic)** - systematization and expansion: precedence model, operating modes, wording semantics, shared vocabulary layer, verification framework, hard-stop protocol, broken-baseline handling, task reporting, documentation rules

## Support the project

If this saved you time, frustration, or a bad deployment, support is welcome:

- ⭐ **Star the repository**
- 💬 **Share the repository**
- <a href="https://buymeacoffee.com/cupofavra" target="_blank">
     <img align="left"
          src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png"
          alt="Buy Me A Coffee"
          style="height: 35px !important; width: 150px !important;" />
   </a>

## License

MIT - use freely, improve openly, credit kindly.
