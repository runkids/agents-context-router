"""compactPathLinks prints a link whose text is its own root-relative target as that path."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from fixture_helpers import run_router, write_fixture


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/ai-context.py'
sys.dont_write_bytecode = True
ROW = '| Ship it | [docs/run.md](../docs/run.md) |\n'


class CompactPathLinksTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.script = self.root / 'scripts/ai-context.py'
        self.script.parent.mkdir()
        shutil.copy2(SCRIPT, self.script)
        write_fixture(self.root, 'AGENTS.md', '`guide`\n')
        write_fixture(self.root, 'wiki/README.md', '# Topics\n')
        write_fixture(self.root, 'docs/run.md', 'Run.\n')
        self.cfg = {'topics': {'guide': {'description': 'Guide', 'sources': [
            {'path': 'wiki/guide.md'}]}}}

    def configure(self, value=True, **topic):
        if value is not None:
            self.cfg['compactPathLinks'] = value
        self.cfg['topics']['guide'].update(topic)
        write_fixture(self.root, 'wiki/ai-context.json', json.dumps(self.cfg))

    def guide(self, text, *args):
        write_fixture(self.root, 'wiki/guide.md', text)
        return run_router(self.script, *(args or ('guide',)))

    def assertOut(self, result, expected):
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        self.assertEqual(result.stdout, '<!-- wiki/guide.md -->\n' + expected)

    def test_default_and_false_print_the_page_unchanged(self):
        for value in (None, False):
            with self.subTest(value=value):
                self.cfg.pop('compactPathLinks', None)
                self.configure(value)
                self.assertOut(self.guide(ROW), ROW)

    def test_self_link_prints_its_path_once(self):
        self.configure()
        self.assertOut(self.guide(ROW + '- [docs/run.md](../docs/run.md) and [docs](../docs).\n'
                                  '[./docs/run.md](../docs/run.md) [docs//run.md](../docs/run.md)\n'),
                       '| Ship it | `docs/run.md` |\n- `docs/run.md` and `docs`.\n'
                       '`docs/run.md` `docs/run.md`\n')

    def test_other_links_are_kept_byte_for_byte(self):
        self.configure()
        kept = ('[run](../docs/run.md)\n'                     # text is not the path
                '[docs/run.md](run.md)\n'                     # text names another file
                '[docs/run.md](../docs/run.md#step)\n'        # fragment
                '[docs/run.md](../docs/run.md "Title")\n'     # title
                '![docs/run.md](../docs/run.md)\n'            # image
                '\\[docs/run.md](../docs/run.md)\n'           # escaped, not a link
                '[docs/run.md][ref]\n\n[ref]: ../docs/run.md\n'  # reference link
                '![outer [docs/run.md](../docs/run.md)](image.png)\n'
                '[https://x.dev/a](https://x.dev/a)\n'        # URL
                '[/docs/run.md](/docs/run.md)\n'              # absolute
                '[docs/my run.md](../docs/my%20run.md)\n'     # not a plain path
                '```\n[docs/run.md](../docs/run.md)\n```\n'   # fenced code
                '    [docs/run.md](../docs/run.md)\n')        # indented code
        self.assertOut(self.guide(kept), kept)

    def test_code_and_titled_links_do_not_interfere_with_neighbors(self):
        self.configure()
        line = ('`[docs/run.md](../docs/run.md)` and [docs/run.md](../docs/run.md)\n'
                '`[docs/run.md](../docs/run.md)` and [run](../docs/run.md "Run").\n')
        expected = ('`[docs/run.md](../docs/run.md)` and `docs/run.md`\n'
                    '`[docs/run.md](../docs/run.md)` and [run](../docs/run.md "Run").\n')
        self.assertOut(self.guide(line), expected)

    def test_adjacent_existing_code_remains_separate(self):
        self.configure()
        link = '[docs/run.md](../docs/run.md)'
        code = '`docs/run.md`'
        sep = '<!-- -->'
        self.assertOut(self.guide(f'`before`{link}\n{link}`after`\n'
                                  f'`before`{link}{link}`after`\n'),
                       f'`before`{sep}{code}\n{code}{sep}`after`\n'
                       f'`before`{sep}{code}{sep}{code}{sep}`after`\n')
        self.assertOut(self.guide(f'{link}{link}\n'), f'{code}{sep}{code}\n')

    def test_container_prefixes_preserve_token_offsets(self):
        self.configure()
        line = ('> [docs/run.md](../docs/run.md)\n'
                '- item\n  > [docs/run.md](../docs/run.md)\n'
                '>\t[docs/run.md](../docs/run.md)\n')
        expected = ('> `docs/run.md`\n'
                    '- item\n  > `docs/run.md`\n'
                    '>\t`docs/run.md`\n')
        self.assertOut(self.guide(line), expected)

    def test_absolute_source_compacts(self):
        self.cfg['topics']['guide']['sources'][0]['path'] = str(Path(self.tmp.name) / 'wiki/guide.md')
        self.configure()
        result = self.guide(ROW)
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        self.assertEqual(result.stdout, '<!-- ' + str(Path(self.tmp.name) / 'wiki/guide.md') +
                         ' -->\n| Ship it | `docs/run.md` |\n')

    def test_heading_source_resolves_from_its_file(self):
        write_fixture(self.root, 'wiki/deep/run.md', 'Deep.\n')
        self.cfg['topics']['guide']['sources'] = [{'path': 'wiki/deep/page.md', 'heading': 'Read'}]
        self.configure()
        write_fixture(self.root, 'wiki/deep/page.md',
                      '# Page\n## Read\n[wiki/deep/run.md](run.md) [docs/run.md](../../docs/run.md)\n## Other\n')
        result = run_router(self.script, 'guide')
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        self.assertEqual(result.stdout,
                         '<!-- wiki/deep/page.md § Read -->\n## Read\n`wiki/deep/run.md` `docs/run.md`\n')

    def test_check_budgets_compact_output_and_still_validates_targets(self):
        printed = len(('<!-- wiki/guide.md -->\n' + '| Ship it | `docs/run.md` |').encode())
        self.configure(maxBytes=printed)
        result = self.guide(ROW, 'check')
        self.assertEqual((result.returncode, result.stderr), (0, ''), result.stdout)
        self.configure(False)
        self.assertEqual(run_router(self.script, 'check').returncode, 1)
        # A moved leaf still fails check with the option on.
        self.configure(True)
        (self.root / 'docs/run.md').rename(self.root / 'docs/moved.md')
        result = run_router(self.script, 'check')
        self.assertEqual(result.returncode, 1)
        self.assertIn("relative link '../docs/run.md' is not a file inside repo", result.stdout)

    def test_mounted_paths_with_backticks_form_valid_code_spans(self):
        cases = (
            ('modules/a`b', '[docs/run.md](../docs/run.md)', '``modules/a`b/docs/run.md``'),
            ('modules/a``b`c', '[docs/run.md](../docs/run.md)', '```modules/a``b`c/docs/run.md```'),
            ('`edge`', '[.](..)', '`` `edge` ``'),
        )
        for mount, link, expected in cases:
            with self.subTest(mount=mount):
                inner = self.root / mount
                write_fixture(inner, 'AGENTS.md', '`guide`\n')
                write_fixture(inner, 'wiki/README.md', '# Topics\n')
                write_fixture(inner, 'docs/run.md', 'Run.\n')
                write_fixture(inner, 'wiki/guide.md', f'{link}\n')
                write_fixture(inner, 'wiki/ai-context.json', json.dumps({
                    'compactPathLinks': True, 'topics': {'guide': {'description': 'Inner',
                        'sources': [{'path': 'wiki/guide.md'}]}}}))
                self.cfg['mounts'] = {'kb': {'root': mount}}
                self.configure(None)
                result = run_router(self.script, 'kb/guide')
                self.assertEqual((result.returncode, result.stderr), (0, ''))
                self.assertEqual(result.stdout, f'<!-- {mount}/wiki/guide.md -->\n'
                                 f'{expected}\n')

    def test_mounted_config_uses_its_own_setting(self):
        inner = self.root / 'modules/kb'
        write_fixture(inner, 'AGENTS.md', '`guide`\n')
        write_fixture(inner, 'wiki/README.md', '# Topics\n')
        write_fixture(inner, 'docs/run.md', 'Inner run.\n')
        write_fixture(inner, 'wiki/guide.md', '# Guide\n' + ROW.replace('[docs/', '[./docs/') + '# Other\n')
        native = '<!-- wiki/guide.md § Guide -->\n# Guide\n| Ship it | `docs/run.md` |'
        write_fixture(inner, 'wiki/ai-context.json', json.dumps({
            'compactPathLinks': True, 'topics': {'guide': {'description': 'Inner',
                'maxBytes': len(native.encode()), 'sources': [
                    {'path': 'wiki/guide.md', 'heading': 'Guide'}]}}}))
        self.cfg['mounts'] = {'kb': {'root': 'modules/kb'}}
        self.configure(None)
        result = self.guide(ROW, 'guide', 'kb/guide')
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        self.assertEqual(result.stdout, '<!-- wiki/guide.md -->\n' + ROW.strip() + '\n\n'
                         '<!-- modules/kb/wiki/guide.md § Guide -->\n# Guide\n'
                         '| Ship it | `modules/kb/docs/run.md` |\n')
        self.configure(True)
        result = self.guide(ROW, 'guide', 'kb/guide')
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        self.assertEqual(result.stdout, '<!-- wiki/guide.md -->\n| Ship it | `docs/run.md` |\n\n'
                         '<!-- modules/kb/wiki/guide.md § Guide -->\n# Guide\n'
                         '| Ship it | `modules/kb/docs/run.md` |\n')
        inner_script = inner / 'scripts/ai-context.py'
        inner_script.parent.mkdir()
        shutil.copy2(SCRIPT, inner_script)
        native_result = run_router(inner_script, 'guide')
        self.assertEqual((native_result.returncode, native_result.stdout, native_result.stderr),
                         (0, native + '\n', ''))
        self.assertEqual(run_router(self.script, 'check').returncode, 0)

    def test_option_must_be_a_boolean(self):
        self.configure('yes')
        write_fixture(self.root, 'wiki/guide.md', ROW)
        result = run_router(self.script, 'check')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, 'FAIL compactPathLinks: expected a boolean\n')
        self.cfg['mounts'] = {'kb': {'root': 'modules/kb'}}
        write_fixture(self.root, 'modules/kb/AGENTS.md', '`guide`\n')
        write_fixture(self.root, 'modules/kb/wiki/ai-context.json', json.dumps(
            {'compactPathLinks': 1, 'topics': {'guide': {'description': 'Inner', 'sources': []}}}))
        self.configure(True)
        result = run_router(self.script, 'kb/guide')
        self.assertEqual(result.returncode, 1)
        self.assertIn('compactPathLinks: expected a boolean', result.stderr)


if __name__ == '__main__':
    unittest.main()
