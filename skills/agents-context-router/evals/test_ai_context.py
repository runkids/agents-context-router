"""CLI regressions: python3 -m unittest discover -s skills/agents-context-router/evals."""
from contextlib import redirect_stdout
import io
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


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'ai-context.py'


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
