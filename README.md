# agents-context-router

**English** | [日本語](README.ja.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md) | [繁體中文](README.zh-TW.md)

Keep your agent instructions short. Load the project details only when a task needs them.

`agents-context-router` helps coding agents turn an oversized `AGENTS.md` into a small shared kernel and a set of task-specific wiki topics. A lightweight Python script prints only the selected topic; history stays available without loading into every task.

<p align="center">
  <img src="assets/context-router-stars.svg" alt="A friendly star routes a coding task to the right project docs" width="100%">
</p>

## The idea

Keep rules that apply to every task in `AGENTS.md`. Move runbooks and reference material into topic pages, and keep dated notes in history. The agent reads the kernel, chooses a topic, and loads only that topic.

<p align="center">
  <img src="assets/context-router-comic-overload.svg" alt="A three-panel comic: a long instruction file overwhelms an agent, a buried rule is found, and the docs are reorganized" width="100%">
</p>

<p align="center">
  <img src="assets/context-router-comic-routing.svg" alt="A three-panel comic showing a task routed through a small kernel to one matching wiki topic" width="100%">
</p>

## What it does

- Measures always-loaded instruction files before and after the split.
- Sorts content into a small kernel, task topics, history, and human docs.
- Routes each topic to whole files or exact Markdown headings through `wiki/ai-context.json`.
- Bundles `scripts/ai-context.py`, a dependency-free router with `list`, topic, and `check` commands.
- Checks byte budgets, missing or ambiguous headings, unlisted topics, orphaned wiki/history files, and broken relative Markdown file links.
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

### Antigravity

Install the plugin with the Antigravity CLI:

```bash
agy plugin install https://github.com/runkids/agents-context-router
```

The root `plugin.json` exposes the same skills; no extra setup is needed. Reinstall with the same command to update.

### Skillshare

