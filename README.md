# agents-context-router

**English** | [日本語](README.ja.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md)

Keep your agent instructions short. Load the project details only when a task needs them.

`agents-context-router` helps coding agents turn an oversized `AGENTS.md` into a small shared kernel and a set of task-specific wiki topics. A lightweight Python script prints only the selected topic; history stays available without loading into every task.

<p align="center">
  <img src="context-router-stars.svg" alt="A friendly star routes a coding task to the right project docs" width="100%">
</p>

## The idea

Keep rules that apply to every task in `AGENTS.md`. Move runbooks and reference material into topic pages, and keep dated notes in history. The agent reads the kernel, chooses a topic, and loads only that topic.

<p align="center">
  <img src="context-router-comic-overload.svg" alt="A three-panel comic: a long instruction file overwhelms an agent, a buried rule is found, and the docs are reorganized" width="100%">
</p>

<p align="center">
  <img src="context-router-comic-routing.svg" alt="A three-panel comic showing a task routed through a small kernel to one matching wiki topic" width="100%">
</p>

## What it does

- Measures always-loaded instruction files before and after the split.
- Sorts content into a small kernel, task topics, history, and human docs.
- Routes each topic to whole files or exact Markdown headings through `docs/ai-context.json`.
- Bundles `scripts/ai-context.py`, a dependency-free router with `list`, topic, and `check` commands.
- Checks byte budgets, missing or ambiguous headings, unlisted topics, and orphaned wiki/history files.
- Adds an in-repo maintenance guide so the router can be maintained after the skill is removed.

The default budgets are 8 KiB for the root instructions and 16 KiB per topic. Split an oversized topic instead of raising its limit.

## Install

### Claude Code plugin

In a Claude Code session:

```text
/plugin marketplace add runkids/agents-context-router
/plugin install agents-context-router@agents-context-router
```

### Codex plugin

Add the repository's Codex plugin marketplace, then open `/plugins` and install **agents-context-router**:

```bash
codex plugin marketplace add runkids/agents-context-router --sparse .agents/plugins
codex
```

### Skillshare

Already use [Skillshare](https://github.com/runkids/skillshare)? Install and sync this plugin to Claude Code and Codex alongside your other agent plugins:

```bash
skillshare plugin add runkids/agents-context-router \
  --plugin agents-context-router \
  --target claude --target codex --global
skillshare sync plugins
```

Skillshare keeps complete native plugins in one place and shows each agent's install status. See the [plugin command guide](https://skillshare.runkids.cc/docs/reference/commands/plugin/).

### Other skill-compatible agents

Install it as a skill with [Vercel's Skills CLI](https://github.com/vercel-labs/skills):

```bash
npx skills add runkids/agents-context-router
```

## Use it

In a repository with bloated agent docs, ask your coding agent:

> “Our `AGENTS.md` is too big. Split it into a small kernel and task-specific wiki topics.”

The skill measures the current context, reorganizes the docs, wires the router, and checks the result. It also handles overlapping `CLAUDE.md` rules and preserves milestone logs in their original language.

After the refactor, the generated script works in that repository:

```bash
python3 scripts/ai-context.py list
python3 scripts/ai-context.py debugging
python3 scripts/ai-context.py check
```

`list` shows available topics. A topic command prints only its mapped sections, marked with their source paths. `check` validates the router and its configured limits.

## Repository layout

```text
AGENTS.md                 Always-loaded rules and topic index
docs/ai-context.json      Topic-to-document map
scripts/ai-context.py     Print topics and check the docs
wiki/<topic>.md           Task-specific guides and runbooks
wiki/history/*.md         Dated records, kept out of default context
wiki/README.md            Human-readable topic and history index
```

The bundled script uses only the Python standard library (Python 3.8+). Exact-heading references fail if a heading is missing or duplicated, so a renamed section cannot silently route the wrong instructions.

## Contributing

Issues and pull requests are welcome. The skill workflow and eval prompts are in [`skills/agents-context-router/`](skills/agents-context-router/).

## License

MIT

---

If this helps keep your agent's context focused, give the repo a ⭐ so more developers can find it.
