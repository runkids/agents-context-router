#!/usr/bin/env python3
"""Print only the doc sections a task needs.

usage: ai-context.py list | <topic> [<topic>...] | check

Topics live in wiki/ai-context.json. A source is a whole file or one exact
heading (the section runs to the next heading of the same or higher level).
check also fails on orphans, so docs cannot silently drift out of the router:
wiki pages no topic loads, history files missing from the router index, and
nested AGENTS.md files no topic loads, and opted-in indexed pages no instructions name.
List deliberate exceptions under
"unrouted" in the config as exact paths or case-sensitive fnmatch globs,
each with a reason. Keys match themselves and other names via fnmatch, regardless
of existence; use wiki/file[[]1].md to exempt the literal wiki/file[1].md
without matching wiki/file1.md.
Keys normalize backslashes to /; * also matches /.
Copy this file to <repo>/scripts/ai-context.py; the repo root is its parent's parent.
For a shared installation, set AI_CONTEXT_ROOT and optionally AI_CONTEXT_CONFIG
(default: <root>/wiki/ai-context.json). Explicit relative overrides resolve from
the invocation cwd independently; relative paths inside the config resolve from ROOT.
Empty or unset overrides use the defaults.
No dependencies beyond the Python 3.8+ standard library.
"""
import fnmatch, json, os, re, sys

