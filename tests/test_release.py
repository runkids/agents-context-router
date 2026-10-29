"""Release metadata and copied-router regressions, using only the standard library."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        config = json.loads((ROOT / 'release-please-config.json').read_text(encoding='utf-8'))
        self.entries = config['packages']['.']['extra-files']
        paths = ['package.json', '.release-please-manifest.json',
                 'release-please-config.json', 'scripts/check-version.py']
        for path in paths + [entry['path'] for entry in self.entries]:
            dest = self.root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, dest)

    def check_versions(self):
        return subprocess.run([sys.executable, str(self.root / 'scripts/check-version.py')],
                              capture_output=True, encoding='utf-8')

    def test_versions_match(self):
        result = self.check_versions()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_drift_in_each_release_target_fails(self):
        version = json.loads((self.root / 'package.json').read_text(encoding='utf-8'))['version']
        for name in ['.release-please-manifest.json'] + [entry['path'] for entry in self.entries]:
            with self.subTest(path=name):
                path = self.root / name
                original = path.read_text(encoding='utf-8')
                path.write_text(original.replace(version, '99.98.97', 1), encoding='utf-8')
                result = self.check_versions()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(name, result.stderr)
                path.write_text(original, encoding='utf-8')

    def test_missing_update_marker_fails(self):
        for entry in self.entries:
            if entry['type'] != 'generic':
                continue
            with self.subTest(path=entry['path']):
                path = self.root / entry['path']
                original = path.read_text(encoding='utf-8')
                path.write_text(original.replace('x-release-please-version', 'removed-marker'), encoding='utf-8')
                result = self.check_versions()
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(entry['path'], result.stderr)
                path.write_text(original, encoding='utf-8')

    def test_copied_router_version_needs_no_config(self):
        version = json.loads((self.root / 'package.json').read_text(encoding='utf-8'))['version']
        env = dict(os.environ, AI_CONTEXT_ROOT=str(self.root),
                   AI_CONTEXT_CONFIG=str(self.root / 'missing.json'))
        for entry in self.entries:
            if not entry['path'].endswith('/ai-context.py'):
                continue
            with self.subTest(path=entry['path']):
                result = subprocess.run([sys.executable, str(self.root / entry['path']), '--version'],
                                        env=env, capture_output=True, encoding='utf-8')
                self.assertEqual((result.returncode, result.stdout, result.stderr),
                                 (0, f'agents-context-router {version}\n', ''))


if __name__ == '__main__':
    unittest.main()
