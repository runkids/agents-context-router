"""Mounted roots: independent namespaces, guarded reads and atomic requests."""
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / 'scripts/ai-context.py'
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('mounted_ai_context', SCRIPT)
router = importlib.util.module_from_spec(spec)
spec.loader.exec_module(router)


class MountFixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.parent = Path(temporary.name)
        self.root = self.parent / 'project'
        self.module_root = self.root / 'modules/kb-core'
        self.cfg = self.config('Project guide')
        self.cfg['mounts'] = {'kb': {'root': 'modules/kb-core'}}
        self.inner_cfg = self.config('Module guide')
        for prefix, body in [('', 'Local.'), ('modules/kb-core/', 'Module.')]:
            self.write(prefix + 'AGENTS.md', '`guide`\n')
            self.write(prefix + 'wiki/README.md', '# Router\n')
            self.write(prefix + 'wiki/guide.md', '# Guide\n' + body + '\n')
        self.save_configs()

    @staticmethod
    def config(description):
        return {'topics': {'guide': {'description': description,
                                    'sources': [{'path': 'wiki/guide.md'}]}}}

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def save_configs(self):
        self.write('wiki/ai-context.json', json.dumps(self.cfg, ensure_ascii=False))
        self.write(str(self.module_root / 'wiki/ai-context.json'),
                   json.dumps(self.inner_cfg, ensure_ascii=False))

    def cli(self, *args, root=None, config=None, cwd=None):
        env = {key: value for key, value in os.environ.items()
               if key not in ('AI_CONTEXT_ROOT', 'AI_CONTEXT_CONFIG')}
        env['AI_CONTEXT_ROOT'] = str(self.root if root is None else root)
        env['AI_CONTEXT_CONFIG'] = str(self.root / 'wiki/ai-context.json'
                                       if config is None else config)
        return subprocess.run([sys.executable, str(SCRIPT), *args], env=env,
                              cwd=cwd, capture_output=True, encoding='utf-8')

    def call_main(self, *args):
        # Real main with reconfigurable streams; injected I/O faults cannot
        # cross a subprocess boundary. Preserve globals and parent streams.
        output, errors = io.BytesIO(), io.BytesIO()
        stdout = io.TextIOWrapper(output, encoding='utf-8')
        stderr = io.TextIOWrapper(errors, encoding='utf-8')
        try:
            with patch.object(router, 'ROOT', str(self.root)), \
                    patch.object(router, 'CFG_PATH', str(self.root / 'wiki/ai-context.json')), \
                    patch.object(sys, 'stdout', stdout), patch.object(sys, 'stderr', stderr):
                try:
                    code = router.main(['ai-context.py', *args])
                except SystemExit as error:
                    code = error.code if isinstance(error.code, int) else 1
                    if not isinstance(error.code, int):
                        print(error.code, file=stderr)
            stdout.flush()
            stderr.flush()
            return code, output.getvalue().decode('utf-8'), errors.getvalue().decode('utf-8')
        finally:
            stdout.close()
            stderr.close()

    def sibling(self):
        self.cfg['mounts']['other'] = {'root': 'modules/other'}
        for path, text in [('AGENTS.md', '`guide`\n'), ('wiki/README.md', '# Router\n'),
                           ('wiki/guide.md', '# Guide\nOther.\n'),
                           ('wiki/ai-context.json', json.dumps(self.config('Other guide')))]:
            self.write('modules/other/' + path, text)
        self.save_configs()

    def symlink(self, path, target, directory=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.symlink_to(target, target_is_directory=directory)
        except (OSError, NotImplementedError) as error:
            self.skipTest('symlink capability unavailable: ' + str(error))

    def assert_failure(self, result, *details):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        for detail in details:
            self.assertIn(detail, result.stdout + result.stderr)


class MountRoutingTests(MountFixture):
    def test_list_and_mixed_render(self):
        # Dropping mounts or using the outer cfg/body must fail these literals.
        local = '<!-- wiki/guide.md -->\n# Guide\nLocal.'
        mounted = '<!-- modules/kb-core/wiki/guide.md -->\n# Guide\nModule.'
        rows = self.cli('list')
        self.assertEqual((rows.returncode, rows.stderr), (0, ''))
        self.assertEqual(rows.stdout.splitlines(), [f'{"guide":18} Project guide',
                         f'{"kb/guide":18} Module guide [modules/kb-core]'])
        for names, bodies in [(('guide',), [local]), (('kb/guide',), [mounted]),
                              (('guide', 'kb/guide'), [local, mounted]),
                              (('kb/guide', 'guide', 'kb/guide'), [mounted, local, mounted])]:
            with self.subTest(names=names):
                result = self.cli(*names)
                self.assertEqual((result.returncode, result.stderr), (0, ''))
                self.assertEqual(result.stdout, '\n\n'.join(bodies) + '\n')
        self.inner_cfg['topics']['指南'] = {'description': '操作說明', 'sources': [
            {'path': 'wiki/中文.md', 'heading': '選擇'}]}
        self.write('modules/kb-core/wiki/中文.md', '# 首頁\n## 選擇\n內容。\n## 其他\n省略。\n')
        self.cfg['mounts']['知識'] = self.cfg['mounts']['kb']
        self.save_configs()
        result = self.cli('知識/指南')
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        self.assertEqual(result.stdout, '<!-- modules/kb-core/wiki/中文.md § 選擇 -->\n## 選擇\n內容。\n')
        self.assertIn(f'{"知識/指南":18} 操作說明 [modules/kb-core]', self.cli('list').stdout)

    def test_namespace_dispatch(self):
        self.cfg['topics']['kb'] = copy.deepcopy(self.cfg['topics']['guide'])
        self.inner_cfg['topics']['ops/guide'] = copy.deepcopy(self.inner_cfg['topics']['guide'])
        self.cfg['mounts']['list'] = {'root': 'modules/kb-core'}
        self.cfg['mounts']['check'] = {'root': 'modules/kb-core'}
        self.save_configs()
        for name, body in [('kb', 'Local.'), ('kb/ops/guide', 'Module.'),
                           ('list/guide', 'Module.'), ('check/guide', 'Module.')]:
            with self.subTest(name=name):
                result = self.cli(name)
                self.assertEqual((result.returncode, result.stderr), (0, ''))
                self.assertIn(body, result.stdout)
        for name in ['absent', 'kb/absent']:
            result = self.cli(name)
            self.assertEqual((result.returncode, result.stdout), (1, ''))
            self.assertIn(f'unknown topic {name!r}; rerun this script with list', result.stderr)

    def test_paths_and_overrides(self):
        external = self.parent / 'outer.json'
        nested = self.root / 'one/two/three'
        nested.mkdir(parents=True)
        for root_path, config_path, source in [
                ('modules/kb-core', None, 'wiki/guide.md'),
                (str(self.module_root), str(self.module_root / 'wiki/ai-context.json'),
                 str(self.module_root / 'wiki/guide.md')),
                ('modules\\kb-core', 'context\\router.json', 'wiki\\guide.md')]:
            with self.subTest(root=root_path, config=config_path):
                self.cfg['mounts']['kb'] = {'root': root_path}
                if config_path is not None:
                    self.cfg['mounts']['kb']['config'] = config_path
                self.inner_cfg['topics']['guide']['sources'][0]['path'] = source
                self.save_configs()
                if config_path == 'context\\router.json':
                    self.write('modules/kb-core/context/router.json', json.dumps(self.inner_cfg))
                external.write_text(json.dumps(self.cfg), encoding='utf-8')
                for cwd in [self.root, nested]:
                    for outer_config in [self.root / 'wiki/ai-context.json', external]:
                        result = self.cli('kb/guide', config=outer_config, cwd=cwd)
                        self.assertEqual((result.returncode, result.stderr), (0, ''))
                        self.assertEqual(result.stdout, '<!-- modules/kb-core/wiki/guide.md -->\n# Guide\nModule.\n')
                result = self.cli('kb/guide', root='../../..',
                                  config=os.path.relpath(external, nested), cwd=nested)
                self.assertEqual((result.returncode, result.stderr), (0, ''))
                self.assertIn('Module.', result.stdout)
        # The copied executable's default root stays independent of cwd.
        self.cfg['mounts']['kb'] = {'root': 'modules/kb-core'}
        self.inner_cfg['topics']['guide']['sources'][0]['path'] = 'wiki/guide.md'
        self.save_configs()
        script = self.root / 'scripts/ai-context.py'
        script.parent.mkdir()
        shutil.copyfile(SCRIPT, script)
        env = {k: v for k, v in os.environ.items() if k not in ('AI_CONTEXT_ROOT', 'AI_CONTEXT_CONFIG')}
        result = subprocess.run([sys.executable, str(script), 'kb/guide'], cwd=nested,
                                env=env, capture_output=True, encoding='utf-8')
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        self.assertIn('Module.', result.stdout)
        for literal in ['~', '$MOUNT_ROOT']:
            target = self.root / literal
            shutil.copytree(self.module_root, target)
            self.cfg['mounts']['kb'] = {'root': literal}
            self.save_configs()
            result = self.cli('kb/guide')
            self.assertEqual((result.returncode, result.stderr), (0, ''))
            self.assertIn(f'<!-- {literal}/wiki/guide.md -->', result.stdout)

    def test_explicit_root_keeps_globals(self):
        original = router.ROOT, router.CFG_PATH
        for owner, cfg, expected in [(self.root, self.cfg, 'Local.'),
                                      (self.module_root, self.inner_cfg, 'Module.'),
                                      (self.root, self.cfg, 'Local.')]:
            self.assertEqual(router.section({'path': 'wiki/guide.md'}, root=str(owner)),
                             '# Guide\n' + expected)
            self.assertEqual(router.render(cfg, 'guide', root=str(owner)),
                             '<!-- wiki/guide.md -->\n# Guide\n' + expected)
            self.assertEqual((router.ROOT, router.CFG_PATH), original)
        with patch.object(router, 'ROOT', str(self.root)):
            self.assertEqual(router.section({'path': 'wiki/guide.md'}), '# Guide\nLocal.')

    def test_failure_matrix(self):
        missing = self.root / 'modules/missing'
        self.cfg['mounts']['kb']['root'] = str(missing)
        self.save_configs()
        result = self.cli('list')
        self.assertEqual((result.returncode, result.stderr), (0, ''))
        self.assertEqual(result.stdout, f'{"guide":18} Project guide\nNOTICE mount kb: missing root {missing}\n')
        self.assertEqual(self.cli('guide').stderr, '')
        self.assertEqual((self.cli('kb/guide').returncode, self.cli('kb/guide').stdout), (1, ''))
        for control in ['\n', '\r', '\x85']:
            self.cfg['mounts']['kb']['root'] = 'missing' + control + 'root'
            self.save_configs()
            result = self.cli('list')
            self.assertEqual(result.returncode, 0)
            self.assertEqual(len(result.stdout.splitlines()), 2)
            self.assertIn('NOTICE mount kb: missing root ', result.stdout)
        self.cfg['mounts']['kb']['root'] = 'modules/kb-core'
        self.sibling()
        config_path = self.module_root / 'wiki/ai-context.json'
        for content, category in [(b'{', 'JSON'), (b'\xff', 'UTF-8'),
                                   (b'{"topics": {}, "mounts": {"nested": {"root": "no"}}}', 'nested')]:
            with self.subTest(category=category):
                config_path.write_bytes(content)
                self.assert_failure(self.cli('list'), 'mount kb:', category)
                self.assertIn('other/guide', self.cli('list').stdout)
                self.assertEqual(self.cli('guide').stderr, '')
                self.assertEqual(self.cli('other/guide').stderr, '')
        self.save_configs()
        config_path.unlink()
        self.assert_failure(self.cli('list'), 'mount kb:', 'config', str(config_path))
        config_path.mkdir()
        self.assert_failure(self.cli('list'), 'mount kb:', 'config')
        config_path.rmdir()
        self.save_configs()
        root_file = self.write('modules/file', 'not a directory')
        self.cfg['mounts']['kb']['root'] = str(root_file)
        self.save_configs()
        self.assert_failure(self.cli('list'), 'mount kb:', 'root', 'directory')
        self.cfg['mounts']['kb']['root'] = 'modules/kb-core'
        self.save_configs()
        real_stat, real_open = os.stat, open
        def denied_stat(path, *args, **kwargs):
            if os.path.abspath(path) == str(self.module_root):
                raise PermissionError('denied root')
            return real_stat(path, *args, **kwargs)
        with patch.object(router.os, 'stat', side_effect=denied_stat):
            code, out, err = self.call_main('list')
        self.assertEqual(code, 1, out + err)
        self.assertIn('mount kb:', err)
        self.assertIn('denied root', err)
        self.assertNotIn('NOTICE', out)
        def denied_open(path, *args, **kwargs):
            if os.path.abspath(path) == str(config_path):
                raise PermissionError('denied config')
            return real_open(path, *args, **kwargs)
        with patch('builtins.open', side_effect=denied_open):
            code, out, err = self.call_main('list')
        self.assertEqual(code, 1, out + err)
        self.assertIn('mount kb:', err)
        self.assertIn('denied config', err)
        self.assertIn('other/guide', out)

    def test_combined_render_is_atomic(self):
        original = copy.deepcopy(self.inner_cfg)
        for kind in ['unknown', 'inner-unknown', 'missing-mount', 'missing-source',
                     'bad-utf8', 'missing-heading', 'duplicate-heading', 'denied-source']:
            with self.subTest(kind=kind):
                self.inner_cfg = copy.deepcopy(original)
                self.cfg['mounts']['kb']['root'] = 'modules/kb-core'
                source = self.write('modules/kb-core/wiki/guide.md', '# Guide\nModule.\n')
                name = 'kb/guide'
                if kind == 'unknown':
                    name = 'unknown'
                elif kind == 'inner-unknown':
                    name = 'kb/unknown'
                elif kind == 'missing-mount':
                    self.cfg['mounts']['kb']['root'] = 'modules/missing'
                elif kind == 'missing-source':
                    source.unlink()
                elif kind == 'bad-utf8':
                    source.write_bytes(b'\xff')
                elif kind in ('missing-heading', 'duplicate-heading'):
                    self.inner_cfg['topics']['guide']['sources'][0]['heading'] = 'Selected'
                    if kind == 'duplicate-heading':
                        source.write_text('# Selected\nOne\n# Selected\nTwo\n', encoding='utf-8')
                self.save_configs()
                real_open = open
                def selected_open(path, *args, **kwargs):
                    if kind == 'denied-source' and os.path.abspath(path) == str(source):
                        raise PermissionError('denied source')
                    return real_open(path, *args, **kwargs)
                for requests in [('guide', name), (name, 'guide')]:
                    with patch('builtins.open', side_effect=selected_open):
                        code, out, err = self.call_main(*requests)
                    self.assertEqual((code, out), (1, ''), err)
                    self.assertIn(name, err)
                    self.assertNotIn('Traceback', err)


class MountDeclarationTests(MountFixture):
    def test_fields_and_namespace(self):
        for value in [None, [], 'kb', 7]:
            with self.subTest(mounts=value):
                self.cfg['mounts'] = value
                self.save_configs()
                for args in [('list',), ('guide',), ('check',)]:
                    result = self.cli(*args)
                    self.assert_failure(result, 'mounts')
                    if args == ('guide',):
                        self.assertEqual(result.stdout, '')
        cases = [(None, 'declaration'), ([], 'declaration'), ('root', 'declaration'),
                 ({}, 'root'), ({'root': ''}, 'root'), ({'root': 1}, 'root'),
                 ({'root': None}, 'root'), ({'root': 'bad\x00path'}, 'root'),
                 ({'root': 'modules/kb-core', 'config': ''}, 'config'),
                 ({'root': 'modules/kb-core', 'config': 1}, 'config'),
                 ({'root': 'modules/kb-core', 'config': None}, 'config'),
                 ({'root': 'modules/kb-core', 'config': 'bad\x00path'}, 'config'),
                 ({'root': 'modules/kb-core', 'typo': True}, 'typo')]
        for declaration, field in cases:
            with self.subTest(declaration=declaration):
                self.cfg['mounts'] = {'kb': declaration}
                self.sibling()
                result = self.cli('list')
                self.assert_failure(result, 'mount kb:', field)
                self.assertIn('other/guide', result.stdout)
                self.assertEqual(self.cli('guide').returncode, 0)
                self.assertEqual((self.cli('kb/guide').returncode, self.cli('kb/guide').stdout), (1, ''))
        for name in ['', '.', '..', 'a/b', 'a\\b', 'a b', 'a\u3000b', 'a\n', 'a\x00', 'a\x7f', 'a\x85']:
            with self.subTest(name=repr(name)):
                self.cfg['mounts'] = {name: {'root': 'modules/kb-core'}}
                self.sibling()
                result = self.cli('list')
                self.assert_failure(result, 'name')
                self.assertIn('other/guide', result.stdout)
        for name in ['kb-core', '知識']:
            self.cfg['mounts'] = {name: {'root': 'modules/kb-core'}}
            self.save_configs()
            self.assertEqual(self.cli(name + '/guide').returncode, 0)
        self.cfg['topics']['kb/guide'] = copy.deepcopy(self.cfg['topics']['guide'])
        for root in ['modules/kb-core', 'modules/missing']:
            self.cfg['mounts'] = {'kb': {'root': root}}
            self.save_configs()
            result = self.cli('list')
            self.assert_failure(result, 'mount kb:', 'collision')
            self.assertNotIn(f'{"kb/guide":18} Project guide', result.stdout)
            failed = self.cli('kb/guide')
            self.assertEqual((failed.returncode, failed.stdout), (1, ''))
            self.assertEqual(self.cli('guide').returncode, 0)
        for mounts in [None, {}]:
            if mounts is None:
                self.cfg.pop('mounts', None)
            else:
                self.cfg['mounts'] = mounts
            self.save_configs()
            self.assertIn('Local.', self.cli('kb/guide').stdout)

    def test_mounted_schema(self):
        original = copy.deepcopy(self.inner_cfg)
        self.sibling()
        # Every consumed field must fail at the loader, before a traceback or
        # partial list can hide a healthy later root.
        cases = [(None, 'config'), ([], 'config'), ({}, 'topics'),
                 ({'topics': []}, 'topics'), ({'topics': {'': {}}}, 'topics')]
        for field, value in [('description', 1), ('sources', {}), ('sources', [None]),
                             ('sources', [{'path': ''}]), ('sources', [{'path': 1}]),
                             ('sources', [{}]), ('sources', [{'path': 'wiki/guide.md', 'heading': 1}])]:
            cfg = copy.deepcopy(original)
            cfg['topics']['guide'][field] = value
            cases.append((cfg, field if field == 'description' else 'sources'))
        cfg = copy.deepcopy(original)
        cfg['topics']['guide'] = []
        cases.append((cfg, 'guide'))
        for key, value in [('budgets', []), ('indexed', 'wiki/*'), ('indexed', [1]),
                           ('skipDirs', {}), ('skipDirs', [1]), ('unrouted', []),
                           ('mounts', None), ('mounts', []),
                           ('mounts', {'inner': {'root': '/must-not-follow'}})]:
            cfg = copy.deepcopy(original)
            cfg[key] = value
            cases.append((cfg, 'nested' if key == 'mounts' and isinstance(value, dict) else key))
        for key in ['rootInstructions', 'wikiDir', 'historyDir', 'routerFile']:
            for value in ['', 1, None, 'bad\x00path']:
                cfg = copy.deepcopy(original)
                cfg[key] = value
                cases.append((cfg, key))
        for value in [-1, True, '10']:
            for key in ['rootInstructionsMaxBytes', 'defaultTopicMaxBytes']:
                cfg = copy.deepcopy(original)
                cfg['budgets'] = {key: value}
                cases.append((cfg, key))
            cfg = copy.deepcopy(original)
            cfg['topics']['guide']['maxBytes'] = value
            cases.append((cfg, 'maxBytes'))
        config_path = self.module_root / 'wiki/ai-context.json'
        for cfg, field in cases:
            with self.subTest(field=field, cfg=cfg):
                config_path.write_text(json.dumps(cfg), encoding='utf-8')
                result = self.cli('list')
                self.assert_failure(result, 'mount kb:', field)
                self.assertIn('other/guide', result.stdout)
                self.assertEqual(self.cli('guide').returncode, 0)
        for cfg in [{'topics': {}}, {'topics': {'empty': {'description': '', 'sources': []}}},
                    dict(original, budgets={'rootInstructionsMaxBytes': 0, 'defaultTopicMaxBytes': 0},
                         unrouted={'anything': None}, mounts={}, future={'accepted': True})]:
            config_path.write_text(json.dumps(cfg), encoding='utf-8')
            result = self.cli('list')
            self.assertEqual((result.returncode, result.stderr), (0, ''))


class MountBoundaryTests(MountFixture):
    def test_root_and_config_boundaries(self):
        outside = self.parent / 'outside'
        outside.mkdir()
        (outside / 'secret.json').write_text('{"topics": {}}', encoding='utf-8')
        sibling = self.parent / 'project-neighbor'
        sibling.mkdir()
        real_open, real_scan = open, os.scandir
        forbidden = []
        def guarded_root_open(candidate, *args, **kwargs):
            canonical = os.path.realpath(candidate)
            if canonical == str(outside) or canonical.startswith(str(outside) + os.sep):
                forbidden.append(canonical)
                raise AssertionError('outside root opened')
            return real_open(candidate, *args, **kwargs)
        def guarded_root_scan(candidate):
            canonical = os.path.realpath(candidate)
            if canonical == str(outside) or canonical.startswith(str(outside) + os.sep):
                forbidden.append(canonical)
                raise AssertionError('outside root scanned')
            return real_scan(candidate)
        for path in ['.', str(self.root), '../outside', str(outside), str(sibling), '../absent']:
            with self.subTest(root=path):
                self.cfg['mounts']['kb'] = {'root': path}
                self.save_configs()
                result = self.cli('list')
                self.assert_failure(result, 'mount kb:', 'root')
                self.assertNotIn('NOTICE', result.stdout)
                with patch('builtins.open', side_effect=guarded_root_open), \
                        patch.object(router.os, 'scandir', side_effect=guarded_root_scan):
                    code, out, err = self.call_main('list')
                self.assertEqual(code, 1, out + err)
                self.assertIn('mount kb:', err)
                self.assertEqual(forbidden, [])
        self.cfg['mounts']['kb'] = {'root': 'modules/kb-core'}
        for path in ['../../wiki/ai-context.json', str(outside / 'secret.json'),
                     str(self.root / 'wiki/ai-context.json')]:
            with self.subTest(config=path):
                self.cfg['mounts']['kb']['config'] = path
                self.save_configs()
                real_open, real_scan = open, os.scandir
                forbidden = []
                def guarded_open(candidate, *args, **kwargs):
                    canonical = os.path.realpath(candidate)
                    if canonical == str(outside / 'secret.json'):
                        forbidden.append(canonical)
                        raise AssertionError('outside config opened')
                    return real_open(candidate, *args, **kwargs)
                def guarded_scan(candidate):
                    if os.path.realpath(candidate) == str(outside):
                        forbidden.append(str(candidate))
                        raise AssertionError('outside directory scanned')
                    return real_scan(candidate)
                with patch('builtins.open', side_effect=guarded_open), \
                        patch.object(router.os, 'scandir', side_effect=guarded_scan):
                    code, out, err = self.call_main('list')
                self.assertEqual(code, 1, out + err)
                self.assertIn('mount kb:', err)
                self.assertIn('config', err)
                self.assertEqual(forbidden, [])
        self.cfg['mounts']['kb'] = {'root': 'modules/kb-core'}
        aliases = [('modules/back', self.root), ('modules/escape', outside),
                   ('modules/dangling-outside', outside / 'missing'),
                   ('modules/dangling-inside', self.root / 'missing'),
                   ('modules/alias', self.module_root)]
        for name, target in aliases:
            self.symlink(self.root / name, target, directory=True)
            self.cfg['mounts']['kb'] = {'root': name}
            self.save_configs()
            result = self.cli('list')
            if name.endswith('dangling-inside'):
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('NOTICE mount kb: missing root ', result.stdout)
            elif name.endswith('/alias'):
                self.assertEqual((result.returncode, result.stderr), (0, ''))
                self.assertIn('kb/guide', result.stdout)
            else:
                self.assert_failure(result, 'mount kb:', 'root')
                self.assertNotIn('NOTICE', result.stdout)
        self.cfg['mounts'] = {'kb': {'root': 'modules/kb-core'},
                              'same': {'root': 'modules/alias'}}
        self.save_configs()
        self.assertEqual(self.cli('same/guide').returncode, 0)
        config_alias = self.module_root / 'context.json'
        self.symlink(config_alias, self.module_root / 'wiki/ai-context.json')
        self.cfg['mounts']['kb']['config'] = 'context.json'
        self.save_configs()
        self.assertEqual(self.cli('kb/guide').returncode, 0)
        config_alias.unlink()
        self.symlink(config_alias, outside / 'secret.json')
        self.assert_failure(self.cli('list'), 'mount kb:', 'config')
        # Ancestor symlinks must not make a textually contained root safe.
        self.cfg['mounts']['kb'] = {'root': 'modules/escape/child'}
        self.save_configs()
        self.assert_failure(self.cli('list'), 'mount kb:', 'root')

    def test_physical_comparison_and_config_recheck(self):
        # No filesystem anchor is ever walked by this helper-only assertion.
        anchor = Path(self.root.anchor)
        self.assertTrue(router.inside_root(str(self.root), str(anchor)))
        self.assertFalse(router.inside_root(str(anchor), str(anchor)))
        self.assertTrue(router.inside_root(str(anchor), str(anchor), allow_root=True))
        self.assertFalse(router.inside_root(str(self.parent / 'project-sibling'), str(self.root)))
        if os.name == 'nt':
            self.assertFalse(router.inside_root('Z:\\outside', 'C:\\owner'))
        entry = router.mount_entries(self.cfg, root=str(self.root))[0]
        outside = self.parent / 'changed.json'
        outside.write_text('{"topics": {}}', encoding='utf-8')
        config = self.module_root / 'wiki/ai-context.json'
        config.unlink()
        self.symlink(config, outside)
        real_open = open
        opened = []
        def guarded_open(path, *args, **kwargs):
            if os.path.realpath(path) == str(outside):
                opened.append(str(path))
                raise AssertionError('changed config opened outside owner')
            return real_open(path, *args, **kwargs)
        with patch('builtins.open', side_effect=guarded_open):
            with self.assertRaisesRegex(ValueError, 'config'):
                router.load_mount(entry)
        self.assertEqual(opened, [])


if __name__ == '__main__':
    unittest.main()
