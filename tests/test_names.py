"""Guard current reader-facing names without reading private editorial history.

Only the listed Huberman spellings are rejected. Source quotations in Markdown
quote blocks or HTML blockquotes, code, URLs, filenames and English-title fields
are outside this check; ordinary inline quotation marks do not hide prose.
"""
import ast
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unittest


PROJECT = Path(__file__).resolve().parents[1]
NONSTANDARD_NAMES = (
    "\u80e1\u4f2f\u66fc", "\u80e1\u535a\u66fc", "\u80e1\u67cf\u66fc",
    "\u4f11\u535a\u66fc", "\u4f11\u67cf\u66fc", "\u4fee\u4f2f\u66fc",
    "\u8bb8\u4f2f\u66fc", "\u8a31\u4f2f\u66fc",
)
NONSTANDARD = re.compile("|".join(map(re.escape, NONSTANDARD_NAMES)))
URL = re.compile(r"https?://[^\s<>\"'，。；：！？（）]+", re.IGNORECASE)
FILENAME = re.compile(
    r"[^\s<>\"'，。；：！？（）]+\.(?:md|json|html|xml|opml|py|js|css|svg|png|jpe?g|webp|rtf|txt|vtt)\b",
    re.IGNORECASE,
)


class VisibleHTML(HTMLParser):
    """Collect visible text and accessibility labels, never link destinations."""

    ignored = {"script", "style", "pre", "code", "blockquote"}
    labels = {"alt", "title", "aria-label", "placeholder"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        if self.hidden or tag in self.ignored:
            if tag in self.ignored:
                self.hidden.append(tag)
            return
        attributes = dict(attrs)
        for key in self.labels:
            if attributes.get(key):
                self.text.append(attributes[key])
        if tag == "meta" and (
            attributes.get("name") == "description"
            or attributes.get("property") in {"og:title", "og:description"}
        ):
            self.text.append(attributes.get("content", ""))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.hidden and tag == self.hidden[-1]:
            self.hidden.pop()

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)


def reader_text(text):
    """Mask non-prose Markdown constructs, then collect HTML display text."""
    lines = []
    fence = None
    quoted = False
    for line in text.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence:
            if re.fullmatch(r" {0,3}" + re.escape(fence[0]) + "{" + str(fence[1]) + r",}\s*", line):
                fence = None
            continue
        if marker:
            fence = (marker[1][0], len(marker[1]))
            continue
        if re.match(r"^ {0,3}>", line):
            quoted = True
            continue
        if quoted and line.strip():
            continue  # CommonMark permits lazy continuation of a quote block.
        quoted = False
        if re.match(r"^(?: {4}|\t)", line):
            continue
        if re.match(r"^ {0,3}\[[^\]]+\]:\s*\S", line):
            continue
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"(`+).*?\1", "", text)
    text = re.sub(r"(!?\[[^\]\n]*\])\([^\n)]*\)", r"\1", text)
    parser = VisibleHTML()
    parser.feed(text)
    parser.close()
    return FILENAME.sub("", URL.sub("", "\n".join(parser.text)))


def display_fields(metadata):
    """Whitelist public display fields; source IDs/paths/English titles stay raw."""
    for key in ("title_zh", "dek", "homepage_dek", "editor_note", "source_intro"):
        if isinstance(metadata.get(key), str):
            yield key, metadata[key]
    for index, host in enumerate(metadata.get("hosts", [])):
        for key in ("name", "role", "bio", "portrait_credit"):
            if isinstance(host.get(key), str):
                yield f"hosts[{index}].{key}", host[key]
    for index, section in enumerate(metadata.get("sections", [])):
        if isinstance(section.get("title"), str):
            yield f"sections[{index}].title", section["title"]


