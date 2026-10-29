# Change review

Use the project skill `agents-context-router-code-review` before committing or
pushing changes and when reviewing an external PR. It checks correctness, repo
rules, the request, consumers and cleanup independently, then verifies findings.
Review requests are read-only unless fixes are authorized.

## Consumer coverage

| Changed concept | Check together |
| --- | --- |
| Router commands or behavior | `skills/agents-context-router/scripts/ai-context.py`, its routed fixture copy, CLI tests, skill instructions, manual template and README locales |
| Config or checks | `assets/ai-context.json`, manual template, fixture config/docs and regressions under the public skill |
| Skill guidance | Public `SKILL.md`, referenced templates and relevant README examples; preserve standalone maintenance docs in generated repos |
| Native installation | `package.json`, root `plugin.json`, platform manifests, marketplace entries and README locales; only claim clients actually verified |
| Version or release | `release-please-config.json`, tracking manifest, every configured version field, source markers, changelog, workflows and `docs/releasing.md` |
| Maintainer workflows | `.skillshare/skills/`, project config, this guide and release guide; keep them outside the public `skills/` bundle |

The source router and its fixture copy must remain identical. The manual
template and routed fixture manual must remain identical. Preserve current
path-containment, symlink, encoding and Markdown validation behavior.

## Verification

Run the relevant commands under **Local checks** in `docs/releasing.md`, and
`git diff --check`. For skill edits, validate frontmatter, referenced paths and
project target discovery. For workflow edits, use actionlint when available.
CI covers Python 3.8 on Linux and Python 3.13 on Linux, macOS and Windows;
local checks do not establish a green remote matrix.

Before delivery, simplify the diff and confirm each finding with a concrete
scenario. For an open PR, inspect reviews and CI for its current head, not an
older reviewed commit. Sending a comment, requesting another review or pushing
fixes requires authorization. An authorized direct push to `main` does not
require opening a PR or requesting an external review.
