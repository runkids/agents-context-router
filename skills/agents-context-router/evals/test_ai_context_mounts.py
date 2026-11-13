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


class MountCheckTests(MountFixture):
    def checked(self, failures=0):
        result = self.cli('check')
        self.assertEqual((result.returncode, result.stderr), (int(bool(failures)), ''),
                         result.stdout + result.stderr)
        summary = 'ok' if not failures else f'{failures} root(s) failed'
        self.assertEqual(result.stdout.splitlines()[-1], summary)
        self.assertEqual(result.stdout.splitlines().count(summary), 1)
        self.assertNotIn('problem(s)', result.stdout)
        return result.stdout

    def fresh(self):
        # Each mutation gets a new synthetic parent, and every parent is
        # registered for cleanup by the existing fixture, even on assertion.
        MountFixture.setUp(self)

    def test_review55_invalid_mounts_fail_check(self):
        # Review32099: a clean local root must not certify an invalid mount.
        for declaration, config, reason in [
                ({'root': '../outside'}, None, 'root'),
                ({'root': 'modules/kb-core', 'typo': True}, None, 'typo'),
                ({'root': 'modules/kb-core'}, '{', 'JSON'),
                ({'root': 'modules/kb-core'}, '{"topics": []}', 'topics'),
                ({'root': 'modules/kb-core'}, '{"topics": {}, "mounts": {"bad": {}}}', 'nested')]:
            with self.subTest(declaration=declaration, reason=reason):
                self.fresh()
                self.cfg['unrouted'] = {'modules/*': 'Independent module data'}
                self.cfg['mounts']['kb'] = declaration
                self.sibling()
                if config is not None:
                    self.write('modules/kb-core/wiki/ai-context.json', config)
                out = self.checked(1)
                self.assertIn('FAIL mount kb:', out)
                self.assertIn(reason, out)
                self.assertIn(f'{"other/guide":18} ', out)
                self.assertNotIn('NOTICE', out)

    def test_independent_discovery(self):
        out = self.checked()
        self.assertIn(f'{"guide":18} ', out)
        self.assertIn(f'{"kb/guide":18} ', out)
        self.assertIn(f'{"kb/AGENTS.md":18} ', out)
        self.write('AGENTS.md', '`guide`\n`kb/guide`\n')
        self.write('modules/kb-core/AGENTS.md', 'No topic discovery.\n')
        self.assertIn('FAIL mount kb: guide: not listed in AGENTS.md', self.checked(1))
        self.write('AGENTS.md', 'No topic discovery.\n')
        self.write('modules/kb-core/AGENTS.md', '`guide`\n')
        out = self.checked(1)
        self.assertIn('FAIL guide: not listed in AGENTS.md', out)
        self.assertNotIn('FAIL mount kb: guide: not listed', out)
        self.write('AGENTS.md', '`guide`\n')
        self.inner_cfg['rootInstructions'] = 'KERNEL.md'
        self.write('modules/kb-core/KERNEL.md', '`guide`\n')
        self.inner_cfg['unrouted'] = {'AGENTS.md': 'Use KERNEL.md'}
        self.save_configs()
        self.assertIn(f'{"kb/KERNEL.md":18} ', self.checked())

    def test_budget_ownership(self):
        native = '<!-- wiki/guide.md -->\n# Guide\nModule.'
        self.assertEqual(len(native.encode('utf-8')), 38)
        raw_kernel = '`guide`\n  \t\n知識\n'
        root_bytes = len(raw_kernel.encode('utf-8'))
        self.write('modules/kb-core/AGENTS.md', raw_kernel)
        self.cfg['budgets'] = {'rootInstructionsMaxBytes': 10000, 'defaultTopicMaxBytes': 10000}
        self.sibling()
        self.inner_cfg['budgets'] = {'rootInstructionsMaxBytes': root_bytes, 'defaultTopicMaxBytes': 38}
        self.save_configs()
        self.assertIn(f'{"kb/guide":18} {38:6} B  (cap 38)', self.checked())
        direct = self.cli('check', root=self.module_root, config=self.module_root / 'wiki/ai-context.json')
        self.assertEqual((direct.returncode, direct.stderr), (0, ''))
        self.assertIn(f'{"guide":18} {38:6} B  (cap 38)', direct.stdout)
        self.inner_cfg['budgets']['defaultTopicMaxBytes'] = 37
        self.save_configs()
        self.assertIn('FAIL mount kb: guide: 38 B > 37', self.checked(1))
        self.inner_cfg['topics']['guide']['maxBytes'] = 38
        self.save_configs()
        self.checked()
        self.inner_cfg['budgets']['rootInstructionsMaxBytes'] = root_bytes - 1
        self.save_configs()
        self.assertIn(f'FAIL mount kb: AGENTS.md {root_bytes} B > {root_bytes - 1}', self.checked(1))
        self.inner_cfg['budgets']['rootInstructionsMaxBytes'] = root_bytes
        long_root = self.root / 'modules/a-very-long-consumer-directory/knowledge/core'
        long_root.parent.mkdir(parents=True)
        self.module_root.rename(long_root)
        self.module_root = long_root
        self.cfg['mounts']['kb']['root'] = str(long_root)
        self.save_configs()
        self.assertIn(f'{"kb/guide":18} {38:6} B  (cap 38)', self.checked())
        absolute = str(self.module_root / 'wiki/guide.md')
        self.inner_cfg['topics']['guide']['sources'][0]['path'] = absolute
        absolute_bytes = len(('<!-- ' + absolute + ' -->\n# Guide\nModule.').encode('utf-8'))
        self.inner_cfg['topics']['guide']['maxBytes'] = absolute_bytes
        self.save_configs()
        self.assertIn(f'{"kb/guide":18} {absolute_bytes:6} B', self.checked())
        self.inner_cfg['topics']['guide']['maxBytes'] -= 1
        self.save_configs()
        self.assertIn(f'{absolute_bytes} B > {absolute_bytes - 1}', self.checked(1))
        self.inner_cfg['topics']['guide']['sources'][0]['path'] = 'wiki/guide.md'
        self.inner_cfg['topics']['guide']['maxBytes'] = 38
        self.write(str(long_root / 'wiki/guide.md'), '# Guide\n模組。\n')
        multibyte = len('<!-- wiki/guide.md -->\n# Guide\n模組。'.encode('utf-8'))
        self.inner_cfg['topics']['guide']['maxBytes'] = multibyte
        self.save_configs()
        self.checked()
        self.inner_cfg['topics']['guide']['maxBytes'] -= 1
        self.save_configs()
        self.assertIn(f'{multibyte} B > {multibyte - 1}', self.checked(1))

    def test_failed_roots_continue(self):
        for kind, reason in [('missing', 'missing root'), ('outside', 'root'),
                             ('declaration', 'declaration'), ('config-missing', 'config'),
                             ('config-directory', 'config'),
                             ('config-json', 'JSON'), ('nested', 'nested'),
                             ('kernel-missing', 'AGENTS.md'), ('kernel-utf8', 'AGENTS.md')]:
            with self.subTest(kind=kind):
                self.fresh()
                self.sibling()
                if kind == 'missing':
                    self.cfg['mounts']['kb']['root'] = 'modules/absent'
                    self.cfg['unrouted'] = {'modules/kb-core/*': 'Unmounted data'}
                elif kind == 'outside':
                    self.cfg['mounts']['kb']['root'] = '../outside'
                    self.cfg['unrouted'] = {'modules/kb-core/*': 'Unmounted data'}
                elif kind == 'declaration':
                    self.cfg['mounts']['kb'] = None
                    self.cfg['unrouted'] = {'modules/kb-core/*': 'Unmounted data'}
                elif kind == 'nested':
                    self.inner_cfg['mounts'] = {'never-follow': {'root': '../'}}
                self.save_configs()
                if kind == 'config-missing':
                    (self.module_root / 'wiki/ai-context.json').unlink()
                elif kind == 'config-directory':
                    (self.module_root / 'wiki/ai-context.json').unlink()
                    (self.module_root / 'wiki/ai-context.json').mkdir()
                elif kind == 'config-json':
                    self.write('modules/kb-core/wiki/ai-context.json', '{')
                elif kind == 'kernel-missing':
                    (self.module_root / 'AGENTS.md').unlink()
                elif kind == 'kernel-utf8':
                    (self.module_root / 'AGENTS.md').write_bytes(b'\xff')
                out = self.checked(1)
                self.assertIn('FAIL mount kb:', out)
                self.assertIn(reason, out)
                self.assertIn(f'{"other/guide":18} ', out)
        self.fresh()
        self.sibling()
        self.write('AGENTS.md', 'No discovery.\n')
        self.write('modules/kb-core/AGENTS.md', 'No discovery.\n')
        self.write('wiki/extra.md', '# Orphan\n')
        out = self.checked(2)
        self.assertIn('FAIL guide: not listed', out)
        self.assertIn('FAIL mount kb: guide: not listed', out)
        self.assertIn(f'{"other/guide":18} ', out)

    def test_each_inner_rule(self):
        cases = [('wiki/extra.md', '# Extra\n', 'wiki page no topic loads'),
                 ('wiki/history/log.md', '# History\n', 'history file not indexed'),
                 ('pkg/AGENTS.md', 'Scoped.\n', 'scoped instructions no topic loads'),
                 ('docs/runbook.md', '# Runbook\n', 'indexed page not named'),
                 ('wiki/guide.md', '# Renamed\n', 'found 0x'),
                 ('wiki/guide.md', '# Guide\nOne\n# Guide\nTwo\n', 'found 2x'),
                 ('wiki/guide.md', '# Guide\nSelected\n# Else\n[Bad](missing.md)\n', 'relative link'),
                 ('wiki/extra.md', '[Bad](missing.md)\n', 'relative link'),
                 ('wiki/history/log.md', '[Bad](missing.md)\n', 'relative link'),
                 ('wiki/README.md', '[Bad](missing.md)\n', 'relative link')]
        for path, text, reason in cases:
            with self.subTest(path=path, reason=reason):
                self.fresh()
                self.sibling()
                self.write('modules/kb-core/' + path, text)
                # Outer exceptions and references cannot satisfy an inner rule.
                self.cfg['unrouted'] = {'*': 'Outer-only exception'}
                self.cfg['skipDirs'] = ['modules']
                self.write('AGENTS.md', '`guide`\n' + path + '\n')
                if path == 'docs/runbook.md':
                    self.inner_cfg['indexed'] = ['docs/*.md']
                if path == 'wiki/guide.md':
                    self.inner_cfg['topics']['guide']['sources'][0]['heading'] = 'Guide'
                if reason == 'relative link' and path == 'wiki/extra.md':
                    self.inner_cfg['unrouted'] = {'wiki/extra.md': 'Human reference'}
                if reason == 'relative link' and path == 'wiki/history/log.md':
                    self.write('modules/kb-core/wiki/README.md', 'history/log.md\n')
                self.save_configs()
                out = self.checked(1)
                self.assertIn('FAIL mount kb:', out)
                self.assertIn(reason, out)
                self.assertIn(f'{"other/guide":18} ', out)
        self.fresh()
        self.write('modules/kb-core/wiki/extra.md', '# Human reference\n')
        self.write('modules/kb-core/generated/AGENTS.md', 'Generated.\n')
        self.inner_cfg['unrouted'] = {'wiki/extra.md': 'Human reference'}
        self.inner_cfg['skipDirs'] = ['generated']
        self.save_configs()
        self.checked()
        self.inner_cfg.update(wikiDir='context', historyDir='logs', routerFile='context/index.md',
                              indexed=['docs/*.md'])
        self.write('modules/kb-core/context/index.md', 'logs/log.md\ndocs/runbook.md\n')
        self.write('modules/kb-core/logs/log.md', '# History\n')
        self.write('modules/kb-core/docs/runbook.md', '# Runbook\n')
        self.save_configs()
        self.checked()
        self.fresh()
        self.symlink(self.module_root / 'wiki/again', self.module_root / 'wiki', directory=True)
        self.checked()

    def test_inventory_ownership_and_aliases(self):
        for location in ['modules/kb-core', 'wiki/kb-core']:
            with self.subTest(location=location):
                self.fresh()
                target = self.root / location
                if target != self.module_root:
                    self.module_root.rename(target)
                    self.module_root = target
                self.cfg['mounts']['kb']['root'] = location
                self.cfg['mounts']['same'] = {'root': location}
                self.cfg['indexed'] = ['**/*.md']
                self.write('AGENTS.md', '`guide`\nAGENTS.md wiki/README.md\n')
                self.symlink(self.root / 'wiki/module-alias', target, directory=True)
                self.symlink(self.root / 'wiki/page-alias.md', target / 'wiki/guide.md')
                self.save_configs()
                out = self.checked()
                self.assertIn(f'{"same/guide":18} ', out)
                # Observe the outer walkers alone. Mounted checks legitimately
                # read the same subtree later with their independent rules.
                real_open, real_scan = open, os.scandir
                forbidden = []
                def owned(path):
                    physical = os.path.realpath(path)
                    return physical == str(target) or physical.startswith(str(target) + os.sep)
                def guarded_open(path, *args, **kwargs):
                    if owned(path):
                        forbidden.append(str(path))
                        raise AssertionError('outer automatic inventory read owned file')
                    return real_open(path, *args, **kwargs)
                def guarded_scan(path):
                    if owned(path):
                        forbidden.append(str(path))
                        raise AssertionError('outer automatic inventory scanned owned tree')
                    return real_scan(path)
                with patch.object(router, 'ROOT', str(self.root)), \
                        patch('builtins.open', side_effect=guarded_open), \
                        patch.object(router.os, 'scandir', side_effect=guarded_scan):
                    self.assertEqual(router.orphans(self.cfg, 'AGENTS.md wiki/README.md',
                                                   excluded_roots=[str(target)]), [])
                    self.assertEqual(router.link_problems(self.cfg, excluded_roots=[str(target)]), [])
                self.assertEqual(forbidden, [])
                neighbor = self.write(location + '-neighbor/wiki/extra.md', '# Unmounted\n')
                out = self.checked(1)
                self.assertIn(str(neighbor.relative_to(self.root)).replace(os.sep, '/'), out)
                neighbor.unlink()
                # An invalid config retains safe-root ownership; neither a
                # parent skip nor its exception can hide that mount failure.
                self.cfg['skipDirs'] = ['modules', 'wiki']
                self.cfg['unrouted'] = {'*': 'Outer rule only'}
                self.save_configs()
                (target / 'wiki/ai-context.json').unlink()
                out = self.checked(2)
                self.assertIn('FAIL mount kb: config', out)
                self.assertIn('FAIL mount same: config', out)
                self.assertNotIn('wiki page no topic loads', out)
                self.assertNotIn('indexed page not named', out)
                self.assertNotIn('scoped instructions no topic loads', out)
        self.fresh()
        # Physical overlap is permitted without recursive declarations. The
        # wider owner explicitly exempts its independently checked subroot.
        for path, text in [('AGENTS.md', '`guide`\n'), ('wiki/README.md', '# Router\n'),
                           ('wiki/guide.md', '# Guide\nPart.\n'),
                           ('wiki/ai-context.json', json.dumps(self.config('Part guide')))]:
            self.write('modules/kb-core/part/' + path, text)
        self.cfg['mounts']['part'] = {'root': 'modules/kb-core/part'}
        self.inner_cfg['unrouted'] = {'part/*': 'Separate independent owner'}
        self.save_configs()
        self.assertIn(f'{"part/guide":18} ', self.checked())

    def test_explicit_outer_sources_are_checked(self):
        inner_source = {'path': 'modules/kb-core/wiki/guide.md', 'heading': 'Guide'}
        self.cfg['topics']['guide']['sources'].append(inner_source)
        self.cfg['skipDirs'] = ['modules']
        self.write('modules/kb-core/wiki/guide.md', '# Guide\nSelected.\n# Other\n[Bad](missing.md)\n')
        self.save_configs()
        out = self.checked(2)
        self.assertIn('FAIL modules/kb-core/wiki/guide.md:4: relative link', out)
        self.assertIn('FAIL mount kb: wiki/guide.md:4: relative link', out)
        self.write('modules/kb-core/wiki/guide.md', '# Guide\nModule.\n')
        inner_source['heading'] = 'Missing'
        self.save_configs()
        self.assertIn("FAIL guide: modules/kb-core/wiki/guide.md: heading 'Missing' found 0x", self.checked(1))
        inner_source['heading'] = 'Guide'
        self.cfg['topics']['guide']['maxBytes'] = 1
        self.save_configs()
        self.assertIn('FAIL guide:', self.checked(1))
        self.cfg['topics']['guide'].pop('maxBytes')
        self.cfg['topics']['guide']['sources'].pop()
        self.cfg['routerFile'] = 'modules/kb-core/wiki/README.md'
        self.cfg['unrouted'] = {'wiki/README.md': 'Using module router explicitly'}
        self.write('modules/kb-core/wiki/README.md', '[Bad](missing.md)\n')
        self.save_configs()
        self.assertIn('FAIL modules/kb-core/wiki/README.md:1: relative link', self.checked(2))
        self.fresh()
        self.write('wiki/guide.md', '# Guide\n[Module](../modules/kb-core/wiki/guide.md)\n')
        self.checked()
        self.write('modules/kb-core/wiki/guide.md', '# Guide\n[Project](../../../wiki/guide.md)\n')
        self.assertIn('FAIL mount kb: wiki/guide.md:2: relative link', self.checked(1))

    def test_absolute_and_alias_ownership(self):
        self.inner_cfg.update(rootInstructions=str(self.module_root / 'AGENTS.md'),
                              wikiDir=str(self.module_root / 'wiki'),
                              historyDir=str(self.module_root / 'wiki/history'),
                              routerFile=str(self.module_root / 'wiki/README.md'), indexed=['docs/*.md'])
        self.inner_cfg['topics']['guide']['sources'] = [
            {'path': str(self.module_root / 'wiki/guide.md'), 'heading': 'Guide'}]
        self.write('modules/kb-core/wiki/README.md', 'history/log.md\ndocs/runbook.md\n')
        self.write('modules/kb-core/wiki/history/log.md', '# History\n')
        self.write('modules/kb-core/docs/runbook.md', '# Runbook\n')
        self.save_configs()
        self.checked()
        self.symlink(self.module_root / 'wiki/alias.md', self.module_root / 'wiki/guide.md')
        self.inner_cfg['topics']['guide']['sources'][0]['path'] = 'wiki/alias.md'
        self.save_configs()
        self.checked()
        self.symlink(self.module_root / 'KERNEL.md', self.module_root / 'AGENTS.md')
        self.symlink(self.module_root / 'router-alias.md', self.module_root / 'wiki/README.md')
        self.inner_cfg['rootInstructions'] = 'KERNEL.md'
        self.inner_cfg['routerFile'] = 'router-alias.md'
        self.save_configs()
        self.checked()
        self.symlink(self.module_root / 'wiki-alias', self.module_root / 'wiki', directory=True)
        self.inner_cfg['wikiDir'] = 'wiki-alias'
        self.save_configs()
        self.checked()
        # Each lexical alias has its own link base despite one physical file.
        self.fresh()
        self.write('modules/kb-core/docs/page.md', '[Neighbor](neighbor.md)\n')
        self.write('modules/kb-core/docs/neighbor.md', '# Neighbor\n')
        self.symlink(self.module_root / 'wiki/alias.md', self.module_root / 'docs/page.md')
        self.inner_cfg['topics']['guide']['sources'] = [
            {'path': 'wiki/guide.md'}, {'path': 'wiki/alias.md'}, {'path': 'docs/page.md'}]
        for reverse in [False, True]:
            if reverse:
                self.inner_cfg['topics']['guide']['sources'].reverse()
            self.save_configs()
            out = self.checked(1)
            self.assertEqual(out.count('FAIL mount kb: wiki/alias.md:1: relative link'), 1)
            self.assertNotIn('FAIL mount kb: docs/page.md:1: relative link', out)

    def test_mounted_reads_stay_inside(self):
        for kind in ['instructions-relative', 'instructions-absolute', 'instructions-alias',
                     'source-relative', 'source-absolute', 'source-alias', 'source-directory',
                     'router-relative', 'router-alias', 'wiki-alias', 'indexed-alias',
                     'link-relative', 'link-encoded']:
            with self.subTest(kind=kind):
                self.fresh()
                inside_outer = not kind.endswith('alias')
                outside = self.write('outer-only/secret.md' if inside_outer else
                                     str(self.parent / 'outside/secret.md'), '# Outside inner owner\n')
                relative = '../../outer-only/secret.md'
                detail = 'secret.md'
                if kind.startswith('instructions'):
                    self.inner_cfg['rootInstructions'] = relative
                    if kind.endswith('absolute'):
                        self.inner_cfg['rootInstructions'] = str(outside)
                    elif kind.endswith('alias'):
                        self.symlink(self.module_root / 'kernel.md', outside)
                        self.inner_cfg['rootInstructions'] = 'kernel.md'
                        detail = 'kernel.md'
                elif kind.startswith('source'):
                    source = self.inner_cfg['topics']['guide']['sources'][0]
                    source['path'] = relative
                    if kind.endswith('absolute'):
                        source['path'] = str(outside)
                    elif kind.endswith('alias'):
                        self.symlink(self.module_root / 'wiki/escape.md', outside)
                        source['path'] = 'wiki/escape.md'
                        detail = 'escape.md'
                    elif kind.endswith('directory'):
                        source['path'] = 'wiki'
                        detail = 'wiki'
                elif kind.startswith('router'):
                    self.inner_cfg['routerFile'] = relative
                    if kind.endswith('alias'):
                        self.symlink(self.module_root / 'wiki/router.md', outside)
                        self.inner_cfg['routerFile'] = 'wiki/router.md'
                        detail = 'router.md'
                elif kind == 'wiki-alias':
                    self.symlink(self.module_root / 'wiki/escape', outside.parent, directory=True)
                    detail = 'wiki/escape'
                elif kind == 'indexed-alias':
                    self.symlink(self.module_root / 'docs/escape.md', outside)
                    self.inner_cfg['indexed'] = ['docs/*.md']
                    self.write('modules/kb-core/AGENTS.md', '`guide`\ndocs/escape.md\n')
                    detail = 'docs/escape.md'
                else:
                    destination = '../../../outer-only/secret.md'
                    if kind == 'link-encoded':
                        destination = '%2e%2e/%2e%2e/%2e%2e/outer-only/secret.md'
                    self.write('modules/kb-core/wiki/guide.md', '# Guide\n[Outside](' + destination + ')\n')
                self.save_configs()
                real_open, real_scan = open, os.scandir
                forbidden = []
                def guarded_open(path, *args, **kwargs):
                    if os.path.realpath(path) == str(outside):
                        forbidden.append(str(path))
                        raise AssertionError('external content opened')
                    return real_open(path, *args, **kwargs)
                def guarded_scan(path):
                    # For file escapes into the outer project, its automatic
                    # walk may legitimately scan outer-only. Alias scan cases
                    # target a sibling outside BOTH roots, still in this temp.
                    if not inside_outer and os.path.realpath(path) == str(outside.parent):
                        forbidden.append(str(path))
                        raise AssertionError('external directory scanned')
                    return real_scan(path)
                with patch('builtins.open', side_effect=guarded_open), \
                        patch.object(router.os, 'scandir', side_effect=guarded_scan):
                    code, out, err = self.call_main('check')
                self.assertEqual((code, err), (1, ''), out + err)
                self.assertIn('FAIL mount kb:', out)
                self.assertIn(detail, out)
                self.assertEqual(forbidden, [])
        self.fresh()
        self.write('modules/kb-core/wiki/guide.md', '# Guide\n'
                   '[External](https://example.invalid) [Absolute](/not/read) [Fragment](#guide)\n')
        self.checked()

    def test_directory_settings_and_regular_file_boundaries(self):
        for field in ['wikiDir', 'historyDir', 'routerFile', 'rootInstructions']:
            for spelling in ['relative', 'absolute', 'alias']:
                with self.subTest(field=field, spelling=spelling):
                    self.fresh()
                    outside = self.write(str(self.parent / 'outside/secret.md'), '# Outside\n')
                    target = outside.parent if field in ('wikiDir', 'historyDir') else outside
                    if spelling == 'relative':
                        value = os.path.relpath(target, self.module_root)
                    elif spelling == 'absolute':
                        value = str(target)
                    else:
                        alias = self.module_root / ('external' if target.is_dir() else 'external.md')
                        self.symlink(alias, target, directory=target.is_dir())
                        value = alias.name
                    self.inner_cfg[field] = value
                    self.save_configs()
                    real_open, real_scan = open, os.scandir
                    forbidden = []
                    def guarded_open(path, *args, **kwargs):
                        if os.path.realpath(path) == str(outside):
                            forbidden.append(str(path))
                            raise AssertionError('outside configured file read')
                        return real_open(path, *args, **kwargs)
                    def guarded_scan(path):
                        if os.path.realpath(path) == str(outside.parent):
                            forbidden.append(str(path))
                            raise AssertionError('outside configured directory scanned')
                        return real_scan(path)
                    with patch('builtins.open', side_effect=guarded_open), \
                            patch.object(router.os, 'scandir', side_effect=guarded_scan):
                        code, out, err = self.call_main('check')
                    self.assertEqual((code, err), (1, ''), out + err)
                    self.assertIn('FAIL mount kb:', out)
                    self.assertIn(field, out)
                    self.assertIn(value, out)
                    self.assertEqual(forbidden, [])
        for field in ['rootInstructions', 'routerFile']:
            with self.subTest(directory_file=field):
                self.fresh()
                self.inner_cfg[field] = 'wiki'
                self.save_configs()
                out = self.checked(1)
                self.assertIn('FAIL mount kb:', out)
                self.assertIn('wiki', out)
        self.fresh()
        # A referenced indexed-only dangling file must still fail file checks;
        # the reference deliberately prevents the orphan rule masking it.
        self.symlink(self.module_root / 'docs/broken.md', self.module_root / 'absent.md')
        self.inner_cfg['indexed'] = ['docs/*.md']
        self.write('modules/kb-core/AGENTS.md', '`guide`\ndocs/broken.md\n')
        self.save_configs()
        out = self.checked(1)
        self.assertIn('FAIL mount kb: docs/broken.md', out)
        self.assertNotIn('indexed page not named', out)

    def test_explicit_checkers_keep_globals_and_references(self):
        self.write('modules/kb-core/docs/runbook.md', '# Indexed\n')
        self.inner_cfg['indexed'] = ['docs/*.md']
        self.write('AGENTS.md', '`guide`\ndocs/runbook.md\n')
        self.save_configs()
        original = router.ROOT, router.CFG_PATH
        for owner, cfg, expected in [(self.root, self.cfg, []),
                                      (self.module_root, self.inner_cfg, ['docs/runbook.md']),
                                      (self.root, self.cfg, [])]:
            excluded = [str(self.module_root)] if owner == self.root else []
            problems = router.orphans(cfg, root=str(owner), excluded_roots=excluded)
            self.assertEqual([item.split(':', 1)[0] for item in problems], expected)
            self.assertEqual(router.link_problems(cfg, root=str(owner), excluded_roots=excluded), [])
            output = io.BytesIO()
            stream = io.TextIOWrapper(output, encoding='utf-8')
            try:
                with patch.object(sys, 'stdout', stream):
                    code = router.check(cfg, root=str(owner), excluded_roots=excluded)
                stream.flush()
                text = output.getvalue().decode('utf-8')
            finally:
                stream.close()
            self.assertEqual(code, int(bool(expected)), text)
            self.assertEqual((router.ROOT, router.CFG_PATH), original)
        self.write('modules/kb-core/AGENTS.md', '`guide`\ndocs/runbook.md\n')
        self.checked()

    def test_owned_read_errors_continue(self):
        for relative, operation in [('wiki/ai-context.json', 'read'), ('AGENTS.md', 'read'),
                                    ('wiki/guide.md', 'read'),
                                    ('wiki/README.md', 'read'), ('wiki', 'scan')]:
            for fault in ['denied', 'utf8'] if operation == 'read' else ['denied']:
                with self.subTest(relative=relative, fault=fault):
                    self.fresh()
                    self.sibling()
                    target = self.module_root / relative
                    real_open, real_scan = open, os.scandir
                    if fault == 'utf8':
                        target.write_bytes(b'\xff')
                    def failing_open(path, *args, **kwargs):
                        if fault == 'denied' and operation == 'read' and os.path.abspath(path) == str(target):
                            raise PermissionError('synthetic denied read')
                        return real_open(path, *args, **kwargs)
                    def failing_scan(path):
                        if operation == 'scan' and os.path.abspath(path) == str(target):
                            raise PermissionError('synthetic denied scan')
                        return real_scan(path)
                    with patch('builtins.open', side_effect=failing_open), \
                            patch.object(router.os, 'scandir', side_effect=failing_scan):
                        code, out, err = self.call_main('check')
                    self.assertEqual((code, err), (1, ''), out + err)
                    self.assertIn('FAIL mount kb:', out)
                    self.assertIn(relative, out)
                    self.assertIn(f'{"other/guide":18} ', out)
                    self.assertTrue(out.endswith('1 root(s) failed\n'), out)
        self.fresh()
        self.sibling()
        (self.root / 'AGENTS.md').unlink()
        out = self.checked(1)
        self.assertIn('FAIL AGENTS.md', out)
        self.assertIn(f'{"kb/guide":18} ', out)
        self.assertIn(f'{"other/guide":18} ', out)


if __name__ == '__main__':
    unittest.main()
