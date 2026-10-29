# Versioning and releases

The repository, native plugins, Pi package, skill and bundled router share one
SemVer version. `package.json` records the source version;
`.release-please-manifest.json` tracks it for Release Please. `0.0.0` is an
unreleased bootstrap baseline. With no previous release tag, that tracking entry
does not select the first release version. This repository selects `0.1.0` with
a `Release-As: 0.1.0` commit footer; later releases follow the policy below.

`release-please-config.json` lists the other version fields under `extra-files`.
Release Please updates them in the same Release PR. Keep the annotated version
lines in the skill, Hermes manifest and both router copies so they update too.
Run `python3 scripts/check-version.py` to detect missing markers or version drift.

The project skill `agents-context-router-release` walks through preparation,
review and publication. Set up this and the review skill with the Skillshare
commands in the README's Contributing section. Maintainer skills are separate
from the public router skill and follow the checked-out repository revision.

## Contributions

Use English Conventional Commit subjects for PR titles and commits:

- `fix:` for corrections, including corrections to skill behavior.
- `feat:` for new behavior in the skill or router, or a new supported agent.
- `docs:` for explanatory or formatting changes that leave behavior unchanged.
- Use `!` or a `BREAKING CHANGE:` footer for incompatible changes.

Fixes bump the patch; features bump the minor. While below `1.0.0`, breaking
changes bump the minor; from `1.0.0`, they bump the major. Docs, tests and chores
alone do not create a release. Skill instructions are product behavior even
though they are Markdown, so classify their changes by effect.

For an explicit next version, add a `Release-As: X.Y.Z` footer to the final
pending commit. Preserve it in the squash commit message when merging.
Review the proposed version before merging the Release PR.

## Release flow

1. A push to `main` runs the reusable Check workflow, then Release Please opens
   or updates a Release PR with the version changes and changelog.
2. Review the version, changes and checks. With the default `GITHUB_TOKEN`,
   bot-created PRs may not trigger another workflow. Run the Check workflow
   manually against the Release PR branch before merging it.
3. Merge the Release PR when ready. The `main` workflow runs checks before
   Release Please creates its `vX.Y.Z` tag and a GitHub
   **draft** release. Tag creation is explicit so later releases can find it.
4. Review and edit the draft notes into a concise user-facing description,
   including contributor credit where appropriate. Confirm the tag points to
   the approved revision, then publish the draft manually on GitHub.

Tags are usable for pinned Git installs as soon as step 3 completes. No workflow
publishes the draft or pushes an npm package. Pi can install directly from Git.

Repository setup requires **Settings → Actions → General → Workflow permissions →
Allow GitHub Actions to create and approve pull requests**. The workflows declare
their own permissions; no PAT is required. If repository rules require PR checks,
make sure the manually dispatched Check run on the Release PR branch satisfies
those rules before merging.

## Local checks

```sh
python3 scripts/check-version.py
python3 -m unittest discover -s tests
python3 -m unittest discover -s skills/agents-context-router/evals -p 'test_*.py'
python3 skills/agents-context-router/evals/fixtures/routed/scripts/ai-context.py check
```

Use `python` or `py -3` instead of `python3` on Windows. CI checks Python 3.8 on
Linux and Python 3.13 on Linux, macOS and Windows.

## Installed copies

Run `python3 scripts/ai-context.py --version` in a routed repository to identify
the release its copied script came from. This command does not require a config.
Updating the installed skill does not update existing copied scripts. Compare
local customizations before replacing a copied router; retain the repository's
config and documentation.

## Native package checks

Pi uses `package.json` and its `pi.skills` entry; no extension or startup hook is
required. To test a checkout, run `pi -e /path/to/agents-context-router` and confirm
`agents-context-router` appears in the available skills.

Antigravity uses the root `plugin.json` and the same `skills/` directory.
Validate a checkout with `agy plugin validate /path/to/agents-context-router --strict`.
After installing, use `agy plugin list --json` to confirm the plugin and skill.

The shared layout is based on the [Agent Skills specification](https://agentskills.io/specification),
[Pi packages](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/packages.md)
and [Antigravity plugins](https://antigravity.google/docs/plugins).