ROOT = os.path.realpath(os.environ.get('AI_CONTEXT_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CFG_PATH = os.path.realpath(os.environ.get('AI_CONTEXT_CONFIG') or os.path.join(ROOT, 'wiki', 'ai-context.json'))
HEAD = re.compile(r'^(#{1,6})\s+(.+?)\s*#*\s*$')
FENCE = re.compile(r'^\s{0,3}(`{3,}|~{3,})')


def load_cfg():
    if not os.path.exists(CFG_PATH):
        sys.exit(f'missing {CFG_PATH}; copy this script to <repo>/scripts/ and create wiki/ai-context.json, or set AI_CONTEXT_ROOT and AI_CONTEXT_CONFIG for a shared installation')
    with open(CFG_PATH, encoding='utf-8') as f:
        return json.load(f)


def headings(lines):
    """Yield (index, level, text), skipping headings inside fenced code (e.g. shell comments)."""
    fence = None
    for i, ln in enumerate(lines):
        m = FENCE.match(ln)
        if m:
            mark = m.group(1)
            if fence is None:
                fence = mark[0] * len(mark)
            elif mark.startswith(fence):
                fence = None
            continue
        if fence is None and (h := HEAD.match(ln)):
            yield i, len(h.group(1)), h.group(2)


def section(src):
    path = os.path.realpath(os.path.join(ROOT, src['path'].replace('\\', '/')))
    if not path.startswith(os.path.join(ROOT, '')):
        raise ValueError(f'{src["path"]}: outside repo')
    with open(path, encoding='utf-8') as f:
        lines = f.read().split('\n')
    if 'heading' not in src:
        return '\n'.join(lines).strip()
    hs = list(headings(lines))
    hits = [(i, lv) for i, lv, t in hs if t == src['heading']]
    if len(hits) != 1:  # fail closed: a renamed or duplicated heading must not load the wrong text
        raise ValueError(f'{src["path"]}: heading {src["heading"]!r} found {len(hits)}x')
    start, level = hits[0]
    end = next((i for i, lv, _ in hs if i > start and lv <= level), len(lines))
    return '\n'.join(lines[start:end]).strip()


def render(cfg, name):
    out = []
    for s in cfg['topics'][name]['sources']:
        where = s['path'] + (f' § {s["heading"]}' if 'heading' in s else '')
        out.append(f'<!-- {where} -->\n{section(s)}')
    return '\n\n'.join(out)


def orphans(cfg, reference_text=''):
    """Docs that exist on disk but that no agent can reach through the router."""
    wiki = cfg.get('wikiDir', 'wiki')
    history = cfg.get('historyDir', f'{wiki}/history')
    router = cfg.get('routerFile', f'{wiki}/README.md')
    root_file = cfg.get('rootInstructions', 'AGENTS.md')
    routed = {s['path'].replace('\\', '/') for t in cfg['topics'].values() for s in t['sources']}
    allowed = {p.replace('\\', '/'): reason for p, reason in cfg.get('unrouted', {}).items()}
    router_text = open(os.path.join(ROOT, router), encoding='utf-8').read() if os.path.exists(os.path.join(ROOT, router)) else ''
    reference_text += '\n' + router_text
    indexed = cfg.get('indexed', [])
    bad = []
    skip = {'.git', 'node_modules', 'dist', 'build', 'vendor', '.venv', 'target'}
    for d, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in skip and not x.startswith('.')]
        for f in files:
            rel = os.path.relpath(os.path.join(d, f), ROOT).replace(os.sep, '/')
            if not f.endswith('.md'):
                continue
            reason = allowed.get(rel)
            if (any(fnmatch.fnmatch(rel, pattern) for pattern in indexed)
                    and rel not in routed and rel not in reference_text
                    and not (isinstance(reason, str) and reason.strip())):
                bad.append(f'{rel}: indexed page not named (name it in a topic page, route it, or list it under "unrouted" with a reason)')
            if rel in allowed or any(fnmatch.fnmatchcase(rel, p) for p in allowed):
                continue
            if rel.startswith(history + '/'):
                if os.path.relpath(rel, wiki).replace(os.sep, '/') not in router_text and rel not in router_text:
                    bad.append(f'{rel}: history file not indexed in {router}')
            elif rel.startswith(wiki + '/'):
                if rel != router and rel not in routed:
                    bad.append(f'{rel}: wiki page no topic loads (map it, or list it under "unrouted" with a reason)')
            elif f == 'AGENTS.md' and rel != root_file and rel not in routed:
                bad.append(f'{rel}: scoped instructions no topic loads')
    return bad


def check(cfg):
    bad = []
    budgets = cfg.get('budgets', {})
    root_file = cfg.get('rootInstructions', 'AGENTS.md')
    root_text = open(os.path.join(ROOT, root_file), encoding='utf-8').read()
    reference_text = [root_text]
    root_size = len(root_text.encode())
    root_cap = budgets.get('rootInstructionsMaxBytes', 8192)
    print(f'{root_file:18} {root_size:6} B  (cap {root_cap})')
    if root_size > root_cap:
        bad.append(f'{root_file} {root_size} B > {root_cap}')
    for name, t in cfg['topics'].items():
        if f'`{name}`' not in root_text:
            bad.append(f'{name}: not listed in {root_file} (agents will not know it exists)')
        try:
            rendered = render(cfg, name)
            size = len(rendered.encode())
        except (ValueError, OSError) as e:
            bad.append(f'{name}: {e}')
            continue
        reference_text.append(rendered)
        cap = t.get('maxBytes', budgets.get('defaultTopicMaxBytes', 16384))
        print(f'{name:18} {size:6} B  (cap {cap})')
        if size > cap:
            bad.append(f'{name}: {size} B > {cap} (split the topic; do not raise the cap)')
    bad = orphans(cfg, '\n'.join(reference_text)) + bad
    for b in bad:
        print('FAIL', b)
    print('ok' if not bad else f'{len(bad)} problem(s)')
    return 1 if bad else 0


def main(argv):
    sys.stdout.reconfigure(encoding='utf-8')  # section markers and CJK pages break cp1252/cp950 consoles on Windows
    sys.stderr.reconfigure(encoding='utf-8')  # error messages can carry non-ASCII paths
    cfg = load_cfg()
    args = argv[1:] or ['list']
    if args == ['list']:
        for n, t in cfg['topics'].items():
            print(f'{n:18} {t["description"]}')
        return 0
    if args == ['check']:
        return check(cfg)
    unknown = [a for a in args if a not in cfg['topics']]
    if unknown:
        sys.exit(f'unknown topic {unknown[0]!r}; rerun this script with list')
    print('\n\n'.join(render(cfg, a) for a in args))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
