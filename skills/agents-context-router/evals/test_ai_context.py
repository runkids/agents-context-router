"""CLI regressions using the installed script layout, without external dependencies."""
from contextlib import redirect_stdout
import io
import runpy
from unittest.mock import patch
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / 'scripts/ai-context.py'
PAGE = 'projects/api/deploy-runbook.md'


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
        return subprocess.run([sys.executable, str(self.script), *args],
                              capture_output=True, encoding='utf-8')

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

    def test_indexed_references(self):
        for surface in ['root', 'router', 'topic', 'section', 'source', 'source-section', 'basename', 'relative']:
            with self.subTest(surface=surface):
                self.write('AGENTS.md', '`guide`\n' + (PAGE if surface == 'root' else ''))
                self.cfg['routerFile'] = 'docs/router.md'
                self.write('docs/router.md', PAGE if surface == 'router' else '')
                self.write('wiki/guide.md', '# Guide\n' + (
                    'deploy-runbook.md' if surface == 'basename' else
                    '[Deploy](../api/deploy-runbook.md)' if surface == 'relative' else
                    PAGE if surface in ['topic', 'section'] else 'Use this guide.'))
                sources = [{'path': 'wiki/guide.md'}]
                if surface == 'section':
                    sources[0]['heading'] = 'Guide'
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
                                 ({'projects/*/*.md': 'Human only'}, 1)]:
            with self.subTest(exceptions=exceptions):
                self.cfg['unrouted'] = exceptions
                self.check(code)

    def test_indexed_matching(self):
        self.cfg['indexed'] = ['projects/*', '**/*.md']
        for path in ['projects/api/readme.txt', 'vendor/orphan.md', '.hidden/orphan.md']:
            self.write(path, 'Not indexed.\n')
        output = self.check(1)
        self.assertEqual(output.count('FAIL ' + PAGE + ':'), 1)
        self.assertIn('1 problem(s)', output)
        if os.name == 'posix':
            self.cfg['indexed'] = ['PROJECTS/*.md']
            self.check(0)

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
                                capture_output=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(result.stdout.endswith('ok\n'), result.stdout)
        self.assertEqual(result.stderr, '')


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cwd = Path(self.tmp.name)
        self.root = self.cwd / 'repo'
        self.write('AGENTS.md', '`guide`\n')
        self.write('wiki/guide.md', '# Guide\nRoot content.\n')
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
        anchor = Path(self.root.anchor)
        source = (self.root / 'wiki' / 'guide.md').relative_to(anchor).as_posix()
        self.cfg['topics']['guide']['sources'] = [{'path': source}]
        self.cfg['rootInstructions'] = str(self.root / 'AGENTS.md')
        self.cfg['routerFile'] = str(self.root / 'wiki' / 'README.md')
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
