#!/usr/bin/env python3
"""Print only the doc sections a task needs.

usage: ai-context.py list | <topic> [<topic>...] | check

Topics live in wiki/ai-context.json. A source is a whole file or one exact
heading (the section runs to the next heading of the same or higher level).
check also fails on orphans, so docs cannot silently drift out of the router:
wiki pages no topic loads, history files missing from the router index, and
nested AGENTS.md files no topic loads, opted-in indexed pages no instructions name, and relative Markdown links are checked.
List deliberate routing exceptions under
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
from urllib.parse import unquote

ROOT = os.path.realpath(os.environ.get('AI_CONTEXT_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CFG_PATH = os.path.realpath(os.environ.get('AI_CONTEXT_CONFIG') or os.path.join(ROOT, 'wiki', 'ai-context.json'))
HEAD = re.compile(r'^(#{1,6})\s+(.+?)\s*#*\s*$')
FENCE = re.compile(r'^\s{0,3}(`{3,}|~{3,})')


def load_cfg():
    if not os.path.exists(CFG_PATH):
        sys.exit(f'missing {CFG_PATH}; copy this script to <repo>/scripts/ and create wiki/ai-context.json, or set AI_CONTEXT_ROOT and AI_CONTEXT_CONFIG for a shared installation')
    with open(CFG_PATH, encoding='utf-8') as f:
        return json.load(f)


def unfenced(lines):
    """Yield original indexes and lines outside fenced code."""
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
        if fence is None:
            yield i, ln


def headings(lines):
    """Yield (index, level, text), skipping fenced code (e.g. shell comments)."""
    for i, ln in unfenced(lines):
        if h := HEAD.match(ln):
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
    indexed = cfg.get('indexed', [])
    if not isinstance(indexed, list) or any(not isinstance(p, str) for p in indexed):
        return ['indexed: expected a list of strings']
    wiki = cfg.get('wikiDir', 'wiki')
    history = cfg.get('historyDir', f'{wiki}/history')
    router = cfg.get('routerFile', f'{wiki}/README.md')
    root_file = cfg.get('rootInstructions', 'AGENTS.md')
    routed = {s['path'].replace('\\', '/') for t in cfg['topics'].values() for s in t['sources']}
    allowed = {p.replace('\\', '/'): reason for p, reason in cfg.get('unrouted', {}).items()}
    router_text = open(os.path.join(ROOT, router), encoding='utf-8').read() if os.path.exists(os.path.join(ROOT, router)) else ''
    reference_text += '\n' + router_text
    bad = []
    skip = {'.git', 'node_modules', 'dist', 'build', 'vendor', '.venv', 'target'}
    for d, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x != '.git' and
                   (indexed or (x not in skip and not x.startswith('.')))]
        for f in files:
            rel = os.path.relpath(os.path.join(d, f), ROOT).replace(os.sep, '/')
            if not f.endswith('.md'):
                continue
            reasons = [reason for pattern, reason in allowed.items()
                       if rel == pattern or fnmatch.fnmatchcase(rel, pattern)]
            if (any(fnmatch.fnmatch(rel, pattern) for pattern in indexed)
                    and rel not in routed and rel not in reference_text
                    and not any(isinstance(reason, str) and reason.strip() for reason in reasons)):
                bad.append(f'{rel}: indexed page not named (name it in a topic page, route it, or list it under "unrouted" with a reason)')
            if (reasons or any(x in skip or x.startswith('.') for x in rel.split('/')[:-1])):
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


def destination(text, start):
    """Read an angle-wrapped or balanced bare Markdown destination."""
    start += len(text[start:]) - len(text[start:].lstrip())
    angle = text[start:start + 1] == '<'
    pos, depth = start + angle, 0
    begin = pos
    while pos < len(text):
        char = text[pos]
        if char == '\\' and pos + 1 < len(text):
            pos += 2
            continue
        if angle:
            if char == '>':
                return text[begin:pos], pos + 1
            if char == '\n':
                break
        else:
            if char.isspace() or (char == ')' and depth == 0):
                return text[begin:pos], pos
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
        pos += 1
    if not angle and depth == 0:
        return text[begin:pos], pos
    return None


def link_destinations(lines):
    """Yield original line and destination for inline links and used definitions."""
    visible = {i for i, _ in unfenced(lines)}
    text = '\n'.join(ln if i in visible else '' for i, ln in enumerate(lines))
    # Mask code spans, retaining their newlines and all original source offsets.
    code = re.compile(r'\\[^\n]|(`+)(?!`)([\s\S]*?)(?<!`)\1(?!`)')
    text = code.sub(lambda m: re.sub(r'[^\n]', ' ', m.group()) if m[1] else m.group(), text)
    label = re.compile(r'\[((?:\\.|[^\[\]\\])+)\]')
    normalize = lambda value: ' '.join(re.sub(r'\\([!"#$%&\'()*+,\-./:;<=>?@\[\]\\^_`{|}~])', r'\1', value).split()).casefold()
    definitions, used = {}, set()
    for line, ln in enumerate(text.split('\n'), 1):
        match = re.match(r'^ {0,3}\[((?:\\.|[^\]\\])+)\]:\s*', ln)
        if match:
            found = destination(ln, match.end())
            if found:
                definitions.setdefault(normalize(match[1]), (line, found[0]))
            continue
        pos = 0
        while pos < len(ln):
            if ln[pos] == '\\':
                # Escaped link/image markup is an example, not a destination.
                escaped = label.match(ln, pos + 1 + (ln[pos + 1:pos + 2] == '!'))
                pos = escaped.end() if escaped else pos + 2
                continue
            match = label.match(ln, pos)
            if not match:
                pos += 1
                continue
            end = match.end()
            if ln[end:end + 1] == '(':
                found = destination(ln, end + 1)
                if found:
                    tail = re.match(r'\s*(?:"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|\((?:\\.|[^)\\])*\))?\s*\)', ln[found[1]:])
                    if tail:
                        yield line, found[0]
                        pos = found[1] + tail.end()
                        continue
            reference = label.match(ln, end)
            if reference:
                used.add(normalize(reference[1]))
                end = reference.end()
            else:
                used.add(normalize(match[1]))
                if ln[end:end + 2] == '[]':
                    end += 2
            pos = end
    for name, value in definitions.items():
        if name in used:
            yield value


def link_problems(cfg):
    """Check local file links in whole routed sources and wiki Markdown pages."""
    paths = {s['path'].replace('\\', '/') for t in cfg['topics'].values() for s in t['sources']}
    wiki = cfg.get('wikiDir', 'wiki')
    paths.add(cfg.get('routerFile', f'{wiki}/README.md'))
    skip = {'.git', 'node_modules', 'dist', 'build', 'vendor', '.venv', 'target'}
    for directory, dirs, files in os.walk(os.path.join(ROOT, wiki)):
        dirs[:] = [d for d in dirs if d not in skip and not d.startswith('.')]
        paths.update(os.path.relpath(os.path.join(directory, f), ROOT)
                     for f in files if f.endswith('.md'))
    bad, seen = [], set()
    for rel in sorted(paths):
        path = os.path.realpath(os.path.join(ROOT, rel))
        if path in seen or not path.startswith(ROOT + os.sep) or not os.path.isfile(path):
            continue  # Rendering retains ownership of invalid source diagnostics.
        seen.add(path)
        with open(path, encoding='utf-8') as source:
            lines = source.read().split('\n')
        for line, raw in link_destinations(lines):
            dest = re.sub(r'\\([!"#$%&\'()*+,\-./:;<=>?@\[\]\\^_`{|}~])', r'\1', raw)
            if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', dest) or dest.startswith(('/', '\\', '#', '?')):
                continue
            dest = unquote(re.split(r'[?#]', dest, maxsplit=1)[0])
            if not dest:
                continue
            try:
                target = os.path.realpath(os.path.join(os.path.dirname(path), dest))
            except (OSError, ValueError):
                target = ''
            if not target.startswith(ROOT + os.sep) or not os.path.isfile(target):
                bad.append(f'{rel}:{line}: relative link {raw!r} is not a file inside repo')
    return bad


def check(cfg):
    bad = link_problems(cfg)
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
