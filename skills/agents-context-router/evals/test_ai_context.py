"""Combined CLI regressions for indexing, shared installs, and relative links."""
from contextlib import redirect_stdout
import importlib.util
import io
import itertools
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote


SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / 'scripts/ai-context.py'
PAGE = 'projects/api/deploy-runbook.md'
spec = importlib.util.spec_from_file_location('ai_context', SCRIPT)
router = importlib.util.module_from_spec(spec)
spec.loader.exec_module(router)


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.script = self.root / 'scripts/ai-context.py'
        self.script.parent.mkdir()
        shutil.copy2(SKILL / 'scripts/ai-context.py', self.script)
        self.write('AGENTS.md', '`guide`\n')
        self.write('wiki/guide.md', '# Guide\nUse this guide.\n')
        self.write(PAGE, '# Deploy\nRun deployment.\n')
        self.cfg = {'topics': {'guide': {
            'description': 'Guide', 'sources': [{'path': 'wiki/guide.md'}]}},
            'indexed': ['projects/*/*-runbook.md']}

    def write(self, path, text):
        dest = self.root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding='utf-8')

    def run_cli(self, *args):
        self.write('wiki/ai-context.json', json.dumps(self.cfg))
        env = {k: v for k, v in os.environ.items()
               if k not in ('AI_CONTEXT_ROOT', 'AI_CONTEXT_CONFIG')}
        return subprocess.run([sys.executable, str(self.script), *args],
                              env=env, capture_output=True, encoding='utf-8')

    def check(self, code):
        result = self.run_cli('check')
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')
        return result.stdout

    def test_indexed_opt_in(self):
        for patterns, code in [(None, 0), ([], 0), (['projects/*/*-runbook.md'], 1)]:
            with self.subTest(patterns=patterns):
                self.cfg.pop('indexed', None)
                if patterns is not None:
                    self.cfg['indexed'] = patterns
                output = self.check(code)
                if code:
                    self.assertIn('FAIL ' + PAGE, output)
                    for remedy in ['name it in a topic page', 'route it', '"unrouted" with a reason']:
                        self.assertIn(remedy, output)
        self.write('AGENTS.md', f'`guide`\n{PAGE}\n')
        renamed = 'projects/api/new-runbook.md'
        (self.root / PAGE).rename(self.root / renamed)
        self.assertIn('FAIL ' + renamed, self.check(1))

    def test_indexed_references(self):
        for surface in ['root', 'router', 'topic', 'section', 'source', 'source-section', 'basename', 'relative', 'relative-full']:
            with self.subTest(surface=surface):
                self.write('AGENTS.md', '`guide`\n' + (PAGE if surface == 'root' else ''))
                self.cfg['routerFile'] = 'docs/router.md'
                self.write('docs/router.md', PAGE if surface == 'router' else '')
                self.write('wiki/guide.md', '# Guide\n' + (
                    'deploy-runbook.md' if surface == 'basename' else
                    f'[Deploy](../{PAGE})' if surface == 'relative-full' else
                    PAGE if surface in ['topic', 'section'] else 'Use this guide.'))
                sources = [{'path': 'wiki/guide.md'}]
                if surface == 'section':
                    sources[0]['heading'] = 'Guide'
                if surface == 'relative':
                    self.write('projects/api/topic.md', '[Deploy](./deploy-runbook.md)')
                    sources.append({'path': 'projects/api/topic.md'})
                if surface in ['source', 'source-section']:
                    sources.append({'path': PAGE})
                    if surface == 'source-section':
                        sources[-1]['heading'] = 'Deploy'
                self.cfg['topics']['guide']['sources'] = sources
                self.check(1 if surface in ['basename', 'relative'] else 0)

    def test_selected_heading_only(self):
        self.cfg['topics']['guide']['sources'][0]['heading'] = 'Selected'
        for selected, other, code in [('Read this.', PAGE, 1), (PAGE, 'Read this.', 0)]:
            with self.subTest(code=code):
                self.write('wiki/guide.md', f'# Guide\n## Selected\n{selected}\n## Other\n{other}\n')
                self.check(code)

    def test_exact_unrouted_reason(self):
        for exceptions, code in [({}, 1), ({PAGE: ''}, 1), ({PAGE: ' \t\n'}, 1),
                                 ({PAGE: None}, 1), ({PAGE: 'Human only'}, 0),
                                 ({PAGE.replace('/', '\\'): 'Human only'}, 0),
                                 ({'projects/*/*.md': 'Human only'}, 0)]:
            with self.subTest(exceptions=exceptions):
                self.cfg['unrouted'] = exceptions
                self.check(code)

    def test_unrouted_globs_and_indexed_overlap(self):
        for path in [PAGE, 'wiki/extra.md', 'wiki/history/log.md',
                     'pkg/AGENTS.md', 'vendor/api/runbook.md']:
            self.write(path, '# Deliberate exception\n')
            self.cfg['indexed'] = [path]
            pattern = path.split('/')[0] + '/*'
            for reason in ['Human only', '', ' \t\n', None, 123]:
                with self.subTest(path=path, reason=reason):
                    self.cfg['unrouted'] = {pattern: reason}
                    output = self.check(0 if reason == 'Human only' else 1)
                    if reason != 'Human only':
                        self.assertIn('FAIL ' + path + ': indexed page not named', output)
                        self.assertIn('1 problem(s)', output)
            if path != PAGE:
                (self.root / path).unlink()
        self.cfg['indexed'] = ['projects/*/*-runbook.md']
        for exceptions, code in [
                ({'projects\\*\\*.md': 'Human only'}, 0),
                ({PAGE: '', 'projects/*': 'Human only'}, 0),
                ({PAGE: 'Human only', 'projects/*': ''}, 0),
                ({'PROJECTS/*': 'Human only'}, 1),
                ({'other/*': 'Human only'}, 1)]:
            with self.subTest(exceptions=exceptions):
                self.cfg['unrouted'] = exceptions
                self.check(code)

    def test_indexed_matching(self):
        self.cfg['indexed'] = ['projects/*/*-runbook.md', '**/*.md', '*.txt']
        self.write('projects/api/readme.txt', 'Not Markdown.\n')
        output = self.check(1)
        self.assertEqual(output.count('FAIL ' + PAGE + ':'), 1)
        self.assertIn('1 problem(s)', output)
        if os.name == 'posix':
            self.cfg['indexed'] = ['PROJECTS/*.md']
            self.check(0)

    def test_indexed_traversal_preserves_legacy_scope(self):
        self.write('.git/internal/runbook.md', 'Git metadata.\n')
        for prefix in ['.internal', 'vendor', 'build']:
            with self.subTest(prefix=prefix):
                page = f'{prefix}/api/deploy-runbook.md'
                for path in [page, f'{prefix}/AGENTS.md', f'{prefix}/wiki/extra.md',
                             f'{prefix}/wiki/history/m1.md']:
                    self.write(path, '# Extra\n')
                self.cfg.update(wikiDir=f'{prefix}/wiki', historyDir=f'{prefix}/wiki/history')
                self.write('AGENTS.md', '`guide`\n')
                self.cfg.pop('indexed', None)
                self.check(0)
                self.cfg['indexed'] = []
                self.check(0)
                self.cfg['indexed'] = [f'{prefix}/api/*-runbook.md', '.git/**/*.md']
                output = self.check(1)
                self.assertIn('FAIL ' + page, output)
                self.assertIn('1 problem(s)', output)
                self.write('AGENTS.md', f'`guide`\n{page}\n')
                self.check(0)

    def test_invalid_indexed(self):
        for value in ['projects/*.md', None, [123], {'projects/*.md': True}]:
            with self.subTest(value=value):
                self.cfg['indexed'] = value
                self.assertIn('FAIL indexed: expected a list of strings', self.check(1))

    def test_existing_orphan_rules(self):
        for path, detail in [('wiki/extra.md', 'wiki page no topic loads'),
                             ('wiki/history/m1.md', 'history file not indexed'),
                             ('pkg/AGENTS.md', 'scoped instructions no topic loads')]:
            with self.subTest(path=path):
                self.write(path, '# Extra\n')
                self.write('AGENTS.md', f'`guide`\n{PAGE}\n{path}\n')
                self.cfg['indexed'] = ['**/*.md']
                self.cfg['unrouted'] = {}
                self.assertIn(f'FAIL {path}: {detail}', self.check(1))
                # Legacy exact exceptions still permit empty reasons when not indexed.
                self.cfg['indexed'] = ['projects/*.md']
                self.cfg['unrouted'] = {path: ''}
                self.check(0)
                (self.root / path).unlink()

    def test_render_errors_survive(self):
        for text, heading, detail in [(None, None, 'No such file'),
                                      ('# Guide\n', 'Absent', "heading 'Absent' found 0x"),
                                      ('# Guide\n# Guide\n', 'Guide', "heading 'Guide' found 2x")]:
            with self.subTest(detail=detail):
                source = {'path': 'wiki/guide.md'}
                if text is None:
                    (self.root / source['path']).unlink()
                else:
                    self.write(source['path'], text)
                    source['heading'] = heading
                self.cfg['topics']['guide']['sources'] = [source]
                output = self.check(1)
                self.assertIn('FAIL guide:', output)
                self.assertIn(detail, output)
                self.assertIn('FAIL ' + PAGE, output)

    def test_existing_commands_and_fixture(self):
        for args, expected in [(('list',), 'guide              Guide\n'),
                               (('guide',), '<!-- wiki/guide.md -->\n# Guide\nUse this guide.\n')]:
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual((result.returncode, result.stdout, result.stderr), (0, expected, ''))
        fixture = self.root / 'fixture'
        shutil.copytree(SKILL / 'evals/fixtures/routed', fixture)
        shutil.copy2(SKILL / 'scripts/ai-context.py', fixture / 'scripts/ai-context.py')
        result = subprocess.run([sys.executable, str(fixture / 'scripts/ai-context.py'), 'check'],
                                env={k: v for k, v in os.environ.items()
                                     if k not in ('AI_CONTEXT_ROOT', 'AI_CONTEXT_CONFIG')},
                                capture_output=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(result.stdout.endswith('ok\n'), result.stdout)
        self.assertEqual(result.stderr, '')


class LinkCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / 'repo'
        self.root.mkdir()
        self.write('scripts/ai-context.py', SCRIPT.read_text(encoding='utf-8'))
        self.write('AGENTS.md', '`guide`\n')
        self.write('wiki/README.md', 'history/log.md\n')
        self.cfg = {'topics': {'guide': {'description': 'Guide', 'sources': [
            {'path': 'wiki/guide.md', 'heading': 'Selected'}]}}}
        self.write('wiki/guide.md', '# Selected\nHello\n')
        self.save_cfg()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def save_cfg(self):
        self.write('wiki/ai-context.json', json.dumps(self.cfg))

    def cli(self, *args):
        env = {k: v for k, v in os.environ.items()
               if k not in ('AI_CONTEXT_ROOT', 'AI_CONTEXT_CONFIG')}
        return subprocess.run([sys.executable, str(self.root / 'scripts/ai-context.py'),
                               *args], env=env, capture_output=True, text=True)

    def problems(self, text):
        self.write('wiki/guide.md', '# Selected\n' + text)
        old_root = router.ROOT
        try:
            router.ROOT = str(self.root)
            return router.link_problems(self.cfg)
        finally:
            router.ROOT = old_root

    def test_cli_missing_link_outside_selected_heading(self):
        self.write('wiki/guide.md', '# Selected\nHello\n# Other\n[Retry](../notes/renamed.md)\n')
        result = self.cli('check')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('wiki/guide.md:4:', result.stdout)
        self.assertIn('../notes/renamed.md', result.stdout)
        self.assertEqual(self.cli('guide').stdout,
                         '<!-- wiki/guide.md § Selected -->\n# Selected\nHello\n')

    def test_inline_destinations_and_titles(self):
        self.write('wiki/a(b).md', '')
        self.write('wiki/space name.md', '')
        for destination in ['a(b).md', r'a\(b\).md', '<space name.md>',
                            'a(b).md "title"', "a(b).md 'title'", 'a(b).md (title)']:
            for mark in ['[link]', '![image]']:
                with self.subTest(destination=destination, mark=mark):
                    self.assertEqual(self.problems(mark + '(' + destination + ')'), [])
        self.assertEqual(len(self.problems('[label](missing(a).md "title")')), 1)
        self.assertEqual(len(self.problems('![label](<missing file.png>)')), 1)

    def test_used_references_report_definition_once(self):
        text = '[Full][ Some ID ]\n![Some ID][]\n[Some ID]\n\n[some id]: <missing file.md> "title"\n'
        errors = self.problems(text)
        self.assertEqual(len(errors), 1)
        self.assertIn('wiki/guide.md:6:', errors[0])
        self.assertIn('missing file.md', errors[0])
        for usage in ['[x][id]', '[id][]', '[id]', '![id]']:
            with self.subTest(usage=usage):
                self.assertEqual(len(self.problems('[id]: missing.md\n' + usage)), 1)
        self.assertEqual(self.problems('[unused]: missing.md\n[undefined]\n'), [])
        self.write('wiki/good.md', '')
        self.assertEqual(self.problems('[id]\n[id]: good.md\n[id]: missing.md'), [])
        self.assertEqual(len(self.problems(r'[a\*b]' + '\n[a*b]: missing.md')), 1)

    def test_code_escapes_and_original_lines(self):
        text = ('```md\n[x](missing.md)\n```\n~~~\n[id]\n~~~\n'
                '`[x](missing.md)` and `` `[id]` ``\n'
                r'\[x](missing.md)' + '\n' + r'!\[x](missing.md)' + '\n'
                '[unused]: missing.md\n[id]: missing.md\n[live](missing.md)\n')
        errors = self.problems(text)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn('wiki/guide.md:13:', errors[0])
        self.assertEqual(self.problems('`example\n[x](missing.md)\n`'), [])
        self.assertEqual(len(self.problems('` unmatched [x](missing.md)')), 1)
        self.assertEqual(len(self.problems(r'\` [x](missing.md) `')), 1)

    def test_exclusions_and_url_decoding(self):
        for target in ['https://example.test/a', 'mailto:a@b.test', 'custom:thing',
                       '//example.test/a', '/absolute/path', '#heading', '?query', '']:
            with self.subTest(target=target):
                self.assertEqual(self.problems('[x](' + target + ')'), [])
        self.write('wiki/space #中文.md', '')
        self.assertEqual(self.problems('[x](space%20%23%E4%B8%AD%E6%96%87.md?q#h)'), [])
        self.assertEqual(len(self.problems('[x](missing.md?query#heading)')), 1)
        self.write('wiki/existing.md', '')
        self.assertEqual(self.problems('[x](existing.md#no-such-heading)'), [])

    def test_containment_and_file_targets(self):
        outside = self.root.parent / 'repo-lookalike'
        outside.mkdir()
        (outside / 'file.md').write_text('outside', encoding='utf-8')
        (self.root / 'wiki' / 'escape').symlink_to(outside, target_is_directory=True)
        self.write('inside.md', '')
        (self.root / 'wiki' / 'inside.md').symlink_to(self.root / 'inside.md')
        self.assertEqual(self.problems('[x](../inside.md) [x](inside.md)'), [])
        for target in ['../wiki', '..', '../../repo-lookalike/file.md',
                       '%2e%2e/%2e%2e/repo-lookalike/file.md', 'escape/file.md', '%00.md']:
            with self.subTest(target=target):
                self.assertEqual(len(self.problems('[x](' + target + ')')), 1)

    def test_inventory_deduplicates_and_includes_unrouted_history_router(self):
        self.cfg['topics']['guide']['sources'].append({'path': 'wiki/guide.md'})
        self.cfg['unrouted'] = {'wiki/extra.md': 'human only'}
        self.write('wiki/extra.md', '[x](missing.md)')
        self.write('wiki/history/log.md', '[x](missing.md)')
        self.write('wiki/README.md', 'history/log.md\n[x](missing.md)')
        errors = self.problems('[x](missing.md)')
        self.assertEqual(len(errors), 4, errors)
        self.assertEqual({e.split(':')[0] for e in errors},
                         {'wiki/guide.md', 'wiki/extra.md', 'wiki/history/log.md', 'wiki/README.md'})
        self.cfg.update(wikiDir='docs', routerFile='INDEX.md')
        self.cfg['topics']['guide']['sources'] = [{'path': 'notes/source.txt'}]
        self.write('notes/source.txt', '[x](missing.md)')
        self.write('docs/extra.md', '[x](missing.md)')
        self.write('INDEX.md', '[x](missing.md)')
        errors = self.problems('hello')
        self.assertEqual({e.split(':')[0] for e in errors},
                         {'notes/source.txt', 'docs/extra.md', 'INDEX.md'})

    def test_bounded_generated_filenames_existing_then_missing(self):
        # Exhaustive small alphabet; failures stay reproducible as individual subtests.
        for parts in itertools.product(['a', ' ', '#', '中', '(', ')'], repeat=2):
            name = ''.join(parts) + '.md'
            target = self.root / 'wiki' / name
            target.write_text('', encoding='utf-8')
            text = '[generated](' + quote(name, safe='') + ')'
            with self.subTest(name=name):
                self.assertEqual(self.problems(text), [])
                target.unlink()
                errors = self.problems(text)
                self.assertEqual(len(errors), 1)
                self.assertIn('wiki/guide.md:2:', errors[0])
                self.assertIn(quote(name, safe=''), errors[0])

    def test_nested_and_wrapped_links_restore_then_rename(self):
        cases = ['[Read **[the guide]**](target.md)', '[guide](\ntarget.md)',
                 '[multi\nline](target.md\n "title")', '![alt [nested]](<target.md>)',
                 '[guide](\n<target.md>\n)', '[x][id]\n\n[id]:\n  target.md',
                 '[x][multi\n id]\n\n[multi id]: target.md "title"']
        for text in cases:
            with self.subTest(text=text):
                self.write('wiki/target.md', '')
                self.assertEqual(self.problems(text), [])
                (self.root / 'wiki/target.md').unlink()
                errors = self.problems(text)
                self.assertEqual(len(errors), 1, errors)
                self.assertIn('wiki/guide.md:', errors[0])
                self.assertIn('target.md', errors[0])
        self.write('wiki/guide.md', '# Selected\n[Read [nested]](\nmissing.md)')
        result = self.cli('check')
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn('wiki/guide.md:2:', result.stdout)
        self.assertEqual(self.problems('[x](\n\nmissing.md)\n[id]:\n\nmissing.md'), [])

    def test_context_masks_examples_but_keeps_live_continuations(self):
        examples = ['\n    [x](missing.md)', '\n\t[x](missing.md)',
                    '\n>     [x](missing.md)', '- item\n\n      [x](missing.md)',
                    '> ```md\n> [x](missing.md)\n> ```',
                    '- ```md\n  [x](missing.md)\n  ```',
                    '\n<!--\n```\n[x](missing.md)\n-->\n',
                    '\n<!--\n```\n-->\n```\n[x](missing.md)\n```\n',
                    '\n<pre>\n[x](missing.md)\n</pre>\n',
                    '\n<script>\n[x](missing.md)\n</script>\n',
                    '\n<div>\n[x](missing.md)\n</div>\n',
                    '\n    <!--\n\n', '\n    ```\n\n']
        for example in examples:
            with self.subTest(example=example):
                errors = self.problems(example + '\n[live](missing.md)')
                self.assertEqual(len(errors), 1, errors)
                self.assertIn('wiki/guide.md:' + str(example.count('\n') + 3) + ':', errors[0])
        for text in ['paragraph\n    [live](missing.md)', '- paragraph\n    [live](missing.md)',
                     '> paragraph\n>     [live](missing.md)', r'\![live](missing.md)',
                     '`<!--` [live](missing.md)', '[live](missing.md) <!-- hidden -->']:
            with self.subTest(text=text):
                self.assertEqual(len(self.problems(text)), 1)
        self.assertEqual(self.problems('<!-- [id] -->\n[id]: missing.md'), [])
        self.assertEqual(len(self.problems('`<!--\nexample` [live](missing.md)')), 1)
        self.assertEqual(self.problems('[x](existing[id].md)\n[id]: missing.md'),
                         ["wiki/guide.md:2: relative link 'existing[id].md' is not a file inside repo"])
        self.assertEqual(self.problems('[outer [id]](#anchor)\n[id]: missing.md'), [])
        self.assertEqual(len(self.problems('[![image][id]](#anchor)\n[id]: missing.md')), 1)
        self.assertEqual(self.problems('\n    [id]: missing.md\n\n[id]'), [])

    def test_entities_decode_before_url_classification(self):
        for name, dest in [('a&b.md', 'a&amp;b.md'), ('#.md', '&#35;.md'),
                           ('a b.md', 'a&#32;b.md'), ('a&b.md', 'a&#38;b.md')]:
            with self.subTest(dest=dest):
                self.write('wiki/' + name, '')
                # A leading decoded hash is an anchor and is intentionally ignored.
                self.assertEqual(self.problems('[x](' + dest + ')'), [])
                (self.root / 'wiki' / name).unlink()
                if name != '#.md':
                    self.assertEqual(len(self.problems('[x](' + dest + ')')), 1)
        self.assertEqual(self.problems('[x](https&#58;//example.test) [x](&#47;absolute)'), [])

    def test_lexical_aliases_keep_distinct_link_bases(self):
        self.write('docs/page.md', '[x](target.txt)')
        self.write('wiki/target.txt', '')
        (self.root / 'wiki/alias.md').symlink_to(self.root / 'docs/page.md')
        self.cfg['topics']['guide']['sources'] = [{'path': 'wiki/alias.md'}]
        self.assertEqual(self.problems('hello'), [])
        self.cfg['topics']['guide']['sources'].append({'path': 'docs/page.md'})
        for sources in [self.cfg['topics']['guide']['sources'],
                        list(reversed(self.cfg['topics']['guide']['sources']))]:
            self.cfg['topics']['guide']['sources'] = sources
            errors = self.problems('hello')
            self.assertEqual(len(errors), 1, errors)
            self.assertIn('docs/page.md:1:', errors[0])
        self.write('docs/target.txt', '')
        self.assertEqual(self.problems('hello'), [])

    def test_complete_wiki_walk_and_directory_alias_cycles(self):
        for folder in ['.private', 'build', 'vendor', 'node_modules']:
            self.write('wiki/' + folder + '/page.md', '[x](missing.md)')
        errors = self.problems('hello')
        self.assertEqual(len(errors), 4, errors)
        self.write('docs/guides/page.md', '[x](target.txt)')
        self.write('docs/guides/target.txt', '')
        (self.root / 'wiki/guides').symlink_to(self.root / 'docs/guides', target_is_directory=True)
        (self.root / 'docs/guides/cycle').symlink_to(self.root / 'wiki', target_is_directory=True)
        self.assertEqual(len(self.problems('hello')), 4)
        (self.root / 'docs/guides/target.txt').unlink()
        errors = self.problems('hello')
        self.assertEqual(len(errors), 5, errors)
        self.assertTrue(any('wiki/guides/page.md:1:' in error for error in errors))

    def test_nested_container_definitions_and_absolute_source_dedup(self):
        for text in ['- item\n  - [id]: target.txt\n\n    [id]',
                     '> - item\n>   - [id]: target.txt\n>\n>     [id]']:
            with self.subTest(text=text):
                self.write('wiki/target.txt', '')
                self.assertEqual(self.problems(text), [])
                (self.root / 'wiki/target.txt').unlink()
                errors = self.problems(text)
                self.assertEqual(len(errors), 1, errors)
                self.assertIn('wiki/guide.md:3:', errors[0])
        self.cfg['topics']['guide']['sources'].append({'path': str(self.root / 'wiki/guide.md')})
        self.assertEqual(len(self.problems('[x](missing.md)')), 1)

    def test_code_spans_cannot_hide_links_across_blank_paragraphs(self):
        text = '# Selected\n`unfinished\n\n[renamed](target.txt)\n\n`other\n'
        self.write('wiki/guide.md', text)
        for exists in [True, False, True]:
            if exists:
                self.write('wiki/target.txt', '')
            else:
                (self.root / 'wiki/target.txt').unlink()
            result = self.cli('check')
            self.assertEqual(result.returncode, 0 if exists else 1, result.stdout)
            if not exists:
                self.assertIn('wiki/guide.md:4:', result.stdout)

    def test_fence_closers_and_inline_html_keep_only_live_links(self):
        for mark in ['```', '~~~']:
            text = ('[before](missing.md)\n' + mark + '\n' + mark + 'not a closer\n'
                    '[example](missing.md)\n' + mark + '\n[after](missing.md)')
            errors = self.problems(text)
            self.assertEqual(len(errors), 2, errors)
            self.assertIn('wiki/guide.md:2:', errors[0])
            self.assertIn('wiki/guide.md:7:', errors[1])

    def test_inline_html_tokens_keep_surrounding_links(self):
        for tag in ['span', 'a']:
            text = ('[before](missing.md)\nText <' + tag + ' title="[example](missing.md)">'
                    'label</' + tag + '>\n[after](missing.md)')
            errors = self.problems(text)
            self.assertEqual(len(errors), 2, errors)
            self.assertIn('wiki/guide.md:2:', errors[0])
            self.assertIn('wiki/guide.md:4:', errors[1])

    def test_shipped_artifacts_match_distributable_assets(self):
        base = SCRIPT.parents[1]
        self.assertEqual(SCRIPT.read_bytes(), (base / 'evals/fixtures/routed/scripts/ai-context.py').read_bytes())
        self.assertEqual((base / 'assets/wiki-ai-context.md').read_bytes(),
                         (base / 'evals/fixtures/routed/wiki/ai-context.md').read_bytes())

    def test_exact_headings_keep_existing_fence_behavior(self):
        self.write('wiki/guide.md', '# Selected\n```sh\n# Selected\n````\n~~~\n# Other\n~~~\nbody\n# End\n')
        result = self.cli('guide')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('body', result.stdout)
        self.assertNotIn('# End', result.stdout)
        self.write('wiki/guide.md', '# Selected\n# Selected\n')
        result = self.cli('check')
        self.assertEqual(result.returncode, 1)
        self.assertIn("heading 'Selected' found 2x", result.stdout)




class RouterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cwd = Path(self.tmp.name)
        self.root = self.cwd / 'repo'
        self.write('AGENTS.md', '`guide`\n')
        self.write('wiki/guide.md', '# Guide\nRoot content.\n')
        self.write('wiki/README.md', '')
        self.cfg = {'topics': {'guide': {'description': 'Read the guide.',
                                       'sources': [{'path': 'wiki/guide.md'}]}}}
        self.save_config()
        self.local_script = self.root / 'scripts' / 'ai-context.py'

    def write(self, path, text):
        dest = self.root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding='utf-8')

    def save_config(self, path=None):
        path = path or self.root / 'wiki' / 'ai-context.json'
        path.write_text(json.dumps(self.cfg), encoding='utf-8')
        return path

    def run_cli(self, command, overrides=None, script=SCRIPT):
        env = {k: v for k, v in os.environ.items()
               if k not in ('AI_CONTEXT_ROOT', 'AI_CONTEXT_CONFIG')}
        env.update(overrides or {})
        return subprocess.run([sys.executable, str(script), command], cwd=self.cwd,
                              env=env, capture_output=True, text=True, encoding='utf-8')

    def assert_commands(self, overrides=None, script=SCRIPT, description='Read the guide.'):
        for command, expected in [('list', description),
                                  ('guide', '<!-- wiki/guide.md -->\n# Guide\nRoot content.'),
                                  ('check', '\nok\n')]:
            with self.subTest(command=command, overrides=overrides):
                result = self.run_cli(command, overrides, script)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(expected, result.stdout)

    def test_copied_script_defaults(self):
        self.local_script.parent.mkdir()
        shutil.copyfile(SCRIPT, self.local_script)
        for overrides in [{}, {'AI_CONTEXT_ROOT': ''}, {'AI_CONTEXT_CONFIG': ''},
                          {'AI_CONTEXT_ROOT': '', 'AI_CONTEXT_CONFIG': ''}]:
            self.assert_commands(overrides, script=self.local_script)

    def test_shared_root_and_external_config(self):
        self.assert_commands({'AI_CONTEXT_ROOT': str(self.root)})
        description = 'Read the externally configured guide.'
        self.cfg['topics']['guide']['description'] = description
        external = self.save_config(self.cwd / 'router.json')
        default = self.root / 'wiki' / 'ai-context.json'
        self.assertTrue(default.is_file())
        self.assertEqual(json.loads(default.read_text(encoding='utf-8'))['topics']['guide']['description'],
                         'Read the guide.')
        self.assert_commands({'AI_CONTEXT_ROOT': str(self.root), 'AI_CONTEXT_CONFIG': str(external)},
                             description=description)
        self.assertFalse(self.local_script.parent.exists())
        default.unlink()
        self.assert_commands({'AI_CONTEXT_ROOT': str(self.root), 'AI_CONTEXT_CONFIG': str(external)},
                             description=description)
        self.assert_commands({'AI_CONTEXT_ROOT': 'repo', 'AI_CONTEXT_CONFIG': 'router.json'},
                             description=description)

    def test_shared_unknown_topic_recovery(self):
        external = self.save_config(self.cwd / 'router.json')
        overrides = {'AI_CONTEXT_ROOT': str(self.root), 'AI_CONTEXT_CONFIG': str(external)}
        self.assertFalse(self.local_script.parent.exists())
        result = self.run_cli('missing-topic', overrides)
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stderr.startswith("unknown topic 'missing-topic'; "), result.stderr)
        self.assertIn('rerun this script with list', result.stderr)
        self.assertNotIn('scripts/ai-context.py', result.stderr)
        recovered = self.run_cli('list', overrides)
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertIn('Read the guide.', recovered.stdout)

    def test_config_only_keeps_script_root(self):
        self.local_script.parent.mkdir()
        shutil.copyfile(SCRIPT, self.local_script)
        external = self.save_config(self.cwd / 'router.json')
        (self.root / 'wiki' / 'ai-context.json').unlink()
        self.assert_commands({'AI_CONTEXT_CONFIG': str(external)}, self.local_script)

    def test_missing_selected_config(self):
        missing = self.cwd / 'missing.json'
        result = self.run_cli('list', {'AI_CONTEXT_CONFIG': str(missing)})
        self.assertNotEqual(result.returncode, 0)
        for text in [str(missing), 'AI_CONTEXT_ROOT', 'AI_CONTEXT_CONFIG']:
            self.assertIn(text, result.stderr)

    def test_plain_keys_match_exact_paths_and_globs_regardless_of_existence(self):
        cases = [
            ('projects/*/AGENTS.md', ['projects/api/AGENTS.md',
                                     'projects/team/api/AGENTS.md'], ['other/AGENTS.md']),
            ('windows\\*\\AGENTS.md', ['windows/api/AGENTS.md'], []),
            ('case/*/agents.md', [], ['case/api/AGENTS.md']),
            ('wiki/notes?.md', ['wiki/notes1.md'], ['wiki/notes12.md']),
            ('wiki/file[1].md', ['wiki/file[1].md', 'wiki/file1.md'], []),
            ('wiki/file[1].md', ['wiki/file1.md'], []),
            ('wiki/file[[]1].md', ['wiki/file[1].md'], ['wiki/file1.md']),
            ('wiki/reference.md', ['wiki/reference.md'],
             ['wiki/unmapped.md', 'wiki/history/unindexed.md']),
        ]
        if os.name != 'nt':
            cases += [('wiki/star*.md', ['wiki/star*.md', 'wiki/star2.md'], []),
                      ('wiki/question?.md', ['wiki/question?.md', 'wiki/question2.md'], [])]
        for key, exempt, unmatched in cases:
            with self.subTest(key=key, exempt=exempt):
                for path in exempt + unmatched:
                    self.write(path, '# Instructions\n')
                self.cfg['unrouted'] = {key: 'Deliberate exception.'}
                self.save_config()
                result = self.run_cli('check', {'AI_CONTEXT_ROOT': str(self.root)})
                self.assertEqual(result.returncode, 1 if unmatched else 0,
                                 result.stdout + result.stderr)
                failures = {line.split(':', 1)[0][5:] for line in result.stdout.splitlines()
                            if line.startswith('FAIL ')}
                self.assertEqual(failures, set(unmatched))
            for path in exempt + unmatched:
                (self.root / path).unlink()

    def test_filesystem_anchor_allows_temporary_sources(self):
        self.write('wiki/guide.md', '# Guide\nRoot content.\n[Target](target.txt)\n')
        self.write('wiki/target.txt', 'Inside the selected filesystem root.\n')
        anchor = Path(self.root.anchor)
        source = (self.root / 'wiki' / 'guide.md').relative_to(anchor).as_posix()
        self.cfg['topics']['guide']['sources'] = [{'path': source}]
        self.cfg['rootInstructions'] = str(self.root / 'AGENTS.md')
        self.cfg['routerFile'] = str(self.root / 'wiki' / 'README.md')
        self.cfg['wikiDir'] = str(self.root / 'wiki')
        external = self.save_config(self.cwd / 'router.json')
        overrides = {'AI_CONTEXT_ROOT': str(anchor), 'AI_CONTEXT_CONFIG': str(external)}
        with self.subTest(command='guide'):
            result = self.run_cli('guide', overrides)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('<!-- ' + source + ' -->\n# Guide\nRoot content.', result.stdout)
        with self.subTest(command='check'), patch.dict(os.environ, overrides):
            router = runpy.run_path(str(SCRIPT))
            # Only traversal is mocked: never walk the filesystem anchor.
            with patch('os.walk', return_value=[]), redirect_stdout(io.StringIO()) as output:
                status = router['check'](router['load_cfg']())
            self.assertEqual(status, 0, output.getvalue())
            self.assertIn('\nok\n', output.getvalue())

    def test_external_config_does_not_allow_sources_outside_root(self):
        (self.cwd / 'outside.md').write_text('Outside content.', encoding='utf-8')
        self.cfg['topics']['guide']['sources'] = [{'path': '../outside.md'}]
        external = self.save_config(self.cwd / 'router.json')
        result = self.run_cli('check', {'AI_CONTEXT_ROOT': str(self.root),
                                        'AI_CONTEXT_CONFIG': str(external)})
        self.assertEqual(result.returncode, 1)
        self.assertIn('../outside.md: outside repo', result.stdout)

    def test_canonical_script_checks_existing_fixture(self):
        fixture = Path(__file__).resolve().parent / 'fixtures' / 'routed'
        result = self.run_cli('check', {'AI_CONTEXT_ROOT': str(fixture)})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('\nok\n', result.stdout)



if __name__ == '__main__':
    unittest.main()
