"""Structured router output retains the text commands' checks and status."""
import json
import importlib.util
from unittest.mock import patch
from pathlib import Path
import shutil
import tempfile
import unittest

from fixture_helpers import run_router, write_fixture

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/ai-context.py'


class JsonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.script = self.root / 'scripts/ai-context.py'
        self.script.parent.mkdir()
        shutil.copy2(SCRIPT, self.script)
        self.cfg = {'topics': {'guide': {'sources': [{'path': 'wiki/guide.md'}]}}}
        self.write('AGENTS.md', '`guide`\n')
        self.write('wiki/README.md', '# Router\n')
        self.write('wiki/guide.md', '---\ndescription: A guide\n---\n# Guide\n')
        self.save()

    def write(self, path, text):
        write_fixture(self.root, path, text)

    def save(self):
        self.write('wiki/ai-context.json', json.dumps(self.cfg))

    def run_json(self, command):
        result = run_router(self.script, command, '--json')
        self.assertEqual(result.stderr, '')
        data = json.loads(result.stdout)
        self.assertEqual(result.returncode, run_router(self.script, command).returncode)
        self.assertEqual(data['schemaVersion'], 1)
        self.assertEqual(data['version'], run_router(self.script, '--version').stdout.split()[-1])
        return data

    def test_success_and_list_descriptions(self):
        data = self.run_json('check')
        self.assertTrue(data['ok'])
        self.assertEqual(data['rootInstructions']['bytes'], 8)
        self.assertEqual(data['topics'][0]['sources'], [{'path': 'wiki/guide.md'}])
        self.assertEqual(data['topics'][0]['description'], 'A guide')
        self.assertEqual(self.run_json('list')['topics'], [{'name': 'guide', 'description': 'A guide'}])
        self.cfg['topics']['guide']['description'] = 'Explicit'
        self.save()
        self.assertEqual(self.run_json('list')['topics'][0]['description'], 'Explicit')
        self.assertEqual(run_router(self.script, 'list').stdout, 'guide              Explicit\n')

    def test_text_check_does_not_read_descriptions(self):
        spec = importlib.util.spec_from_file_location('router', SCRIPT)
        router = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(router)
        with patch.object(router, 'topic_description', side_effect=AssertionError('description read')):
            with patch('sys.stdout'):
                self.assertEqual(router.check(self.cfg, root=str(self.root)), 0)

    def test_heading_source(self):
        self.cfg['topics']['guide']['sources'][0]['heading'] = 'Guide'
        self.save()
        topic = self.run_json('check')['topics'][0]
        self.assertEqual(topic['sources'], [{'path': 'wiki/guide.md', 'heading': 'Guide'}])
        self.assertEqual(topic['cap'], 16384)

    def test_routed_fixture(self):
        fixture = Path(__file__).parent / 'fixtures/routed/scripts/ai-context.py'
        result = run_router(fixture, 'check', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data['ok'])
        self.assertEqual([topic['name'] for topic in data['topics']],
                         ['build-deploy', 'debugging', 'ai-context'])
        self.assertEqual(data['mounts'][0]['topics'][0]['name'], 'kb/guide')

    def test_config_validation_errors(self):
        self.cfg['okfReservedPages'] = 'yes'
        self.save()
        for command in ('list', 'check'):
            result = run_router(self.script, command, '--json')
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, '')
            self.assertIn('FAIL okfReservedPages:', result.stderr)

    def test_failures(self):
        self.cfg['budgets'] = {'rootInstructionsMaxBytes': 1}
        self.cfg['topics']['guide']['sources'][0]['heading'] = 'Missing'
        self.write('AGENTS.md', 'no topics\n')
        self.write('wiki/orphan.md', '[bad](missing.md)\n')
        self.write('wiki/history/old.md', '# Old\n')
        self.save()
        data = self.run_json('check')
        self.assertFalse(data['ok'])
        self.assertIsNone(data['topics'][0]['bytes'])
        problems = data['problems']
        self.assertEqual(run_router(self.script, 'check').stdout.splitlines()[-1],
                         f"{len(problems)} problem(s)")
        self.assertTrue({'budget', 'source', 'unlisted', 'orphan', 'link'} <= {p['kind'] for p in problems})
        self.assertEqual([p['kind'] for p in problems], sorted([p['kind'] for p in problems], key={'orphan': 0, 'link': 1, 'budget': 2, 'unlisted': 3, 'source': 4}.get))
        self.assertTrue(any(p.get('topic') == 'guide' and p['kind'] == 'source' for p in problems))
        self.assertTrue(any(p.get('file') == 'wiki/history/old.md' and p['kind'] == 'orphan' for p in problems))
        self.assertTrue(any(p.get('file') == 'wiki/orphan.md' and p.get('line') == 1
                            and p['kind'] == 'link' for p in problems))
        self.assertTrue(any(p['kind'] == 'budget' and p.get('file') == 'AGENTS.md'
                            for p in problems))
        check = run_router(self.script, 'check')
        self.assertEqual((check.stdout, check.stderr, check.returncode), (
            'AGENTS.md              10 B  (cap 1)\n'
            'FAIL wiki/orphan.md: wiki page no topic loads (map it, or list it under "unrouted" with a reason)\n'
            'FAIL wiki/history/old.md: history file not indexed in wiki/README.md\n'
            "FAIL wiki/orphan.md:1: relative link 'missing.md' is not a file inside repo\n"
            'FAIL AGENTS.md 10 B > 1\n'
            'FAIL guide: not listed in AGENTS.md (agents will not know it exists)\n'
            "FAIL guide: wiki/guide.md: heading 'Missing' found 0x\n"
            '6 problem(s)\n', '', 1))
        listing = run_router(self.script, 'list')
        self.assertEqual((listing.stdout, listing.stderr, listing.returncode),
                         ('guide              A guide\n', '', 0))

    def test_missing_root(self):
        (self.root / 'AGENTS.md').unlink()
        data = self.run_json('check')
        self.assertIsNone(data['rootInstructions']['bytes'])
        self.assertTrue(any(p['kind'] == 'root' and p.get('file') == 'AGENTS.md'
                            for p in data['problems']))

    def test_flag_wins_over_topic(self):
        self.cfg['topics']['--json'] = self.cfg['topics']['guide']
        self.save()
        self.assertIn('topics', self.run_json('list'))
        self.assertIn('topics', self.run_json('check'))

    def test_topic_over_budget(self):
        self.cfg['topics']['guide']['maxBytes'] = 1
        self.save()
        data = self.run_json('check')
        topic = data['topics'][0]
        self.assertGreater(topic['bytes'], topic['cap'])
        self.assertTrue(any(p['kind'] == 'budget' and p.get('topic') == 'guide'
                            for p in data['problems']))

    def test_mounts_and_text(self):
        self.cfg['mounts'] = {'kb': {'root': 'modules/kb'}}
        self.save()
        self.assertEqual(len(self.run_json('list')['notices']), 1)
        missing = self.run_json('check')['mounts'][0]
        self.assertEqual((missing['mount'], missing['root']), ('kb', 'modules/kb'))
        self.assertEqual(missing['problems'][0]['kind'], 'mount')
        self.write('modules/kb/AGENTS.md', '`guide`\n')
        self.write('modules/kb/wiki/README.md', '# Router\n')
        self.write('modules/kb/wiki/guide.md', '# Guide\n')
        self.write('modules/kb/wiki/ai-context.json', json.dumps({'topics': {'guide': {'description': 'Inner', 'sources': [{'path': 'wiki/guide.md'}]}}}))
        self.assertEqual(self.run_json('list')['topics'][1]['name'], 'kb/guide')
        mount = self.run_json('check')['mounts'][0]
        self.assertEqual((mount['mount'], mount['root']), ('kb', 'modules/kb'))
        mounted_topic = mount['topics'][0]
        self.assertEqual(mounted_topic['name'], 'kb/guide')
        self.assertEqual(mounted_topic['bytes'], 30)
        self.assertEqual(mounted_topic['cap'], 16384)
        self.write('modules/kb/wiki/ai-context.json', json.dumps({'topics': {'guide': {'maxBytes': 1, 'sources': [{'path': 'wiki/guide.md'}]}}}))
        data = self.run_json('check')
        self.assertEqual(data['problems'], [])
        self.assertTrue(any(p['kind'] == 'budget' and p.get('topic') == 'kb/guide'
                            for p in data['mounts'][0]['problems']))
        self.write('modules/kb/wiki/ai-context.json', json.dumps({'topics': {'guide': {'description': 'Inner', 'sources': [{'path': 'wiki/guide.md'}]}}}))
        self.write('modules/kb/wiki/orphan.md', '# Orphan\n')
        data = self.run_json('check')
        self.assertEqual(data['problems'], [])
        self.assertEqual(data['mounts'][0]['problems'][0]['kind'], 'orphan')
        text = run_router(self.script, 'check').stdout
        self.assertEqual(text, 'AGENTS.md               8 B  (cap 8192)\nguide                  59 B  (cap 16384)\nkb/AGENTS.md            8 B  (cap 8192)\nkb/guide               30 B  (cap 16384)\nFAIL mount kb: wiki/orphan.md: wiki page no topic loads (map it, or list it under "unrouted" with a reason)\n1 root(s) failed\n')
        self.write('modules/kb/wiki/ai-context.json', json.dumps({
            'budgets': {'rootInstructionsMaxBytes': 1},
            'topics': {'guide': {'sources': [{'path': 'wiki/guide.md'}]}}}))
        mount = self.run_json('check')['mounts'][0]
        self.assertTrue(any(p['kind'] == 'budget' and p.get('file') == 'AGENTS.md'
                            for p in mount['problems']))
        (self.root / 'modules/kb/AGENTS.md').unlink()
        mount = self.run_json('check')['mounts'][0]
        self.assertTrue(any(p['kind'] == 'root' and p.get('file') == 'AGENTS.md'
                            for p in mount['problems']))
        self.write('modules/kb/wiki/ai-context.json', '{}')
        self.assertEqual(self.run_json('list')['problems'][0]['kind'], 'mount')


if __name__ == '__main__':
    unittest.main()
