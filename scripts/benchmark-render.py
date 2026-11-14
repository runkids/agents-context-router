#!/usr/bin/env python3
"""Synthetic opt-in render benchmark; no private data or optional dependencies.

Reports UTF-8 bytes, source reads/heading scans, and interleaved fresh-process
median wall time, including interpreter startup. The pair approximates an
overlap shape; its text is generated, not copied from a real repository.
"""
import importlib.util
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/agents-context-router/scripts/ai-context.py'
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('router', SCRIPT)
router = importlib.util.module_from_spec(spec)
spec.loader.exec_module(router)


def benchmark(root, label, cfg, runs=61):
    selected = list(cfg['topics'])
    config = root / 'wiki/ai-context.json'
    config.write_text(json.dumps(cfg), encoding='utf-8')
    env = dict(os.environ, AI_CONTEXT_ROOT=str(root), AI_CONTEXT_CONFIG=str(config))
    times, counts, sizes = {False: [], True: []}, {}, {}
    for dedupe in (False, True):
        cache, seen = ({}, set()) if dedupe else (None, None)
        with patch.object(router, 'read_text', wraps=router.read_text) as reads, \
                patch.object(router, 'headings', wraps=router.headings) as headings:
            bodies = [router.render(cfg, topic, root=str(root), cache=cache, seen=seen)
                      for topic in selected]
            counts[dedupe] = [reads.call_count, headings.call_count]
        sizes[dedupe] = len(('\n\n'.join(body for body in bodies if body) + '\n').encode('utf-8'))
    for iteration in range(runs):
        for dedupe in ([False, True] if iteration % 2 == 0 else [True, False]):
            command = [sys.executable, str(SCRIPT)] + (['--dedupe'] if dedupe else []) + selected
            start = time.perf_counter()
            result = subprocess.run(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            elapsed = (time.perf_counter() - start) * 1000
            if result.returncode:
                raise RuntimeError(result.stderr.decode('utf-8'))
            if len(result.stdout) != sizes[dedupe]:
                raise AssertionError('CLI output size differs from rendered output')
            times[dedupe].append(elapsed)
    print(label, json.dumps({'bytes': sizes, 'reads_and_heading_parses': counts,
                            'median_ms': {key: round(statistics.median(value), 3)
                                          for key, value in times.items()}, 'runs': runs}))


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / 'wiki').mkdir()

        def page(name, size, headings=False):
            body = ('# Selected\n' + 'body\n' * size if headings else '# Guide\n' + 'x' * size)
            (root / 'wiki' / name).write_text(body + '\n', encoding='utf-8')

        page('shared.md', 4830)
        page('one.md', 4610)
        page('two.md', 4611)
        cfg = {'topics': {topic: {'description': topic, 'sources': [
            {'path': 'wiki/shared.md'}, {'path': f'wiki/{file}.md'}]}
            for topic, file in [('a', 'one'), ('b', 'two')]}}
        benchmark(root, 'representative_pair', cfg)

        refs = [0, 1, 0, 2, 0, 3, 0, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 1, 2]
        for index in set(refs):
            page(f'file{index}.md', 4800)
        cfg = {'topics': {f't{index}': {'description': 'Synthetic', 'sources': [
            {'path': f'wiki/file{ref}.md'} for ref in refs[index * 2:index * 2 + 2]]}
            for index in range(13)}}
        benchmark(root, '13_topics_25_refs_20_unique', cfg)

        page('large.md', 20000, headings=True)
        cfg = {'topics': {f't{index}': {'description': 'Repeated section', 'sources': [
            {'path': 'wiki/large.md', 'heading': 'Selected'}]} for index in range(40)}}
        benchmark(root, 'heading_stress_40_refs_100kb', cfg, runs=31)


if __name__ == '__main__':
    main()