Already use [Skillshare](https://github.com/runkids/skillshare)? Install it as a plain skill and sync it to all your targets:

```bash
skillshare install runkids/agents-context-router --global
skillshare sync
```

Or install the complete native plugin and sync it to Claude Code and Codex alongside your other agent plugins:

```bash
skillshare plugin add runkids/agents-context-router \
  --plugin agents-context-router \
  --target claude --target codex --global
skillshare sync plugins
```

Skillshare keeps complete native plugins in one place and shows each agent's install status. See the [plugin command guide](https://skillshare.runkids.cc/docs/reference/commands/plugin/).

### Pi

Pi loads the skill directly from `package.json` without an extension or startup hook.

```bash
pi install git:github.com/runkids/agents-context-router
```

To pin a published release, append `@vX.Y.Z` to the Git source, replacing `vX.Y.Z` with an existing tag. Pinned tags stay pinned during updates.

### Hermes, Kimi Code and Muse

Native manifests for more agents live in this repository:

```bash
# Hermes Agent
hermes plugins install runkids/agents-context-router --enable

# Muse
git clone https://github.com/runkids/agents-context-router.git
muse plugins install ./agents-context-router
muse plugins approve agents-context-router
```

```text
# Kimi Code
/plugins install https://github.com/runkids/agents-context-router
```

### Other skill-compatible agents

Install it as a skill with [Vercel's Skills CLI](https://github.com/vercel-labs/skills):

```bash
npx skills add runkids/agents-context-router
```

## Versions

The package, native plugins, skill and bundled router share one version. `0.0.0` is an unreleased bootstrap baseline; published versions have Git tags and [release notes](https://github.com/runkids/agents-context-router/releases). Read the [release guide](docs/releasing.md) for contribution and release policy.

Copied routers retain their source version. Run `python3 scripts/ai-context.py --version` to identify it; updating the skill does not replace existing copies.

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

`list` shows available topics. A topic command prints only its mapped sections, marked with their source paths. `check` validates the router and its configured limits. Relative Markdown links are always checked in complete routed sources, wiki pages (including history and routing exceptions), and pages matched by optional `indexed` patterns. Destinations resolve from the containing page and must be files inside the repository; heading fragments are not validated.

You can also keep one installed script outside the repository, with no local `scripts/` directory:

```bash
AI_CONTEXT_ROOT=/work/repo AI_CONTEXT_CONFIG=/work/settings/router.json \
  python3 /opt/tools/ai-context.py check
```

Use the same environment for `list` and topic commands, and record it in the kernel's load-context commands and verification hooks. Without overrides, the root is the script's parent's parent and the config is `<root>/wiki/ai-context.json`. A symlink outside a `scripts/` directory whose own parent's parent has no `wiki/ai-context.json`, such as `~/.local/bin/ai-context` pointing at `/work/repo/scripts/ai-context.py`, uses the target's parent's parent unless `AI_CONTEXT_CONFIG` is set. Only runs that would otherwise fail on a missing config change; a symlink inside `scripts/` is that repo's copy and keeps its own root. `AI_CONTEXT_ROOT` alone selects that repo's default config; `AI_CONTEXT_CONFIG` alone keeps the script-derived root. Empty or unset overrides use the defaults.

Both selections are canonicalized. Explicit relative overrides resolve independently from the invocation's current working directory: from `/work`, root `repo` and config `settings/router.json` select `/work/repo` and `/work/settings/router.json`. Relative paths inside the JSON resolve from the selected root, even with an external config. The script does not expand `~` or shell variables; use absolute paths or let your shell expand them.

Deliberate orphan exceptions go under `"unrouted"` as exact paths or fnmatch globs, each with a reason. For example, `"projects/*/AGENTS.md": "Agents load these scoped instructions by cwd."` exempts those files. Matching is case-sensitive, and backslashes in keys normalize to `/`. `*`, `?` and bracket classes follow Python fnmatch semantics: `*` can cross `/`, so that example also matches `projects/team/api/AGENTS.md`; `**` has no special recursive meaning. Keys match themselves and also act as patterns, regardless of file existence: `wiki/file[1].md` exempts both itself and `wiki/file1.md`. Use `wiki/file[[]1].md` to exempt the literal bracketed filename without also exempting `wiki/file1.md`. Unmatched orphans still fail `check`.

Keep `check` out of bulky trees that hold no instructions, such as generated output or evidence dumps, with `"skipDirs": ["projects/*/artifacts"]` (default `[]`). Entries are exact repo-relative directory paths or case-sensitive fnmatch globs, matched like `"unrouted"` keys (`*` crosses `/`). `check` does not walk into a matching directory, so its pages are not checked for orphans, indexed naming or links unless a topic routes them. The wiki directory is always walked.

Opt in to discoverability checks outside the wiki with `"indexed": ["projects/*/*-runbook.md"]` (default `[]`). Matching `.md` pages must be topic sources or have their full repo-relative paths named in root instructions, the router index, or rendered topic text. A matching exact path or case-sensitive `"unrouted"` glob also exempts an indexed page when at least one matching reason is a nonblank string. Blank or non-string reasons preserve legacy orphan exceptions, but do not satisfy indexed checks. Indexing includes hidden, dependency, and build directories, excludes `.git`, and does not follow directory symlinks. Indexed patterns use Python fnmatch semantics: `*` crosses `/`; matching is case-sensitive on POSIX and follows platform normalization on Windows. Indexed references do not bypass the existing wiki, history, or nested-instructions checks.

## Repository layout

```text
AGENTS.md                 Always-loaded rules and topic index
wiki/ai-context.json      Topic-to-document map
scripts/ai-context.py     Print topics and check the docs
wiki/<topic>.md           Task-specific guides and runbooks
wiki/history/*.md         Dated records, kept out of default context
wiki/README.md            Human-readable topic and history index
```

The bundled script uses only the Python standard library (Python 3.8+). Examples use `python3`; on Windows use `python` or `py -3` instead. The skill tells the agent to pick the right command when it installs the router. Exact-heading references fail if a heading is missing or duplicated, so a renamed section cannot silently route the wrong instructions.

## Contributing

Issues and pull requests are welcome. The skill workflow and eval prompts are in [`skills/agents-context-router/`](skills/agents-context-router/).

Maintainers can load the project review and release skills through Skillshare:

```sh
skillshare install -p
skillshare sync -p
```

The project config syncs `.skillshare/skills/` to `universal` and `claude`.
Use `agents-context-router-code-review` before committing or pushing, and
`agents-context-router-release` for releases. See the [review guide](docs/review.md)
and [release guide](docs/releasing.md). These maintainer skills are not part of
the public router skill bundle.

## License

MIT

---

If this helps keep your agent's context focused, give the repo a ⭐ so more developers can find it.
