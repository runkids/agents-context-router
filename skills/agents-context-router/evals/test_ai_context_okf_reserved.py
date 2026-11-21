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

    def test_reserved_pages_require_opt_in_and_exact_names(self):
        reserved = ('index.md', 'log.md', 'area/index.md', 'area/log.md')
        for name in reserved:
            write_fixture(self.root, 'wiki/' + name, '# Page\n')
        for setting in (None, False, True):
            with self.subTest(setting=setting):
                if setting is None:
                    self.cfg.pop('okfReservedPages', None)
                else:
                    self.cfg['okfReservedPages'] = setting
                result = self.check()
                self.assertEqual(result.returncode, 0 if setting is True else 1, result.stdout)
                for name in reserved:
                    message = 'wiki/' + name + ': wiki page no topic loads'
                    self.assertEqual(message in result.stdout, setting is not True)
        (self.root / 'wiki/index.md').unlink()
        others = ('area/other.md', 'Index.md', 'index.md.bak.md')
        for name in others + ('index.md.bak',):
            write_fixture(self.root, 'wiki/' + name, '# Page\n')
        result = self.check()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        for name in others:
            self.assertIn('wiki/' + name + ': wiki page no topic loads', result.stdout)
        for name in ('area/index.md', 'area/log.md', 'index.md.bak'):
            self.assertNotIn('wiki/' + name + ': wiki page no topic loads', result.stdout)

    def test_history_reserved_pages_and_indexed_check(self):
        self.cfg['indexed'] = ['wiki/index.md']
        for name in ('index.md', 'log.md'):
            write_fixture(self.root, 'wiki/' + name, '# Wiki\n')
            write_fixture(self.root, 'wiki/history/' + name, '# History\n')
            write_fixture(self.root, 'archive/' + name, '# History\n')
        for history, enabled in ((None, False), (None, True), ('archive', True)):
            with self.subTest(history=history, enabled=enabled):
                if history is None:
                    self.cfg.pop('historyDir', None)
                else:
                    self.cfg['historyDir'] = history
                self.cfg['okfReservedPages'] = enabled
                result = self.check()
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn('wiki/index.md: indexed page not named', result.stdout)
                for name in ('index.md', 'log.md'):
                    self.assertEqual('wiki/' + name + ': wiki page no topic loads' in result.stdout,
                                     not enabled)
                    self.assertEqual('wiki/history/' + name + ': history file not indexed' in result.stdout,
                                     history is None and not enabled)
                    self.assertEqual('archive/' + name + ': history file not indexed' in result.stdout,
                                     history == 'archive')

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
