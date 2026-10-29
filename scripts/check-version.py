#!/usr/bin/env python3
"""Check the versions declared in Release Please's update list."""
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def problems(root):
    version = json.loads((root / 'package.json').read_text(encoding='utf-8'))['version']
    manifest = json.loads((root / '.release-please-manifest.json').read_text(encoding='utf-8'))
    versions = {'.release-please-manifest.json': [manifest['.']]}
    config = json.loads((root / 'release-please-config.json').read_text(encoding='utf-8'))
    for entry in config['packages']['.']['extra-files']:
        path = entry['path']
        text = (root / path).read_text(encoding='utf-8')
        if entry['type'] == 'json':
            value = json.loads(text)
            # The configured JSON paths only use field names and array indexes.
            for key in re.findall(r'\w+', entry['jsonpath']):
                value = value[int(key)] if isinstance(value, list) else value[key]
            versions[path] = [value]
        else:
            versions[path] = re.findall(r'[\'"]([^\'"\n]+)[\'"]\s*# x-release-please-version', text)
    bad = [f'{path}: expected {version}, found {values!r}'
           for path, values in versions.items() if values != [version]]
    return bad


if __name__ == '__main__':
    try:
        bad = problems(ROOT)
    except (OSError, ValueError, KeyError, IndexError, TypeError) as error:
        sys.exit(str(error))
    if bad:
        sys.exit('\n'.join(bad))
    print('All release versions match package.json.')
