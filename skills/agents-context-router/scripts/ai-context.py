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
from html import unescape

ROOT = os.path.realpath(os.environ.get('AI_CONTEXT_ROOT') or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CFG_PATH = os.path.realpath(os.environ.get('AI_CONTEXT_CONFIG') or os.path.join(ROOT, 'wiki', 'ai-context.json'))
HEAD = re.compile(r'^(#{1,6})\s+(.+?)\s*#*\s*$')
FENCE = re.compile(r'^\s{0,3}(`{3,}|~{3,})')
TITLE = r'(?:"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|\((?:\\.|[^)\\])*\))'


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


def markdown_unescape(value):
    return re.sub(r'\\([!"#$%&\'()*+,\-./:;<=>?@\[\]\\^_`{|}~])', r'\1', value)


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


def reference_definition(text):
    """Read one complete definition and its exact consumed line count."""
    match = re.match(r'^ {0,3}\[((?:\\.|[^\]\\])+)\]:', text)
    found = destination(text, match.end()) if match else None
    if not found or re.search(r'\n[ \t]*\n', text[:found[1]]):
        return None
    tail = re.match(r'[ \t]*(?:\n[ \t]*(?=' + TITLE + r'))?(?:' + TITLE + r')?[ \t]*(?:\n|$)', text[found[1]:])
    if tail:
        end = found[1] + tail.end()
        return match[1], found[0], text[:end].count('\n') + (not text[:end].endswith('\n'))
    return None


def markdown_text(lines):
    """Mask inactive Markdown contexts without changing offsets or line numbers."""
    blank = lambda value: re.sub(r'[^\n]', ' ', value)
    code = re.compile(r'\\[^\n]|(?<!`)(`+)(?!`)((?:(?!\n[ \t]*\n)[\s\S])*?)(?<!`)\1(?!`)')
    original = '\n'.join(lines)
    protected = code.sub(lambda m: blank(m.group()) if m[1] else m.group(), original).split('\n')
    result, definitions = [], []
    consumed, owner = 0, (0, 0)
    fence, raw, comment = None, None, False
    paragraph, list_indent, quote_depth = False, 0, 0
    for line_index, ln in enumerate(lines):
        if line_index < consumed:
            result.append(blank(ln))
            continue
        quote = re.match(r'^(?: {0,3}>[ \t]?)+', ln)
        prefix = quote.end() if quote else 0
        depth = ln[:prefix].count('>')
        content = ln[prefix:]
        indentation = len(content) - len(content.lstrip(' '))
        if (fence or raw is not None) and (depth < owner[0] or
                (owner[1] and content.strip() and indentation < owner[1])):
            fence, raw, paragraph = None, None, False
        if depth != quote_depth:
            paragraph, list_indent = False, 0
        quote_depth = depth
        marker = re.match(r'^ {0,3}(?:[-+*]|\d+[.)])[ \t]+', content)
        if marker and not (fence or raw is not None):
            list_indent = len(marker.group().expandtabs(4))
            prefix += marker.end()
            content = ln[prefix:]
            paragraph = False
        elif list_indent:
            spaces = len(content) - len(content.lstrip(' '))
            if spaces >= list_indent:
                prefix += list_indent
                content = ln[prefix:]
            elif content.strip():
                list_indent = 0
        indent = len(content.expandtabs(4)) - len(content.expandtabs(4).lstrip(' '))
        mark = FENCE.match(content)
        if fence:
            result.append(blank(ln))
            if mark and mark[1].startswith(fence) and not content[mark.end():].strip():
                fence = None
            paragraph = False
            continue
        if raw is not None:
            result.append(blank(ln))
            if (not raw and not content.strip()) or (raw and re.search(r'</' + raw + r'\s*>', content, re.I)):
                raw = None
            continue
        if indent >= 4 and not paragraph and not comment:
            result.append(blank(ln))
            continue
        # Ignore comment markers inside inline code; code blocks took precedence.
        probe = protected[line_index][prefix:]
        masked = list(content)
        pos = 0
        while pos < len(content):
            start = pos if comment else probe.find('<!--', pos)
            if start < 0:
                break
            end = content.find('-->', start + (0 if comment else 4))
            stop = len(content) if end < 0 else end + 3
            masked[start:stop] = blank(content[start:stop])
            comment = end < 0
            pos = stop
        content = ''.join(masked)
        mark = FENCE.match(content)
        html = re.match(r'^ {0,3}<(pre|script|style|textarea)(?:\s|>|$)', content, re.I)
        if mark and (mark[1][0] == '~' or '`' not in content[mark.end():]):
            fence = mark[1]
            owner = (depth, list_indent)
            result.append(blank(ln))
            paragraph = False
        elif html:
            raw = html[1].lower()
            owner = (depth, list_indent)
            if re.search(r'</' + raw + r'\s*>', content, re.I):
                raw = None
            result.append(blank(ln))
            paragraph = False
        elif re.match(r'^ {0,3}</?(?:address|article|aside|blockquote|details|div|dl|fieldset|figure|footer|form|h[1-6]|header|hr|li|main|nav|ol|p|section|table|tbody|td|th|thead|tr|ul)(?:\s|/?>|$)', content, re.I):
            raw = ''  # Ordinary HTML blocks end at a blank line.
            owner = (depth, list_indent)
            result.append(blank(ln))
            paragraph = False
        else:
            if not paragraph and content.lstrip().startswith('['):
                candidate = [content]
                for following in lines[line_index + 1:]:
                    q = re.match(r'^(?: {0,3}>[ \t]?)+', following)
                    qend = q.end() if q else 0
                    next_content = following[qend:]
                    if following[:qend].count('>') != depth or not next_content.strip():
                        break
                    if list_indent and not next_content.startswith(' ' * list_indent):
                        break
                    candidate.append(next_content[list_indent:])
                definition = reference_definition('\n'.join(candidate))
                if definition:
                    label, dest, count = definition
                    definitions.append((label, line_index + 1, dest))
                    consumed = line_index + count
                    result.append(blank(ln))
                    continue
            result.append(' ' * prefix + content)
            paragraph = bool(content.strip()) and not HEAD.match(content)
    text = '\n'.join(result)
    return code.sub(lambda m: blank(m.group()) if m[1] else m.group(), text), definitions


def link_destinations(lines):
    """Yield original line and destination for inline links and used definitions."""
    text, collected = markdown_text(lines)
    normalize = lambda value: ' '.join(markdown_unescape(value).split()).casefold()
    definitions, used = {}, set()
    for label, line, dest in collected:
        definitions.setdefault(normalize(label), (line, dest))
    # Pair brackets with a stack so nested labels require no recursive parser.
    html_token = re.compile(r"</?[A-Za-z][A-Za-z0-9-]*(?:\s+(?:[^<>\"']|\"[^\"]*\"|'[^']*')*)?\s*/?>")
    pairs, stack, pos = {}, [], 0
    while pos < len(text):
        if text[pos] == '\\':
            pos += 2
            continue
        if text[pos] == '<' and (token := html_token.match(text, pos)):
            pos = token.end()
            continue
        if text[pos] == '[':
            stack.append(pos)
        elif text[pos] == ']' and stack:
            pairs[stack.pop()] = pos
        pos += 1
    consumed, destination_ranges, linked_labels = -1, [], []
    for start, close in sorted(pairs.items()):
        if start < consumed or any(a <= start < b for a, b in destination_ranges):
            continue
        label, end = text[start + 1:close], close + 1
        if not label or re.search(r'\n[ \t]*\n', label):
            continue
        if text[end:end + 1] == '(':
            found = destination(text, end + 1)
            if found:
                tail = re.match(r'\s*(?:' + TITLE + r')?\s*\)', text[found[1]:])
                stop = found[1] + tail.end() if tail else end
                if tail and not re.search(r'\n[ \t]*\n', text[start:stop]):
                    yield text.count('\n', 0, start) + 1, found[0]
                    destination_ranges.append((end, stop))
                    linked_labels.append((start, close))
                    continue
        if text[start - 1:start] != '!' and any(a < start < b for a, b in linked_labels):
            continue
        reference = pairs.get(end)
        if reference is not None:
            used.add(normalize(text[end + 1:reference] or label))
            consumed = reference + 1
        else:
            used.add(normalize(label))
    for name, value in definitions.items():
        if name in used:
            yield value


def link_problems(cfg):
    """Check local file links in whole routed sources and wiki Markdown pages."""
    paths = {s['path'].replace('\\', '/') for t in cfg['topics'].values() for s in t['sources']}
    wiki = cfg.get('wikiDir', 'wiki')
    paths.add(cfg.get('routerFile', f'{wiki}/README.md'))
    pending = [(os.path.join(ROOT, wiki), frozenset())]
    while pending:
        directory, ancestors = pending.pop()
        canonical = os.path.realpath(directory)
        if canonical in ancestors or not (canonical == ROOT or canonical.startswith(ROOT + os.sep)):
            continue
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.is_dir():
                        pending.append((entry.path, ancestors | {canonical}))
                    elif entry.name.endswith('.md'):
                        paths.add(os.path.relpath(entry.path, ROOT))
        except OSError:
            continue
    bad = []
    for path in sorted({os.path.abspath(os.path.join(ROOT, p)) for p in paths}):
        rel = os.path.relpath(path, ROOT)
        canonical = os.path.realpath(path)
        if not canonical.startswith(ROOT + os.sep) or not os.path.isfile(path):
            continue  # Rendering retains ownership of invalid source diagnostics.
        try:
            with open(path, encoding='utf-8') as source:
                lines = source.read().split('\n')
        except (ValueError, OSError) as error:
            bad.append(f'{rel}: {error}')
            continue
        for line, raw in link_destinations(lines):
            dest = unescape(markdown_unescape(raw))
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
