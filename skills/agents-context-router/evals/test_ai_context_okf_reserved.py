"""OKF reserved wiki pages are exempt from orphan checks only when opted in."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from fixture_helpers import run_router, write_fixture


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/ai-context.py'
sys.dont_write_bytecode = True


class OkfReservedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.script = self.root / 'scripts/ai-context.py'
        self.script.parent.mkdir()
        shutil.copy2(SCRIPT, self.script)
        self.cfg = self.config()
        self.write_root('')
        write_fixture(self.root, 'index.md', '---\nokf_version: 1\n---\n# Bundle\n')

    @staticmethod
    def config():
        return {'topics': {'guide': {'description': 'Guide', 'sources': [
            {'path': 'wiki/guide.md'}]}}}

    def write_root(self, prefix):
        for path, content in [('AGENTS.md', '`guide`\n'), ('wiki/README.md', '# Router\n'),
                              ('wiki/guide.md', '# Guide\n')]:
            write_fixture(self.root, prefix + path, content)

    def check(self):
        write_fixture(self.root, 'wiki/ai-context.json', json.dumps(self.cfg))
        return run_router(self.script, 'check')

    def test_reserved_pages_require_explicit_opt_in(self):
        for name in ('index.md', 'log.md'):
            write_fixture(self.root, 'wiki/' + name, '# Reserved\n')
        for setting in (None, False):
            with self.subTest(setting=setting):
                if setting is None:
                    self.cfg.pop('okfReservedPages', None)
                else:
                    self.cfg['okfReservedPages'] = setting
                result = self.check()
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                for name in ('index.md', 'log.md'):
                    self.assertIn('wiki/' + name + ': wiki page no topic loads', result.stdout)
        self.cfg['okfReservedPages'] = True
        result = self.check()
        self.assertEqual((result.returncode, result.stderr), (0, ''), result.stdout)

    def test_exact_names_at_any_wiki_depth(self):
        self.cfg['okfReservedPages'] = True
        for name in ('area/index.md', 'area/log.md', 'area/other.md', 'Index.md',
                     'index.md.bak', 'index.md.bak.md'):
            write_fixture(self.root, 'wiki/' + name, '# Page\n')
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        for name in ('area/other.md', 'Index.md', 'index.md.bak.md'):
            self.assertIn('wiki/' + name + ': wiki page no topic loads', result.stdout)
        for name in ('area/index.md', 'area/log.md', 'index.md.bak'):
            self.assertNotIn('wiki/' + name + ': wiki page no topic loads', result.stdout)

    def test_history_and_indexed_checks_still_apply(self):
        self.cfg.update(okfReservedPages=True, indexed=['wiki/index.md'])
        write_fixture(self.root, 'wiki/index.md', '# Index\n')
        write_fixture(self.root, 'wiki/history/log.md', '# History\n')
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('wiki/index.md: indexed page not named', result.stdout)
        self.assertIn('wiki/history/log.md: history file not indexed', result.stdout)

    def test_links_in_reserved_pages_are_checked(self):
        self.cfg['okfReservedPages'] = True
        write_fixture(self.root, 'wiki/index.md', '# Index\n[Missing](missing.md)\n')
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("wiki/index.md:2: relative link 'missing.md'", result.stdout)
        self.assertNotIn('wiki/index.md: wiki page no topic loads', result.stdout)

    def test_mounts_use_their_own_setting(self):
        self.write_root('modules/kb/')
        self.cfg['mounts'] = {'kb': {'root': 'modules/kb'}}
        inner = self.config()
        for prefix in ('', 'modules/kb/'):
            write_fixture(self.root, prefix + 'wiki/index.md', '# Index\n')
        for outer, mounted in ((True, False), (False, True), (True, True)):
            with self.subTest(outer=outer, mounted=mounted):
                self.cfg['okfReservedPages'] = outer
                inner['okfReservedPages'] = mounted
                write_fixture(self.root, 'modules/kb/wiki/ai-context.json', json.dumps(inner))
                result = self.check()
                self.assertEqual(result.returncode, 0 if outer and mounted else 1, result.stdout)
                self.assertEqual('FAIL wiki/index.md: wiki page no topic loads' in result.stdout, not outer)
                self.assertEqual('FAIL mount kb: wiki/index.md: wiki page no topic loads' in result.stdout,
                                 not mounted)

    def test_non_boolean_rejected_locally_and_in_mount(self):
        self.cfg['okfReservedPages'] = 'yes'
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('FAIL okfReservedPages: expected a boolean', result.stdout)
        self.cfg['okfReservedPages'] = True
        self.cfg['mounts'] = {'kb': {'root': 'modules/kb'}}
        self.write_root('modules/kb/')
        inner = self.config()
        inner['okfReservedPages'] = 1
        write_fixture(self.root, 'modules/kb/wiki/ai-context.json', json.dumps(inner))
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('FAIL mount kb: okfReservedPages: expected a boolean', result.stdout)


if __name__ == '__main__':
    unittest.main()
