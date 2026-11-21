"""List falls back to a routed page's closed frontmatter description."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from fixture_helpers import run_router, write_fixture

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/ai-context.py'
sys.dont_write_bytecode = True


class PageDescriptionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'project'
        self.script = self.root / 'scripts/ai-context.py'
        self.script.parent.mkdir(parents=True)
        shutil.copy2(SCRIPT, self.script)
        write_fixture(self.root, 'AGENTS.md', '`guide`\n')
        write_fixture(self.root, 'wiki/README.md', '# Topics\n')
        self.topic = {'sources': [{'path': 'wiki/guide.md'}]}

    def configure(self):
        write_fixture(self.root, 'wiki/ai-context.json', json.dumps({'topics': {'guide': self.topic}}))

    def assert_list(self, description):
        self.configure()
        result = run_router(self.script, 'list')
        self.assertEqual((result.returncode, result.stderr, result.stdout),
                         (0, '', f'{"guide":18} {description}\n'))

    def test_page_description_and_config_precedence(self):
        write_fixture(self.root, 'wiki/guide.md', '---\ntitle: T\ndescription: How to bisect.\n---\n')
        self.assert_list('How to bisect.')
        for description in ('Configured', ''):
            with self.subTest(description=description):
                self.topic['description'] = description
                self.assert_list(description)

    def test_first_source_with_heading_and_later_source_ignored(self):
        self.topic['sources'][0]['heading'] = 'Section'
        self.topic['sources'].append({'path': 'wiki/second.md'})
        write_fixture(self.root, 'wiki/guide.md', '---\ndescription: First\n---\n# Section\n')
        write_fixture(self.root, 'wiki/second.md', '---\ndescription: Second\n---\n')
        self.assert_list('')
        write_fixture(self.root, 'wiki/guide.md', '# Section\n')
        self.assert_list('')

    def test_scalar_forms(self):
        for text, expected in [
                ("---\ndescription: 'It''s useful'\n---\n", "It's useful"),
                ('---\ndescription: "Double quoted"\n---\n', 'Double quoted'),
                ('\ufeff---\r\ndescription:\tUnicode café\r\n...\r\n', 'Unicode café'),
                ('---\ndescription: Value # comment\n---\n', 'Value')]:
            with self.subTest(text=text):
                write_fixture(self.root, 'wiki/guide.md', text)
                self.assert_list(expected)

    def test_plain_comment_and_hash(self):
        for scalar, expected in [('Value # comment', 'Value'), ('Value#part', 'Value#part')]:
            with self.subTest(scalar=scalar):
                write_fixture(self.root, 'wiki/guide.md', f'---\ndescription: {scalar}\n---\n')
                self.assert_list(expected)

    def test_quoted_trailing_comments(self):
        for scalar, expected in [("'It''s # useful' # note", "It's # useful"),
                                 ('"Quoted # value" # note', 'Quoted # value')]:
            with self.subTest(scalar=scalar):
                write_fixture(self.root, 'wiki/guide.md', f'---\ndescription: {scalar}\n---\n')
                self.assert_list(expected)

    def test_double_quoted_escapes(self):
        write_fixture(self.root, 'wiki/guide.md',
                      r'---' + '\n' + r'description: "Explain \"quoted\" caf\u00e9"' + '\n---\n')
        self.assert_list('Explain "quoted" café')

    def test_null_and_indicator_values_are_rejected(self):
        for scalar in ['~', 'null', 'Null', '&anchor Text', '*alias', '!tag Text',
                       '- item', '? key', ': value', '@reserved', '`reserved', 'true', '123',
                       '0xFF', '0b10', '0o17', '.5', '2024-01-01']:
            with self.subTest(scalar=scalar):
                write_fixture(self.root, 'wiki/guide.md', f'---\ndescription: {scalar}\n---\n')
                self.assert_list('')

    def test_continued_scalar_is_rejected(self):
        for scalar in ['first line', '"first line', "'first line"]:
            with self.subTest(scalar=scalar):
                write_fixture(self.root, 'wiki/guide.md',
                              f'---\ndescription: {scalar}\n  second line\n---\n')
                self.assert_list('')

    def test_unclosed_or_invalid_quoted_scalar_is_rejected(self):
        for scalar in ['"unclosed', "'unclosed", '"value"extra', '"bad\\q"',
                       '"bad\\u12xz"', '"bad\\uD800"']:
            with self.subTest(scalar=scalar):
                write_fixture(self.root, 'wiki/guide.md', f'---\ndescription: {scalar}\n---\n')
                self.assert_list('')

    def test_missing_or_unsupported_description(self):
        for text in ['# No envelope\n', '---\ndescription: unclosed\n',
                     '---\ntitle: T\n---\n', '---\ndescription: >\n---\n',
                     '---\ndescription: |\n---\n', '---\ndescription: [a]\n---\n',
                     '---\ndescription: {a: b}\n---\n', '---\ndescription: \n---\n',
                     '---\n description: indented\n---\n',
                     '---\ntitle: T\n---\ndescription: body\n',
                     '\n---\ndescription: late\n---\n']:
            with self.subTest(text=text):
                write_fixture(self.root, 'wiki/guide.md', text)
                self.assert_list('')
        (self.root / 'wiki/guide.md').unlink()
        self.assert_list('')
        (self.root / 'wiki/guide.md').write_bytes(b'\xff')
        self.assert_list('')
        (self.root / 'wiki/guide.md').unlink()
        outside = Path(self.tmp.name) / 'outside.md'
        outside.write_text('---\ndescription: secret\n---\n', encoding='utf-8')
        try:
            (self.root / 'wiki/guide.md').symlink_to(outside)
        except (OSError, NotImplementedError) as error:
            self.skipTest('symlink capability unavailable: ' + str(error))
        self.assert_list('')
        self.topic['sources'] = []
        self.assert_list('')

    def test_check_accepts_missing_description(self):
        write_fixture(self.root, 'wiki/guide.md', '---\ndescription: A guide\n---\n# Guide\n')
        self.configure()
        result = run_router(self.script, 'check')
        self.assertEqual((result.returncode, result.stderr), (0, ''), result.stdout)


if __name__ == '__main__':
    unittest.main()
