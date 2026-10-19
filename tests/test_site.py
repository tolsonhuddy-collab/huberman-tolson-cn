"""Static site behavior and publication-boundary tests; no network or packages."""
import importlib.util
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from urllib.parse import urlsplit

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_site", PROJECT / "scripts/build_site.py")
site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site)


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.ids, self.links, self.images = set(), [], []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "a" and "href" in attrs:
            self.links.append(attrs["href"])
        if tag == "img":
            self.images.append(attrs["src"])


class SiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        shutil.copytree(PROJECT / "web", self.root / "web")
        for directory in ("catalog", "private/articles", "private/metadata"):
            (self.root / directory).mkdir(parents=True, exist_ok=True)

    def write_json(self, path, data):
        (self.root / path).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def inputs(self, source_a="https://www.youtube.com/watch?v=episode-A", source_b="https://www.youtube.com/watch?v=episode-B"):
        episodes = [
            {"id": "episode-a", "title_en": "Title A", "kind": "long_episode", "guest_series": True},
            {"id": "episode-b", "title_en": "Title B", "kind": "long_episode"},
            {"id": "episode-excerpt", "title_en": "An AMA excerpt", "kind": "ama", "explicit_excerpt": True},
            {"id": "episode-essentials", "title_en": "An Essentials episode", "kind": "essentials"},
            {"id": "episode-live", "title_en": "Live Q and A", "kind": "live_qa"},
        ]
        self.write_json("catalog/episodes.json", {"schema_version": 1, "episodes": episodes})
        self.write_json("private/progress.json", {"episodes": {"episode-a": {"status": "draft_complete"}, "episode-b": {"status": "reviewed"}}})
        for suffix, source, sec in (("a", source_a, 15), ("b", source_b, 3661)):
            episode_id = "episode-" + suffix
            md = f"# 中文标题 {suffix}\n\n引言 {suffix}。\n\n## 起点 {suffix}\n\n正文前半。\n\n## 终点 {suffix}\n\n正文后半。\n"
            (self.root / "private/articles" / (episode_id + ".md")).write_text(md, encoding="utf-8")
            self.write_json("private/metadata/" + episode_id + ".json", {"id": episode_id, "title_zh": "中文标题 " + suffix, "source_url": source,
                "hosts": [{"name": "人物 " + suffix, "role": "访谈者", "bio": "人物简介"}],
                "sections": [{"title": "起点 " + suffix, "source_seconds": sec}, {"title": "终点 " + suffix, "source_seconds": None}],
                "editor_note": "仅作测试。"})
        return episodes

    def private_build(self):
        return site.build_site(self.root, Path("private/site"), private=True)

    def test_two_episodes_keep_independent_titles_sources_and_timestamps(self):
        self.inputs()
        manifest = self.private_build()
        a = (self.root / "private/site/episodes/episode-a.html").read_text()
        b = (self.root / "private/site/episodes/episode-b.html").read_text()
        self.assertIn("中文标题 a", a)
        self.assertIn("episode-A&amp;t=15", a)
        self.assertNotIn("episode-B", a)
        self.assertIn("episode-B&amp;t=3661", b)
        self.assertIn("1:01:01", b)
        self.assertNotIn("episode-A", b)
        self.assertEqual(manifest["article_count"], 2)

    def test_unknown_source_has_no_fabricated_video_link(self):
        self.inputs(None, "javascript:alert(1)")
        self.private_build()
        for suffix in ("a", "b"):
            html = (self.root / f"private/site/episodes/episode-{suffix}.html").read_text()
            self.assertNotIn("youtube.com", html)
            self.assertNotIn("javascript:", html)
            self.assertIn("原稿时间", html)
            self.assertIn("链接尚未核验", html)

    def test_non_youtube_source_does_not_invent_time_query(self):
        self.inputs("https://example.org/source", None)
        self.private_build()
        html = (self.root / "private/site/episodes/episode-a.html").read_text()
        self.assertIn('href="https://example.org/source"', html)
        self.assertNotIn("source?t=", html)
        self.assertIn("原稿时间 00:15", html)

    def test_frontmatter_is_not_rendered(self):
        self.inputs()
        path = self.root / "private/articles/episode-a.md"
        path.write_text("---\nsource: /private/DO-NOT-RENDER/file.txt\nauthor: metadata\n---\n" + path.read_text())
        self.private_build()
        html = (self.root / "private/site/episodes/episode-a.html").read_text()
        self.assertNotIn("DO-NOT-RENDER", html)
        self.assertNotIn("author: metadata", html)
        self.assertIn("引言 a", html)
        with self.assertRaisesRegex(ValueError, "Unclosed"):
            site.parse_article("---\nprivate: yes\n# Title\n## Body\nText")

    def test_demo_never_reads_private_catalog_handoff_or_full_text(self):
        self.inputs()
        (self.root / "private/articles/episode-a.md").write_text("SECRET-FULL-TRANSCRIPT <script>alert(1)</script>")
        (self.root / "catalog/episodes.json").write_text("not JSON: demo must not open this")
        (self.root / "private/handoff").mkdir()
        (self.root / "private/handoff/private.html").write_text("SECRET-HANDOFF")
        site.build_site(self.root, Path("dist"))
        files = list((self.root / "dist").rglob("*"))
        contents = "\n".join(path.read_text() for path in files if path.is_file())
        self.assertNotIn("SECRET-", contents)
        self.assertNotIn("Title A", contents)
        self.assertNotIn("episode-a.html", contents)
        self.assertFalse(any(path.suffix.lower() in {".jpg", ".png", ".webp"} for path in files))
        self.assertIn("虚构", contents)

    def test_private_output_and_input_symlinks_cannot_escape(self):
        self.inputs()
        for out in (Path("dist"), Path("../outside"), Path("private/../dist"), Path("private"), Path("private/articles")):
            with self.subTest(out=out), self.assertRaises(ValueError):
                site.build_site(self.root, out, private=True)
        outside = self.root / "outside.txt"
        outside.write_text("must not read")
        article = self.root / "private/articles/episode-a.md"
        article.unlink()
        article.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "outside private"):
            self.private_build()

    def test_demo_cannot_overwrite_code_or_private_inputs(self):
        for out in (Path("web"), Path("private/site"), Path("..")):
            with self.subTest(out=out), self.assertRaises(ValueError):
                site.build_site(self.root, out)
        (self.root / "dist").mkdir()
        (self.root / "dist/owner-file.txt").write_text("keep")
        with self.assertRaisesRegex(ValueError, "Refusing to overwrite"):
            site.build_site(self.root, Path("dist"))
        self.assertEqual((self.root / "dist/owner-file.txt").read_text(), "keep")

    def test_all_article_toc_anchors_and_local_resources_resolve(self):
        self.inputs()
        self.private_build()
        output = self.root / "private/site"
        for page in output.rglob("*.html"):
            parsed = Links(page.read_text())
            for href in parsed.links:
                parts = urlsplit(href)
                if parts.scheme:
                    continue
                target = page.parent / parts.path if parts.path else page
                self.assertTrue(target.is_file(), (page, href))
                if parts.fragment:
                    self.assertIn(parts.fragment, Links(target.read_text()).ids, (page, href))
            for src in parsed.images:
                self.assertTrue((page.parent / src).is_file(), (page, src))

    def test_html_and_url_values_are_escaped(self):
        self.inputs()
        path = self.root / "private/articles/episode-a.md"
        path.write_text('# <img src=x onerror=alert(1)>\n\n## 起点 a\n\n<script>alert(1)</script> **加粗** [安全](https://example.org/?a=1&b=2) [危险](javascript:alert)\n\n## 终点 a\n\n尾段。')
        meta_path = self.root / "private/metadata/episode-a.json"
        meta = json.loads(meta_path.read_text())
        meta["title_zh"] = '<img src=x onerror=alert(1)>'
        meta["hosts"][0]["name"] = '\"><script>alert(2)</script>'
        meta_path.write_text(json.dumps(meta))
        self.private_build()
        html = (self.root / "private/site/episodes/episode-a.html").read_text()
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<img src=x", html)
        self.assertNotIn('href="javascript:', html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("<strong>加粗</strong>", html)
        self.assertIn('href="https://example.org/?a=1&amp;b=2"', html)

    def test_section_mismatch_and_invalid_timestamp_fail_without_replacing_good_build(self):
        self.inputs()
        self.private_build()
        output = self.root / "private/site/episodes/episode-a.html"
        before = output.read_text()
        path = self.root / "private/metadata/episode-a.json"
        meta = json.loads(path.read_text())
        meta["sections"][0]["title"] = "Wrong chapter"
        path.write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError, "must match"):
            self.private_build()
        self.assertEqual(output.read_text(), before)
        meta["sections"][0] = {"title": "起点 a", "source_seconds": -10}
        path.write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            self.private_build()

    def test_directory_marks_categories_excerpts_and_incomplete_items(self):
        self.inputs()
        self.private_build()
        html = (self.root / "private/site/index.html").read_text()
        self.assertIn("仅节选", html)
        self.assertIn("Essentials", html)
        self.assertIn("现场问答", html)
        self.assertIn("Guest Series", html)
        self.assertIn('href="episodes/episode-a.html"', html)
        self.assertNotIn('href="episodes/episode-excerpt.html"', html)
        self.assertIn("完整初稿 · 待审核", html)

    def test_drafting_and_missing_articles_are_not_linked(self):
        self.inputs()
        self.write_json("private/progress.json", {"episodes": {"episode-a": {"status": "drafting"}, "episode-b": {"status": "reviewed"}}})
        (self.root / "private/articles/episode-b.md").unlink()
        manifest = self.private_build()
        html = (self.root / "private/site/index.html").read_text()
        self.assertEqual(manifest["article_count"], 0)
        self.assertNotIn('href="episodes/episode-a.html"', html)
        self.assertIn("稿件文件缺失", html)

    def test_numbered_headings_display_once_and_keep_raw_metadata_matching(self):
        self.inputs()
        article_path = self.root / "private/articles/episode-a.md"
        article_path.write_text(article_path.read_text().replace("## 起点 a", "## 01 起点 a").replace("## 终点 a", "## 二、终点 a"))
        meta_path = self.root / "private/metadata/episode-a.json"
        meta = json.loads(meta_path.read_text())
        meta["sections"][0]["title"] = "01 起点 a"
        meta["sections"][1]["title"] = "二、终点 a"
        meta_path.write_text(json.dumps(meta))
        self.private_build()
        html = (self.root / "private/site/episodes/episode-a.html").read_text()
        self.assertIn('<a href="#section-1"><span>01</span>起点 a</a>', html)
        self.assertIn('<a href="#section-1">01 起点 a</a>', html)
        self.assertIn('<a href="#section-2">02 终点 a</a>', html)
        self.assertIn('<h2>起点 a</h2>', html)
        self.assertNotIn('01 01 起点 a', html)
        self.assertNotIn('二、终点 a', html)
        self.assertEqual(site.display_section_title("24 小时的节律", 1), "24 小时的节律")
        meta["sections"][0]["title"] = "起点 a"
        meta_path.write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError, "must match"):
            self.private_build()

    def test_readable_articles_come_first_and_numbers_mean_directory_positions(self):
        episodes = self.inputs()
        reordered = [episodes[2], episodes[0], episodes[4], episodes[1], episodes[3]]
        self.write_json("catalog/episodes.json", {"episodes": reordered})
        self.private_build()
        html = (self.root / "private/site/index.html").read_text()
        self.assertLess(html.index('href="episodes/episode-a.html"'), html.index('href="episodes/episode-b.html"'))
        self.assertLess(html.index('href="episodes/episode-b.html"'), html.index('An AMA excerpt'))
        self.assertIn('title="目录顺序 1；不是原节目期号"', html)
        self.assertIn('aria-label="目录顺序 1">001</span>', html)
        self.assertIn("左侧数字仅为目录顺序", html)
        self.assertIn("完整初稿 · 待审核", html)
        original = json.loads((self.root / "catalog/episodes.json").read_text())["episodes"]
        self.assertEqual([ep["id"] for ep in original], [ep["id"] for ep in reordered])

    def test_unsafe_and_duplicate_episode_ids_are_rejected(self):
        for ids in (("../escape",), ("same", "same")):
            self.write_json("catalog/episodes.json", {"episodes": [{"id": value, "kind": "long_episode"} for value in ids]})
            self.write_json("private/progress.json", {"episodes": {}})
            with self.subTest(ids=ids), self.assertRaisesRegex(ValueError, "safe slugs"):
                self.private_build()

    def test_safe_url_rejects_unsafe_schemes_credentials_and_controls(self):
        for value in ("javascript:alert(1)", "data:text/html,hello", "file:///etc/passwd", "//example.org", "https://user:pass@example.org/", "https://example.org/\nnext", " https://example.org", "https://example.org\\x", "https://example.org:wrong/"):
            self.assertIsNone(site.safe_url(value), value)
        self.assertEqual(site.safe_url("https://example.org/?x=1&y=2"), "https://example.org/?x=1&y=2")

    def test_private_portraits_are_local_and_never_copy_svg(self):
        self.inputs()
        path = self.root / "private/metadata/episode-a.json"
        meta = json.loads(path.read_text())
        meta["hosts"][0]["portrait"] = "web/portrait-placeholder.svg"
        path.write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError, "outside private"):
            self.private_build()
        meta["hosts"][0]["portrait"] = "private/portrait.svg"
        (self.root / "private/portrait.svg").write_text("<svg/>")
        path.write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError, "JPG, PNG, or WebP"):
            self.private_build()
        meta["hosts"][0]["portrait"] = "private/portrait.jpg"
        (self.root / "private/portrait.jpg").write_bytes(b"fixture-jpg")
        path.write_text(json.dumps(meta))
        self.private_build()
        self.assertEqual((self.root / "private/site/portraits/episode-a-0.jpg").read_bytes(), b"fixture-jpg")
        self.assertIn('src="portraits/episode-a-0.jpg"', (self.root / "private/site/index.html").read_text())

    @unittest.skipUnless(shutil.which("node"), "Node is optional; Python build has no JS runtime dependency")
    def test_reader_script_runs_on_homepage_without_reader_controls(self):
        stub = "global.document={documentElement:{dataset:{},style:{setProperty(){}},scrollHeight:800},getElementById(){return null},querySelectorAll(){return []}};global.window={innerHeight:800,scrollY:0,addEventListener(){}};global.requestAnimationFrame=f=>f();"
        script = stub + (PROJECT / "web/app.js").read_text()
        result = subprocess.run([shutil.which("node"), "-e", script], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which("node"), "Node is optional; Python build has no JS runtime dependency")
    def test_directory_search_combines_category_and_reading_state(self):
        stub = """
const assert=require('node:assert/strict');
const control=(value)=>({value,listeners:{},addEventListener(k,f){this.listeners[k]=f;}});
const nodes={'episode-search':control(''),'kind-filter':control('all'),'status-filter':control('all'),'result-count':{},'no-results':{}};
const cards=[{dataset:{search:'sleep article',kind:'long_episode',availability:'readable'}},{dataset:{search:'ama excerpt',kind:'ama',availability:'pending'}}];
global.document={documentElement:{dataset:{},style:{setProperty(){}},scrollHeight:800},getElementById(k){return nodes[k]||null;},querySelectorAll(s){return s==='.episode-card'?cards:[];}};
global.window={innerHeight:800,scrollY:0,addEventListener(){}};global.requestAnimationFrame=f=>f();
"""
        checks = """
assert.equal(cards.filter(x=>!x.hidden).length,2);
nodes['kind-filter'].value='ama';nodes['kind-filter'].listeners.input();
assert.deepEqual(cards.map(x=>x.hidden),[true,false]);
nodes['episode-search'].value='sleep';nodes['episode-search'].listeners.input();
assert.equal(nodes['no-results'].hidden,false);
nodes['kind-filter'].value='all';nodes['status-filter'].value='readable';nodes['status-filter'].listeners.input();
assert.deepEqual(cards.map(x=>x.hidden),[false,true]);
assert.equal(nodes['result-count'].textContent,'显示 1 / 2 期');
"""
        script = stub + (PROJECT / "web/app.js").read_text() + checks
        result = subprocess.run([shutil.which("node"), "-e", script], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