class NameTests(unittest.TestCase):
    def assert_standard(self, text, location):
        found = NONSTANDARD.search(reader_text(text))
        self.assertIsNone(found, f"{location}: use 休伯曼 for Andrew Huberman; found {found[0] if found else ''}")

    def test_published_markdown_names(self):
        paths = sorted((PROJECT / "site/zh").rglob("*.md"))
        self.assertTrue(paths, "No current public manuscripts were checked")
        for path in paths:
            with self.subTest(path=path.relative_to(PROJECT)):
                self.assert_standard(path.read_text(encoding="utf-8"), path)

    def test_public_metadata_display_names(self):
        paths = sorted((PROJECT / "site/zh").rglob("*.json"))
        self.assertTrue(paths, "No current public metadata were checked")
        for path in paths:
            metadata = json.loads(path.read_text(encoding="utf-8"))
            for field, text in display_fields(metadata):
                with self.subTest(path=path.relative_to(PROJECT), field=field):
                    self.assert_standard(text, f"{path}:{field}")
        catalog = json.loads((PROJECT / "catalog/episodes.json").read_text(encoding="utf-8"))
        for episode in catalog["episodes"]:
            for field, text in display_fields(episode):
                self.assert_standard(text, f"catalog:{episode['id']}:{field}")

    def test_readme_templates_and_about_copy_names(self):
        for path in (PROJECT / "README.md", PROJECT / "README.en.md", *sorted((PROJECT / "web").glob("*.html"))):
            with self.subTest(path=path.relative_to(PROJECT)):
                self.assert_standard(path.read_text(encoding="utf-8"), path)
        # Read the about/article display literals without importing the builder,
        # Pillow, runtime fonts, or any private inputs.
        path = PROJECT / "scripts/build_site.py"
        module = ast.parse(path.read_text(encoding="utf-8"))
        functions = {node.name: node for node in module.body if isinstance(node, ast.FunctionDef)}
        for name in ("render_catalog", "render_article", "speakers_html"):
            self.assertIn(name, functions)
            for node in ast.walk(functions[name]):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    self.assert_standard(node.value, f"{path}:{node.lineno}")

    def test_other_researchers_keep_their_names(self):
        path = PROJECT / "site/zh/ep-1278bde47f01"
        article = path.with_suffix(".md").read_text(encoding="utf-8")
        metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        self.assertIn("马克·伯曼（Marc Berman）", article)
        self.assertIn("伯曼研究的出发点", article)
        self.assertIn("马克·伯曼", metadata["title_zh"])
        guest = next(host for host in metadata["hosts"] if host["name"] == "Marc Berman")
        self.assertIn("马克·伯曼", guest["bio"])
        self.assertIn("利伯曼实验室", (PROJECT / "site/zh/ep-043a8da8dd27.md").read_text(encoding="utf-8"))
        self.assertIn("丹尼尔·利伯曼（Daniel Lieberman）", (PROJECT / "site/zh/ep-da74d87f9f47.md").read_text(encoding="utf-8"))

    def test_regressions_in_prose_headings_and_labels_are_detected(self):
        for name in NONSTANDARD_NAMES:
            for text in (f"{name}提出问题。", f"# {name}\n\n## {name}的回答", f"“{name}”", f"[{name}](https://example.org/)", f'<img src="portrait.jpg" alt="{name}">'):
                with self.subTest(name=name, text=text):
                    self.assertIsNotNone(NONSTANDARD.search(reader_text(text)))

    def test_original_quotes_code_urls_and_filenames_are_exempt(self):
        name = NONSTANDARD_NAMES[0]
        examples = (
            f"> 原文引文：{name}\n后续引文\n\n休伯曼的正文。",
            f"```text\n{name}\n```\n\n休伯曼。",
            f"~~~\n{name}\n~~~",
            f"    {name}\n\n休伯曼。",
            f"`{name}` 与 ``{name}`code``",
            f"[官方页面](https://example.org/{name})",
            f"https://example.org/{name}",
            f"旧文件：{name}.md",
            f'<blockquote cite="https://example.org/">{name}</blockquote>',
            f'<a href="https://example.org/{name}">官方节目</a><code>{name}</code>',
        )
        for text in examples:
            with self.subTest(text=text):
                self.assertIsNone(NONSTANDARD.search(reader_text(text)))

    def test_metadata_excludes_english_titles_and_source_identifiers(self):
        name = NONSTANDARD_NAMES[0]
        metadata = {
            "title_zh": "休伯曼的访谈", "title_en": name,
            "source_url": f"https://example.org/{name}", "source_file": name + ".md",
            "hosts": [{"name": "Andrew Huberman", "bio": "安德鲁·休伯曼"}],
            "sections": [{"title": "休伯曼的提问", "source_seconds": 10}],
        }
        self.assertEqual({field for field, _ in display_fields(metadata)}, {"title_zh", "hosts[0].name", "hosts[0].bio", "sections[0].title"})
        for field, text in display_fields(metadata):
            self.assert_standard(text, field)


if __name__ == "__main__":
    unittest.main()
