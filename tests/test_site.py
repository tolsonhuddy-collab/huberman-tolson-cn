"""Static site behavior and publication-boundary tests; no network or packages."""
import importlib.util
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from urllib.parse import urljoin, urlsplit
from xml.etree import ElementTree as ET

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

    def test_reviewed_pages_hide_editorial_status_without_relaxing_draft_warnings(self):
        self.inputs()
        progress_path = self.root / "private/progress.json"
        before = progress_path.read_bytes()
        self.private_build()
        index = (self.root / "private/site/index.html").read_text()
        reviewed = (self.root / "private/site/episodes/episode-b.html").read_text()
        draft = (self.root / "private/site/episodes/episode-a.html").read_text()
        for html in (index, reviewed):
            self.assertNotIn("已审核", html)
            self.assertNotIn("已校读", html)
        self.assertIn("2 篇中文精读", index)
        reviewed_card = index.split('data-search="中文标题 b', 1)[1].split("</article>", 1)[0]
        self.assertNotIn('class="card-status', reviewed_card)
        self.assertNotIn('<span></span>', reviewed)
        self.assertIn('class="reading-status" aria-live="off"><span id="progress-label">', reviewed)
        self.assertIn("完整初稿 · 待审核", draft)
        self.assertIn("完整初稿 · 待审核", index)
        self.assertEqual(before, progress_path.read_bytes())

    def test_unknown_source_has_no_fabricated_video_link(self):
        self.inputs(None, "javascript:alert(1)")
        self.private_build()
        for suffix in ("a", "b"):
            html = (self.root / f"private/site/episodes/episode-{suffix}.html").read_text()
            self.assertNotIn("youtube.com", html)
            self.assertNotIn("javascript:", html)
            self.assertIn('class="chapter-time"', html)
            self.assertIn("本地 VTT 定位，未独立核对原音", html)
            self.assertIn("链接尚未核验", html)

    def test_publication_copy_preserves_content_limits_and_frozen_inputs(self):
        self.inputs(source_b=None)
        meta_path = self.root / "private/metadata/episode-a.json"
        meta = json.loads(meta_path.read_text())
        meta["editor_note"] = "来源已核，原音偏移未核。研究仍有样本限制。当前为私有编辑稿，内容公开授权待确认。"
        portrait = self.root / "private/reference.jpg"
        portrait.write_bytes(b"synthetic portrait fixture")
        meta["hosts"][0].update(portrait="private/reference.jpg", portrait_credit="原样稿所载头像来自 Stanford Profiles；公开使用授权未核定")
        self.write_json("private/metadata/episode-a.json", meta)
        article_path = self.root / "private/articles/episode-a.md"
        before = (meta_path.read_bytes(), article_path.read_bytes())
        self.private_build()
        index = (self.root / "private/site/index.html").read_text()
        article = (self.root / "private/site/episodes/episode-a.html").read_text()
        self.assertIn("本站提供中文精读，未完成节目仅列目录。", index)
        self.assertIn("原节目及素材权利归各自权利人所有。", index)
        for stale in ["本地私有工作台", "仅供私有审阅", "未部署到公开网站", "尚未获准公开", "授权待确认", "公开使用授权未核定", "本地私有审阅"]:
            self.assertNotIn(stale, index + article)
        for kept in ["非官方阅读项目", "来源已核，原音偏移未核。研究仍有样本限制。", "不构成医疗建议", "正文与素材不属于 MIT 代码许可", "原始英文转写仅用于编校核对，未随本站发布。", "头像来源：Stanford Profiles；人物肖像不属于 MIT 代码许可", "正文前半。", "正文后半。", "episode-A&amp;t=15"]:
            self.assertIn(kept, article)
        self.assertIn("未独立核对原音", (self.root / "private/site/episodes/episode-b.html").read_text())
        self.assertNotIn("官方授权合作", index + article)
        self.assertEqual(before, (meta_path.read_bytes(), article_path.read_bytes()))
        site.build_site(self.root, Path("dist"), private=False)
        demo = (self.root / "dist/episodes/demo-reading.html").read_text()
        self.assertIn("原创虚构版式演示", demo)
        self.assertNotIn("Stanford Profiles", demo)

    def test_non_youtube_source_does_not_invent_time_query(self):
        self.inputs("https://example.org/source", None)
        self.private_build()
        html = (self.root / "private/site/episodes/episode-a.html").read_text()
        self.assertIn('href="https://example.org/source"', html)
        self.assertNotIn("source?t=", html)
        self.assertIn('>00:15</span>', html)

    def test_provenance_is_preserved_in_closed_footer_without_repeated_chapter_lines(self):
        self.inputs()
        path = self.root / "private/articles/episode-a.md"
        path.write_text("# 中文标题 a\n\n中文精读编号：内部编号。\n\n来源有2047条字幕，索引日期尚未核实。\n\n## 起点 a\n\n〔VTT 定位：00:00:15.000—00:00:20.000；主题另见00:00:01.000〕\n\n正文前半，保留条件。\n\n〔编辑注：00:00:17.000 的机制解释仍是假说。〕\n\n## 终点 a\n\n本地时间轴：00:00:20.000–00:00:30.000\n\n正文后半。")
        self.private_build()
        html = (self.root / "private/site/episodes/episode-a.html").read_text()
        reading = html.split('<article id="reading" class="reading-body">', 1)[1].split('</article>', 1)[0]
        before = html.split('<article id="reading"', 1)[0]
        footer = html.split('<details class="source-details"', 1)[1]
        self.assertNotIn("内部编号", before + reading)
        self.assertNotIn("2047条", before + reading)
        self.assertNotIn("〔VTT 定位", reading)
        self.assertNotIn("本地时间轴", reading)
        self.assertIn("正文前半，保留条件", reading)
        self.assertIn("机制解释仍是假说", reading)
        self.assertIn("内部编号", footer)
        self.assertIn("2047条", footer)
        self.assertIn("主题另见00:00:01.000", footer)
        self.assertIn("本地时间轴：00:00:20.000–00:00:30.000", footer)
        self.assertIn('id="editor-sources"><summary>', html)
        self.assertNotIn('id="editor-sources" open', html)

    def test_catalog_portrait_alt_names_only_the_person_shown(self):
        self.inputs()
        path = self.root / "private/metadata/episode-a.json"
        meta = json.loads(path.read_text())
        meta["hosts"] = [{"name": "Andrew Huberman", "role": "主持人", "portrait": "private/host.jpg"}, {"name": "Guest Scientist", "role": "嘉宾"}]
        path.write_text(json.dumps(meta))
        (self.root / "private/host.jpg").write_bytes(b"fixture-host-photo")
        self.private_build()
        html = (self.root / "private/site/index.html").read_text()
        self.assertIn('alt="Andrew Huberman"', html)
        self.assertNotIn('alt="Andrew Huberman · Guest Scientist"', html)
        self.assertIn('class="card-people">Andrew Huberman · Guest Scientist</p>', html)
        self.assertIn('class="card-portrait-label">主持人</span>', html)

    def test_updated_source_intro_replaces_stale_footer_without_changing_prose(self):
        self.inputs()
        article = self.root / "private/articles/episode-a.md"
        article.write_text(article.read_text().replace("引言 a。", "旧来源说明：节目链接未知，由父任务待核。"))
        original = article.read_bytes()
        path = self.root / "private/metadata/episode-a.json"
        meta = json.loads(path.read_text())
        meta["source_intro"] = "节目来源已核实。时间来自本地 VTT，未独立核对原音。"
        path.write_text(json.dumps(meta))
        self.private_build()
        html = (self.root / "private/site/episodes/episode-a.html").read_text()
        footer = html.split('<details class="source-details"', 1)[1]
        reading = html.split('<article id="reading" class="reading-body">', 1)[1].split('</article>', 1)[0]
        self.assertIn(meta["source_intro"], footer)
        self.assertNotIn("父任务", html)
        self.assertNotIn("节目链接未知", html)
        self.assertIn("正文前半。", reading)
        self.assertIn("正文后半。", reading)
        self.assertEqual(article.read_bytes(), original)

    def test_source_intro_rejects_nontext_metadata(self):
        self.inputs()
        path = self.root / "private/metadata/episode-a.json"
        meta = json.loads(path.read_text())
        meta["source_intro"] = {"invalid": "nested"}
        path.write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError, "source_intro must be text"):
            self.private_build()

    def test_whitespace_only_blank_line_does_not_move_article_prose_into_footer(self):
        self.inputs()
        for blank in ("  ", "\t"):
            with self.subTest(blank=repr(blank)):
                path = self.root / "private/articles/episode-a.md"
                path.write_text("# 中文标题 a\n\n## 起点 a\n\n〔VTT 定位：00:00:15.000—00:00:20.000〕\n" + blank + "\n正文必须留在阅读区。\n\n〔编辑注：该机制仍是假说。〕\n\n## 终点 a\n\n结尾正文。")
                self.private_build()
                html = (self.root / "private/site/episodes/episode-a.html").read_text()
                reading = html.split('<article id="reading" class="reading-body">', 1)[1].split('</article>', 1)[0]
                footer = html.split('<details class="source-details"', 1)[1]
                self.assertIn("正文必须留在阅读区", reading)
                self.assertIn("该机制仍是假说", reading)
                self.assertNotIn("正文必须留在阅读区", footer)
                self.assertNotIn("〔VTT 定位", reading)

    def test_timestamp_paragraph_mixed_with_scientific_prose_stays_in_reading(self):
        self.inputs()
        for position in ("〔VTT 定位：00:00:15.000—00:00:20.000〕", "本地时间轴：00:00:15.000–00:00:20.000"):
            for separator in ("", "\n"):
                with self.subTest(position=position, separator=repr(separator)):
                    path = self.root / "private/articles/episode-a.md"
                    path.write_text("# 中文标题 a\n\n## 起点 a\n\n" + position + separator + "该机制仍是假说。\n\n正文。\n\n## 终点 a\n\n结尾。")
                    self.private_build()
                    html = (self.root / "private/site/episodes/episode-a.html").read_text()
                    reading = html.split('<article id="reading" class="reading-body">', 1)[1].split('</article>', 1)[0]
                    footer = html.split('<details class="source-details"', 1)[1]
                    self.assertIn("该机制仍是假说", reading)
                    self.assertNotIn("该机制仍是假说", footer)

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
        (self.root / "site/zh").mkdir(parents=True)
        (self.root / "site/zh/secret.md").write_text("SECRET-COMMITTED-ESSAY")
        site.build_site(self.root, Path("dist"))
        files = list((self.root / "dist").rglob("*"))
        contents = "\n".join(path.read_text(encoding="utf-8") for path in files if path.is_file() and path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"})
        self.assertNotIn("SECRET-", contents)
        self.assertNotIn("Title A", contents)
        self.assertNotIn("episode-a.html", contents)
        rasters = [path for path in files if path.suffix.lower() in {".jpg", ".png", ".webp"}]
        self.assertTrue(rasters)
        self.assertTrue(all(path.parent.name == "og" and path.suffix == ".jpg" for path in rasters))
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

    def test_hash_mismatch_downgrades_current_build_only_and_keeps_other_articles(self):
        for status in ("draft_complete", "reviewed"):
            with self.subTest(status=status):
                self.inputs()
                path_a = self.root / "private/articles/episode-a.md"
                path_b = self.root / "private/articles/episode-b.md"
                self.write_json("private/progress.json", {"episodes": {
                    "episode-a": {"status": status, "metrics": {"sha256": hashlib.sha256(path_a.read_bytes()).hexdigest()}},
                    "episode-b": {"status": "reviewed", "metrics": {"sha256": hashlib.sha256(path_b.read_bytes()).hexdigest()}},
                }})
                progress_path = self.root / "private/progress.json"
                original_progress = progress_path.read_bytes()
                path_a.write_text(path_a.read_text() + "\n稿件在记录状态后被修改。\n")
                _, progress, _, articles = site.read_private(self.root)
                self.assertEqual(progress["episode-a"]["status"], "needs_revision")
                self.assertEqual(progress["episode-b"]["status"], "reviewed")
                self.assertNotIn("episode-a", articles)
                self.assertIn("episode-b", articles)
                manifest = self.private_build()
                html = (self.root / "private/site/index.html").read_text()
                self.assertNotIn('href="episodes/episode-a.html"', html)
                self.assertFalse((self.root / "private/site/episodes/episode-a.html").exists())
                self.assertIn('href="episodes/episode-b.html"', html)
                self.assertIn("待修订", html)
                self.assertEqual(manifest["article_count"], 1)
                self.assertEqual(progress_path.read_bytes(), original_progress)

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

    def test_fullwidth_pipe_ordinals_display_once_without_mutating_inputs_or_prose(self):
        self.inputs()
        article_path = self.root / "private/articles/episode-a.md"
        meta_path = self.root / "private/metadata/episode-a.json"
        for separator in ("｜", "｜ "):
            with self.subTest(separator=separator):
                first, last = f"01{separator}起点 a", f"02{separator}终点 a"
                article_path.write_text(f"# 中文标题 a\n\n## {first}\n\n〔VTT 定位：00:00:15.000—00:00:20.000〕\n\n正文前半，结果仍是假说。\n\n## {last}\n\n正文后半。")
                meta = json.loads(meta_path.read_text())
                for section, title in zip(meta["sections"], (first, last)):
                    section["title"] = title
                meta_path.write_text(json.dumps(meta))
                frozen_article, frozen_meta = article_path.read_bytes(), meta_path.read_bytes()
                self.private_build()
                html = (self.root / "private/site/episodes/episode-a.html").read_text()
                self.assertIn('<a href="#section-1"><span>01</span>起点 a</a>', html)
                self.assertIn('<a href="#section-1">01 起点 a</a>', html)
                self.assertIn('<h2>起点 a</h2>', html)
                self.assertIn('<h3>01 起点 a</h3>', html)
                self.assertNotIn(first, html)
                self.assertNotIn(last, html)
                self.assertIn('正文前半，结果仍是假说。', html)
                self.assertIn('正文后半。', html)
                self.assertEqual(article_path.read_bytes(), frozen_article)
                self.assertEqual(meta_path.read_bytes(), frozen_meta)
        for title in ("24｜小时的节律", "1.5小时", "2026｜研究", "01｜"):
            self.assertEqual(site.display_section_title(title, 1), title)

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
        self.assertIn("编号仅为目录顺序", html)
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

    def set_cover(self, suffix, verified=True, path=None):
        metadata = self.root / f"private/metadata/episode-{suffix}.json"
        meta = json.loads(metadata.read_text())
        image = f"private/cover-{suffix}.jpg"
        (self.root / image).write_bytes(b"fixture-episode-cover")
        meta["cover"] = {"path": path or image, "verified": verified,
                         "source_url": "https://example.org/episode?a=1&b=2", "alt": 'Cover "title"'}
        meta["homepage_dek"] = '<script>Escaped editorial text</script>'
        metadata.write_text(json.dumps(meta))

    def test_verified_cover_and_reviewed_feature_preserve_safe_editorial_hierarchy(self):
        self.inputs()
        self.set_cover("a")
        self.set_cover("b")
        self.private_build()
        html = (self.root / "private/site/index.html").read_text()
        feature = html.split('<section id="front-story"', 1)[1].split('</section>', 1)[0]
        self.assertIn('covers/episode-b.jpg', feature)
        self.assertNotIn('covers/episode-a.jpg', feature)
        self.assertIn('href="episodes/episode-b.html"', feature)
        self.assertIn('&lt;script&gt;Escaped editorial text&lt;/script&gt;', feature)
        self.assertIn('https://example.org/episode?a=1&amp;b=2', feature)
        self.assertIn('alt="Cover &quot;title&quot;"', feature)
        self.assertIn('class="card-cover" href="episodes/episode-a.html"', html)
        self.assertEqual((self.root / "private/site/covers/episode-b.jpg").read_bytes(), b"fixture-episode-cover")
        self.assertLess(html.index('class="masthead-slogan"'), html.index('id="front-story"'))

    def test_unverified_cover_never_becomes_an_image_or_feature(self):
        self.inputs()
        self.set_cover("b", verified=False)
        self.private_build()
        html = (self.root / "private/site/index.html").read_text()
        self.assertNotIn('<section id="front-story"', html)
        self.assertNotIn('covers/episode-b.jpg', html)
        self.assertFalse((self.root / "private/site/covers").exists())
        self.assertIn('节目封面待核实', html)

    def test_unsafe_verified_cover_cannot_replace_a_good_build(self):
        self.inputs()
        self.private_build()
        good = (self.root / "private/site/index.html").read_bytes()
        for path, error in (("web/portrait-placeholder.svg", "outside private"), ("private/cover.svg", "local raster")):
            with self.subTest(path=path):
                (self.root / "private/cover.svg").write_text('<svg/>')
                self.set_cover("b", path=path)
                with self.assertRaisesRegex(ValueError, error):
                    self.private_build()
                self.assertEqual((self.root / "private/site/index.html").read_bytes(), good)

    @unittest.skipUnless(shutil.which("node"), "Node is optional; Python build has no JS runtime dependency")
    def test_reader_font_defaults_and_saved_preferences_survive_theme_update(self):
        fixture = r"""
const vm = require('vm'), fs = require('fs');
const script = fs.readFileSync(process.argv[1], 'utf8');
function run(saved, blocked = false) {
  const storage = {...saved}, styles = {}, elements = {};
  for (const id of ['font-down', 'font-up', 'font-label', 'theme-toggle'])
    elements[id] = {listeners: {}, attributes: {}, addEventListener(k, f) {this.listeners[k] = f}, setAttribute(k, v) {this.attributes[k] = v}};
  const root = {dataset: {}, style: {setProperty(k, v) {styles[k] = v}}, scrollHeight: 1000};
  vm.runInNewContext(script, {
    document: {documentElement: root, getElementById(id) {return elements[id] || null}, querySelectorAll() {return []}},
    window: {innerHeight: 800, scrollY: 0, addEventListener() {}}, requestAnimationFrame(f) {f()},
    localStorage: {getItem(k) {if (blocked) throw Error('unavailable'); return storage[k] ?? null}, setItem(k, v) {if (blocked) throw Error('unavailable'); storage[k] = v}}
  });
  const initial = {size: styles['--read-size'], label: elements['font-label'].value, theme: root.dataset.theme,
    downDisabled: !!elements['font-down'].disabled, upDisabled: !!elements['font-up'].disabled};
  elements['font-up'].listeners.click();
  const afterUp = styles['--read-size'];
  elements['font-down'].listeners.click();
  const afterDown = styles['--read-size'];
  for (let i = 0; i < 10; i++) elements['font-down'].listeners.click();
  const lower = {size: styles['--read-size'], disabled: elements['font-down'].disabled};
  for (let i = 0; i < 10; i++) elements['font-up'].listeners.click();
  return {initial, afterUp, afterDown, lower, upper: {size: styles['--read-size'], disabled: elements['font-up'].disabled}, storage};
}
process.stdout.write(JSON.stringify([
  run({}), run({'huberman-reading-size': '18', 'huberman-reading-theme': 'dark'}),
  run({'huberman-reading-size': '24'}), run({'huberman-reading-size': '16'}),
  run({'huberman-reading-size': 'invalid'}), run({}, true)
]));
"""
        result = subprocess.run([shutil.which("node"), "-e", fixture, str(PROJECT / "web/app.js")], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        cases = json.loads(result.stdout)
        self.assertEqual([c["initial"]["size"] for c in cases], ["20px", "18px", "24px", "16px", "20px", "20px"])
        self.assertEqual(cases[0]["initial"]["label"], "20")
        self.assertEqual(cases[1]["initial"]["theme"], "dark")
        self.assertEqual(cases[1]["storage"]["huberman-reading-theme"], "dark")
        self.assertEqual((cases[1]["afterUp"], cases[1]["afterDown"]), ("20px", "18px"))
        self.assertTrue(cases[2]["initial"]["upDisabled"])
        self.assertTrue(cases[3]["initial"]["downDisabled"])
        for case in cases:
            self.assertEqual(case["lower"], {"size": "16px", "disabled": True})
            self.assertEqual(case["upper"], {"size": "24px", "disabled": True})

    def test_reader_template_starts_at_twenty_with_shared_paper_palette(self):
        self.inputs()
        self.private_build()
        article = (self.root / "private/site/episodes/episode-b.html").read_text()
        self.assertIn('<output id="font-label" aria-live="polite">20</output>', article)
        css = (self.root / "private/site/style.css").read_text()
        self.assertIn('--paper:#f6f3ec;--ink:#272926;--body:#343833;', css)
        self.assertIn('--read-size:20px;', css)
        self.assertIn('::selection{background:var(--accent);color:var(--paper)}', css)

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
const nodes={'episode-search':control(''),'kind-filter':control('all'),'status-filter':control('all'),'result-count':{},'no-results':{},'front-story':{}};
const tabs=['all','readable','pending'].map(value=>({...control(value),dataset:{catalogStatus:value},setAttribute(k,v){this[k]=v;}}));
const cards=[{dataset:{search:'sleep article',kind:'long_episode',availability:'readable'}},{dataset:{search:'ama excerpt',kind:'ama',availability:'pending'}}];
global.document={documentElement:{dataset:{},style:{setProperty(){}},scrollHeight:800},getElementById(k){return nodes[k]||null;},querySelectorAll(s){return s==='.episode-card'?cards:s==='[data-catalog-status]'?tabs:[];}};
global.window={innerHeight:800,scrollY:0,addEventListener(){}};global.requestAnimationFrame=f=>f();
"""
        checks = """
assert.equal(cards.filter(x=>!x.hidden).length,2);
assert.equal(nodes['front-story'].hidden,false);
tabs[1].listeners.click();
assert.equal(nodes['status-filter'].value,'readable');
assert.equal(tabs[1]['aria-pressed'],'true');
assert.equal(nodes['front-story'].hidden,true);
tabs[0].listeners.click();
assert.equal(nodes['front-story'].hidden,false);
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

    def test_full_text_atom_feed_opml_and_relative_discovery(self):
        episodes, progress = [], {"episodes": {}}
        for number in range(21):
            episode_id = f"ep-{number:02d}"
            kind = "essentials" if number == 19 else "long_episode"
            episodes.append({"id": episode_id, "title_en": f"English {number}", "kind": kind})
            progress["episodes"][episode_id] = {"status": "reviewed", "updated_at": f"2024-01-{(number + 1):02d}T03:04:05Z"}
        episodes.append({"id": "ep-skip", "title_en": "Skipped revision", "kind": "ama"})
        progress["episodes"]["ep-00"]["updated_at"] = "2000-01-02T00:00:00Z"
        progress["episodes"]["ep-skip"] = {"status": "needs_revision", "updated_at": "2024-06-01T00:00:00Z"}
        self.write_json("catalog/episodes.json", {"episodes": episodes})
        self.write_json("private/progress.json", progress)
        for number in range(21):
            episode_id = f"ep-{number:02d}"
            title = "标题 & 二十 <未转义>" if number == 20 else f"标题 {number}"
            source = "https://example.org/episode-20" if number == 20 else None
            dek = "导语二十" if number == 20 else None
            body = "符号 A & B 以及 <tag>。" if number == 20 else f"后半正文 {number}。"
            (self.root / "private/articles" / f"{episode_id}.md").write_text(
                f"---\nsecret_path: /private/sources/{episode_id}.txt\n---\n# {title}\n\n〔VTT 定位：00:00:01.000—00:00:02.000〕\n\n## 前半 {number}\n\n前半正文 {number}。\n\n## 后半 {number}\n\n{body}\n",
                encoding="utf-8",
            )
            meta = {"id": episode_id, "title_zh": title, "source_url": source, "sections": [
                {"title": f"前半 {number}", "source_seconds": None}, {"title": f"后半 {number}", "source_seconds": None}]}
            if dek:
                meta["dek"] = dek
            self.write_json(f"private/metadata/{episode_id}.json", meta)
        (self.root / "private/articles/ep-skip.md").write_text("# 跳过\n\n## 一\n\n不应出现在订阅。\n", encoding="utf-8")
        self.write_json("private/metadata/ep-skip.json", {"id": "ep-skip", "title_zh": "跳过", "source_url": "https://example.org/skip",
            "sections": [{"title": "一", "source_seconds": None}]})
        manifest = self.private_build()
        readable_ids = [f"ep-{number:02d}" for number in range(20, -1, -1)]
        self.assertEqual(manifest["feed_entry_count"], len(readable_ids))
        atom = "{http://www.w3.org/2005/Atom}"
        root_feed = ET.parse(self.root / "private/site/feed.xml").getroot()
        podcast_feed = ET.parse(self.root / "private/site/podcasts/huberman/feed.xml").getroot()
        opml = ET.parse(self.root / "private/site/tolson-rss.opml")
        entries = root_feed.findall(f"{atom}entry")
        self.assertEqual(len(entries), len(readable_ids))
        self.assertEqual([entry.findtext(f"{atom}id").rsplit(":", 1)[-1] for entry in entries], readable_ids)
        self.assertEqual([entry.findtext(f"{atom}id") for entry in entries], [entry.findtext(f"{atom}id") for entry in podcast_feed.findall(f"{atom}entry")])
        newest = entries[0]
        self.assertEqual(newest.findtext(f"{atom}title"), "标题 & 二十 <未转义>")
        self.assertEqual(newest.findtext(f"{atom}id"), "tag:huberman-reading-001.tolsonhuddy.chatgpt.site,2026:episode:ep-20")
        self.assertEqual(newest.findtext(f"{atom}published"), "2024-01-21T03:04:05Z")
        self.assertEqual(newest.findtext(f"{atom}updated"), "2024-01-21T03:04:05Z")
        links = {(link.get("rel"), link.get("href"), link.get("title")) for link in newest.findall(f"{atom}link")}
        self.assertIn(("alternate", "https://huberman-reading-001.tolsonhuddy.chatgpt.site/episodes/ep-20.html", None), links)
        self.assertIn(("related", "https://example.org/episode-20", "原节目"), links)
        category = newest.find(f"{atom}category")
        self.assertEqual((category.get("term"), category.get("label")), ("long_episode", "长节目"))
        content = newest.find(f"{atom}content")
        self.assertEqual(content.get("type"), "html")
        self.assertIn("非官方精读，未获授权，版权归原作者", content.text)
        self.assertIn("导语二十", content.text)
        self.assertIn("前半正文 20。", content.text)
        self.assertIn("符号 A &amp; B 以及 &lt;tag&gt;。", content.text)
        self.assertNotIn("<tag>", content.text)
        self.assertIn('href="https://example.org/episode-20"', content.text)
        self.assertNotIn("VTT 定位", content.text)
        self.assertNotIn("secret_path", content.text)
        self.assertNotIn("<未转义>", content.text)
        raw = (self.root / "private/site/feed.xml").read_text(encoding="utf-8")
        self.assertNotIn("github.io", raw)
        self.assertNotIn("1970-01-01", raw)
        self.assertEqual(root_feed.findtext(f"{atom}updated"), "2024-01-21T03:04:05Z")
        self.assertIn(f'<img src="https://huberman-reading-001.tolsonhuddy.chatgpt.site/og/ep-20.jpg"', content.text)
        enclosure = next(link for link in newest.findall(f"{atom}link") if link.get("rel") == "enclosure")
        self.assertEqual(enclosure.get("href"), "https://huberman-reading-001.tolsonhuddy.chatgpt.site/og/ep-20.jpg")
        self.assertEqual(enclosure.get("type"), "image/jpeg")
        thumb = newest.find("{http://search.yahoo.com/mrss/}thumbnail")
        self.assertEqual((thumb.get("url"), thumb.get("width"), thumb.get("height")), ("https://huberman-reading-001.tolsonhuddy.chatgpt.site/og/ep-20.jpg", "1200", "630"))
        self.assertNotIn("不应出现在订阅", raw)
        self.assertIn("前半正文 0。", raw)
        essentials = next(entry for entry in entries if entry.findtext(f"{atom}id").endswith("ep-19"))
        self.assertEqual(essentials.find(f"{atom}category").get("label"), "Essentials")
        oldest = entries[-1]
        self.assertTrue(oldest.findtext(f"{atom}id").endswith("ep-00"))
        self.assertEqual(oldest.findtext(f"{atom}published"), "2000-01-02T00:00:00Z")
        bare = next(entry for entry in entries if entry.findtext(f"{atom}id").endswith("ep-01"))
        self.assertIsNone(next((link for link in bare.findall(f"{atom}link") if link.get("rel") == "related"), None))
        self.assertEqual(root_feed.find(f"{atom}link[@rel='self']").get("href"), "https://huberman-reading-001.tolsonhuddy.chatgpt.site/feed.xml")
        self.assertEqual(podcast_feed.find(f"{atom}link[@rel='self']").get("href"), "https://huberman-reading-001.tolsonhuddy.chatgpt.site/podcasts/huberman/feed.xml")
        listed = [node.get("xmlUrl") for node in opml.getroot().iter("outline") if node.get("xmlUrl")]
        self.assertEqual(listed, ["https://huberman-reading-001.tolsonhuddy.chatgpt.site/podcasts/huberman/feed.xml"])
        self.assertIn("Tolson-RSS", ET.tostring(opml.getroot(), encoding="unicode"))
        pages = "https://tolsonhuddy-collab.github.io/huberman-tolson-cn/"
        index = (self.root / "private/site/index.html").read_text(encoding="utf-8")
        article = (self.root / "private/site/episodes/ep-20.html").read_text(encoding="utf-8")
        self.assertIn('property="og:image" content="https://huberman-reading-001.tolsonhuddy.chatgpt.site/og/ep-20.jpg"', article)
        self.assertIn('name="twitter:image" content="https://huberman-reading-001.tolsonhuddy.chatgpt.site/og/ep-20.jpg"', article)
        self.assertIn('rel="alternate" type="application/atom+xml"', index)
        self.assertIn('href="feed.xml"', index)
        self.assertIn('href="../feed.xml"', article)
        self.assertEqual(urljoin(pages, "feed.xml"), pages + "feed.xml")
        self.assertEqual(urljoin(pages + "episodes/ep-20.html", "../feed.xml"), pages + "feed.xml")
        self.assertEqual(urljoin(pages + "episodes/ep-20.html", "../style.css"), pages + "style.css")
        self.assertNotRegex(index + article, r'(?:href|src)="/')
        site.build_site(self.root, Path("dist"), private=False)
        demo = ET.parse(self.root / "dist/feed.xml").getroot()
        demo_entry = demo.find(f"{atom}entry")
        self.assertIn("带着这个问题继续读", demo_entry.find(f"{atom}content").text)
        self.assertIn(site.RIGHTS_LINE, demo_entry.find(f"{atom}content").text)
        self.assertEqual(demo_entry.find(f"{atom}link[@rel='alternate']").get("href"), "https://huberman-reading-001.tolsonhuddy.chatgpt.site/episodes/demo-reading.html")
        self.assertTrue((self.root / "dist/podcasts/huberman/feed.xml").is_file())
        self.assertTrue((self.root / "dist/tolson-rss.opml").is_file())
        self.assertTrue((self.root / "dist/.nojekyll").is_file())

    def test_published_build_reads_site_zh_and_keeps_canonical_feed(self):
        self.write_json("catalog/episodes.json", {"episodes": [
            {"id": "essay-one", "title_en": "Sleep Essay", "kind": "long_episode"},
            {"id": "catalog-only", "title_en": "Not written", "kind": "ama"},
        ]})
        (self.root / "site/zh").mkdir(parents=True)
        (self.root / "site/zh/essay-one.md").write_text(
            "# 已发布标题\n\n导语写在这里。\n\n## 第一章\n\nCOMMITTED-ESSAY-BODY。\n", encoding="utf-8")
        self.write_json("site/zh/essay-one.json", {
            "id": "essay-one", "title_zh": "已发布标题", "title_en": "Sleep Essay",
            "source_url": "https://www.hubermanlab.com/episode/example",
            "hosts": [{"name": "讲述者", "role": "主持人", "bio": "简介"}],
            "sections": [{"title": "第一章", "source_seconds": 90}],
            "editor_note": "编辑说明。",
        })
        (self.root / "private/articles/secret.md").write_text("PRIVATE-TRANSCRIPT-SECRET", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "either"):
            site.build_site(self.root, Path("dist"), private=True, published=True)
        manifest = site.build_site(self.root, Path("dist"), published=True)
        self.assertEqual(manifest["mode"], "published")
        self.assertEqual(manifest["article_count"], 1)
        self.assertEqual(manifest["episode_count"], 2)
        self.assertEqual(manifest["feed_entry_count"], 1)
        page = (self.root / "dist/episodes/essay-one.html").read_text(encoding="utf-8")
        built = "\n".join(path.read_text(encoding="utf-8") for path in (self.root / "dist").rglob("*") if path.is_file() and path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"})
        self.assertIn("COMMITTED-ESSAY-BODY", page)
        self.assertIn("非官方阅读项目", page)
        self.assertNotIn("虚构版式演示", built)
        self.assertNotIn("PRIVATE-TRANSCRIPT-SECRET", built)
        self.assertFalse((self.root / "dist/episodes/catalog-only.html").exists())
        self.assertNotIn("github.io", built)
        self.assertIn(site.RIGHTS_LINE, (self.root / "dist/feed.xml").read_text(encoding="utf-8"))
        self.assertIn("https://huberman-reading-001.tolsonhuddy.chatgpt.site/episodes/essay-one.html", built)
        index = (self.root / "dist/index.html").read_text(encoding="utf-8")
        self.assertIn('href="feed.xml"', index)
        self.assertIn('href="../feed.xml"', page)
        self.assertNotRegex(index + page, r'(?:href|src)="/')
        pages = "https://tolsonhuddy-collab.github.io/huberman-tolson-cn/"
        self.assertEqual(urljoin(pages + "episodes/essay-one.html", "../style.css"), pages + "style.css")
        self.assertEqual(urljoin(pages + "episodes/essay-one.html", "../feed.xml"), pages + "feed.xml")

    def test_repository_commits_two_hundred_fifty_chinese_essays(self):
        files = [path for path in (PROJECT / "site/zh").iterdir() if path.is_file()]
        self.assertEqual(sorted(path.suffix for path in files), [".json"] * 250 + [".md"] * 250)
        stems = {}
        for path in files:
            stems.setdefault(path.suffix, set()).add(path.stem)
            self.assertFalse(path.is_symlink())
        self.assertEqual(stems[".md"], stems[".json"])
        catalog = json.loads((PROJECT / "catalog/episodes.json").read_text(encoding="utf-8"))
        ids = {episode["id"] for episode in catalog["episodes"]}
        self.assertEqual(len(stems[".md"]), 250)
        self.assertTrue(stems[".md"] <= ids)
        for path in files:
            if path.suffix != ".json":
                continue
            meta = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(meta.get("id"), path.stem)
            raw = path.read_text(encoding="utf-8")
            self.assertNotIn('"portrait"', raw)
            self.assertNotIn('"cover"', raw)
            published = site.parse_time(meta.get("published"))
            self.assertIsNotNone(published, path.name)
            self.assertGreaterEqual(published, site.DATE_FLOOR)

    def test_public_provider_paragraph_times_do_not_claim_vtt(self):
        ep = {"id": "provider-essay", "title_en": "Example", "timeline": {
            "provenance": "public_provider_paragraph_start_unverified_audio",
        }}
        meta = {"source_url": "https://www.hubermanlab.com/episode/example", "sections": [
            {"title": "第一章", "source_seconds": 90},
        ]}
        md = "# 标题\n\n导语。\n\n## 第一章\n\n正文。\n"
        html = site.reading_fragment(ep, meta, md)["article"]
        self.assertIn("第三方转写段落定位，未独立核对原音", html)
        self.assertNotIn("本地 VTT", html)
        ep["timeline"]["provenance"] = "local_vtt_unverified"
        self.assertIn("本地 VTT 定位", site.reading_fragment(ep, meta, md)["article"])

    def test_2026_full_episode_dates(self):
        dates = {
            "ep-48628f59d8cd": "2026-01-05T09:00:00Z",
            "ep-3b4e0847739b": "2026-01-12T09:00:00Z",
            "ep-a04a308f176e": "2026-05-11T08:00:00Z",
            "ep-1c02cb35c6f0": "2026-03-16T08:00:00Z",
            "ep-e0ae20af0cac": "2026-01-26T09:00:00Z",
            "ep-7cdb88401f4d": "2026-05-25T08:00:00Z",
            "ep-dfcc799b7f38": "2026-08-24T08:00:00Z",
            "ep-af5002cc73ad": "2026-04-20T08:00:00Z",
            "ep-a0877f413358": "2026-05-18T08:00:00Z",
            "ep-fddf3201b114": "2026-06-08T08:00:00Z",
            "ep-05cf82118130": "2026-02-16T09:00:00Z",
            "ep-a50f5894f167": "2026-10-12T08:00:00Z",
            "ep-18fe46070000": "2026-09-21T08:00:00Z",
            "ep-10bda8536ba0": "2026-09-14T08:00:00Z",
            "ep-623a28c789a8": "2026-07-20T08:00:00Z",
            "ep-2823b38717af": "2026-07-13T08:00:00Z",
            "ep-937d06db3239": "2026-09-07T08:00:00Z",
            "ep-c6ccfb8d2308": "2026-08-10T08:00:00Z",
            "ep-b09fb0581523": "2026-08-03T08:00:00Z",
            "ep-95f092e17bde": "2026-07-06T08:00:00Z",
            "ep-d7694e4dc7cc": "2026-06-29T08:00:00Z",
            "ep-5e65ae4c1d6a": "2026-06-22T08:00:00Z",
            "ep-e90d4f92ba4a": "2026-04-13T08:00:00Z",
            "ep-4933405f0f80": "2026-04-06T08:00:00Z",
            "ep-f1d7b06e8a45": "2026-03-02T09:00:00Z",
            "ep-9a3526498e8c": "2026-02-02T09:00:00Z",
            "ep-d54e8baf9adb": "2024-02-05T09:00:00Z",
            "ep-1a42f3290026": "2024-01-22T09:00:00Z",
            "ep-845bb0c607e0": "2024-01-15T09:00:00Z",
            "ep-073f298b1901": "2024-01-08T09:00:00Z",
            "ep-567f2ce95d72": "2024-01-01T09:00:00Z",
            "ep-786e15085096": "2023-12-25T09:00:00Z",
            "ep-c2f993b109d4": "2023-12-11T09:00:00Z",
            "ep-33e66a2ca68b": "2023-12-04T09:00:00Z",
            "ep-6f03c85f0bdf": "2023-11-27T09:00:00Z",
            "ep-9815b702187b": "2023-11-13T09:00:00Z",
            "ep-ec045612ab99": "2023-11-06T09:00:00Z",
            "ep-7aac3873675f": "2023-10-30T08:00:00Z",
            "ep-be4d02ffb3cf": "2023-10-23T08:00:00Z",
            "ep-194671570e35": "2023-10-16T08:00:00Z",
            "ep-05b5a52a5da0": "2023-10-02T08:00:00Z",
            "ep-1a0eb2d06b43": "2023-09-27T08:00:00Z",
            "ep-8cf739cd45a0": "2023-09-25T08:00:00Z",
            "ep-89728f69ea5b": "2023-09-20T08:00:00Z",
            "ep-dbfcb81c9266": "2023-09-13T08:00:00Z",
            "ep-0383d0fabcb2": "2023-09-11T08:00:00Z",
            "ep-ff408f4a91b5": "2024-05-01T08:00:00Z",
            "ep-963cf10a118c": "2024-04-22T08:00:00Z",
            "ep-9bb8d2fb0842": "2024-04-17T08:00:00Z",
            "ep-1d73a976adef": "2024-04-15T08:00:00Z",
            "ep-e8d4aea7810c": "2024-04-10T08:00:00Z",
            "ep-2dcad5dba0c9": "2024-04-08T08:00:00Z",
            "ep-ec7938012fae": "2024-04-03T08:00:00Z",
            "ep-3ecacc5a34c8": "2024-04-01T08:00:00Z",
            "ep-74c15ccb38f6": "2024-03-25T08:00:00Z",
            "ep-9d8c06d97a27": "2024-03-18T08:00:00Z",
            "ep-e1f4a8c51c0d": "2024-03-11T08:00:00Z",
            "ep-412248c8d814": "2024-03-04T09:00:00Z",
            "ep-5e7d624cae09": "2024-02-26T09:00:00Z",
            "ep-d08fc1aaeff7": "2024-02-19T09:00:00Z",
            "ep-9a04208f30fe": "2024-02-12T09:00:00Z",
            "ep-b85d5d8e4223": "2025-12-22T09:00:00Z",
            "ep-75fd5416b76c": "2025-12-01T09:00:00Z",
            "ep-593de98c0f26": "2024-09-23T08:00:00Z",
            "ep-d1302d2e6e79": "2024-07-15T08:00:00Z",
            "ep-917d7c64b0a8": "2024-07-08T08:00:00Z",
            "ep-9280564995e9": "2024-07-01T08:00:00Z",
            "ep-cc8f3950bc4a": "2024-06-24T08:00:00Z",
            "ep-4f0a86d606b8": "2024-06-17T08:00:00Z",
            "ep-c74add4ad00a": "2024-06-10T08:00:00Z",
            "ep-92600eda038f": "2024-06-03T08:00:00Z",
            "ep-4f582892b472": "2024-05-27T08:00:00Z",
            "ep-fd9b1d791b16": "2024-05-20T08:00:00Z",
            "ep-4e5d4059e6a8": "2024-05-13T08:00:00Z",
            "ep-3a66a20ae1ba": "2024-05-08T08:00:00Z",
            "ep-4f0efb6e199c": "2024-05-06T08:00:00Z",
            "ep-f07ea64d6d97": "2025-04-14T08:00:00Z",
            "ep-1406544acff5": "2025-02-10T09:00:00Z",
            "ep-6809fed77fec": "2025-01-20T09:00:00Z",
            "ep-aab0f3b5df76": "2024-12-30T09:00:00Z",
            "ep-849ef654bb39": "2024-12-23T09:00:00Z",
            "ep-73cc66774a58": "2024-12-16T09:00:00Z",
            "ep-3e58e758aa11": "2024-12-09T09:00:00Z",
            "ep-945a02368881": "2024-12-02T09:00:00Z",
            "ep-908db0d246de": "2024-11-25T09:00:00Z",
            "ep-b93daa0c3837": "2024-11-18T09:00:00Z",
            "ep-dc860fff5462": "2024-11-11T09:00:00Z",
            "ep-fb089e44dc01": "2024-11-04T09:00:00Z",
            "ep-18de1e8d393b": "2024-10-28T08:00:00Z",
            "ep-bec7f3776eb4": "2024-10-21T08:00:00Z",
            "ep-85f611f0ec8a": "2024-10-14T08:00:00Z",
            "ep-dfaf20e30e8f": "2024-10-07T08:00:00Z",
            "ep-ceac065ef83e": "2024-09-30T08:00:00Z",
            "ep-fdbace6cfeac": "2024-09-16T08:00:00Z",
            "ep-eb9f36449956": "2024-09-09T08:00:00Z",
            "ep-0b606b3a939b": "2024-09-02T08:00:00Z",
            "ep-2e335cac8e37": "2024-08-19T08:00:00Z",
            "ep-70aa61b101f3": "2024-08-12T08:00:00Z",
            "ep-2bc447654ff1": "2024-08-05T08:00:00Z",
            "ep-c3d1dc086eb1": "2024-07-29T08:00:00Z",
            "ep-2db14b1fe531": "2024-07-22T08:00:00Z",
            "ep-1c1c621f2c05": "2026-10-26T08:00:00Z",
            "ep-af0546901ade": "2025-11-03T09:00:00Z",
            "ep-e724725c9c98": "2025-10-06T08:00:00Z",
            "ep-80e08a6d1110": "2025-09-15T08:00:00Z",
            "ep-416176e0a526": "2025-08-25T08:00:00Z",
            "ep-aa6b9d8c03af": "2025-08-18T08:00:00Z",
            "ep-caac26b88f43": "2025-07-28T08:00:00Z",
            "ep-469ee27f3f42": "2025-07-21T08:00:00Z",
            "ep-b26aabe0cd25": "2025-06-09T08:00:00Z",
            "ep-69c480c7e5da": "2025-05-19T08:00:00Z",
            "ep-c8132934ae2a": "2025-12-29T09:00:00Z",
            "ep-25234662ebf8": "2025-12-15T09:00:00Z",
            "ep-ce5fb6c20006": "2025-12-08T09:00:00Z",
            "ep-c3dfb8e05662": "2025-11-24T09:00:00Z",
            "ep-2439189db5fe": "2025-11-17T09:00:00Z",
            "ep-70e7d23554dc": "2025-11-10T09:00:00Z",
            "ep-fb628e7a4cd6": "2025-10-27T08:33:00Z",
            "ep-ee7dd8290ee5": "2025-10-20T08:00:00Z",
            "ep-a1ef2b9e0dba": "2025-09-29T08:00:00Z",
            "ep-8fa56998b30c": "2025-09-22T08:00:00Z",
            "ep-f0f8ef1ccebb": "2025-09-08T08:00:00Z",
            "ep-c6dbd149f5d7": "2025-09-01T08:00:00Z",
            "ep-6c0a34dbec31": "2025-08-04T08:00:00Z",
            "ep-1278bde47f01": "2025-07-14T08:00:00Z",
            "ep-57160644e7cf": "2025-06-30T08:00:00Z",
            "ep-14aecc92ceba": "2025-06-23T08:00:00Z",
            "ep-da74d87f9f47": "2025-06-16T08:00:00Z",
            "ep-8957ecc50beb": "2025-06-02T08:00:00Z",
            "ep-1a85f1b61f49": "2025-05-26T08:00:00Z",
            "ep-415235192c11": "2025-05-05T08:00:00Z",
            "ep-10d01a16d878": "2025-04-28T08:00:00Z",
            "ep-171c301c0729": "2025-04-21T08:00:00Z",
            "ep-6a025622e031": "2025-04-07T08:00:00Z",
            "ep-0df8acb66c49": "2025-03-31T08:00:00Z",
            "ep-07fedcba1443": "2025-03-17T08:00:00Z",
            "ep-fe75d44b200b": "2025-03-10T08:00:00Z",
            "ep-b920735d3d1e": "2025-03-03T09:00:00Z",
            "ep-5ca36831bcf3": "2025-02-24T09:00:00Z",
            "ep-9bdaeb076766": "2025-02-03T09:00:00Z",
            "ep-c5a06bbcf965": "2025-01-27T09:00:00Z",
            "ep-615bf4370e1b": "2025-08-11T08:00:00Z",
            "ep-4f67bc84be50": "2025-10-13T08:00:00Z",
            "ep-7286c0b5fb3c": "2025-03-24T08:00:00Z",
            "ep-46847b969704": "2025-02-17T09:00:00Z",
            "ep-78f6f5ffa993": "2026-10-19T08:00:00Z",
            "ep-43172c733089": "2026-08-31T08:00:00Z",
            "ep-9b1fb0261224": "2026-10-05T08:00:00Z",
            "ep-a8ecb0ae0c81": "2026-09-28T08:00:00Z",
            "ep-c24d3ee59354": "2026-08-17T08:00:00Z",
            "ep-226daf018467": "2026-05-04T08:00:00Z",
            "ep-4a3d9d5b8a6c": "2025-01-13T09:00:00Z",
            "ep-c09c96510c0c": "2026-06-01T08:00:00Z",
            "ep-5d4a2f70af51": "2026-03-23T08:00:00Z",
            "ep-966dac96a166": "2026-03-09T08:00:00Z",
            "ep-3e049bc03de9": "2026-02-23T09:00:00Z",
            "ep-b480bf029986": "2026-01-19T09:00:00Z",
            "ep-71a750278d03": "2026-06-15T08:00:00Z",
            "ep-13a459db84a2": "2026-04-27T08:00:00Z",
            "ep-e8faa4a6a0ce": "2026-03-30T08:00:00Z",
            "ep-b3f93de0e165": "2026-02-09T09:00:00Z",
        }
        for episode_id, published in dates.items():
            meta = json.loads((PROJECT / f"site/zh/{episode_id}.json").read_text())
            self.assertEqual(meta["published"], published)
            self.assertNotIn("essentials", meta["title_en"].lower())

    def test_pages_base_url_cards_and_real_dates(self):
        self.write_json("catalog/episodes.json", {"episodes": [
            {"id": "essay-new", "title_en": "Newer", "kind": "long_episode", "source_index_date": "1990-01-01"},
            {"id": "essay-old", "title_en": "Older", "kind": "long_episode", "source_index_date": "1991-01-01"},
            {"id": "essay-git", "title_en": "From git", "kind": "ama", "source_index_date": "1992-06-01"},
        ]})
        (self.root / "site/zh").mkdir(parents=True)
        essays = {
            "essay-new": ("较新的中文标题", "2025-07-07T08:00:00Z"),
            "essay-old": ("较早的中文标题", "2021-01-11T09:00:00Z"),
        }
        for episode_id, (title, published) in essays.items():
            (self.root / "site/zh" / f"{episode_id}.md").write_text(f"# {title}\n\n导语。\n\n## 第一章\n\n正文 {episode_id}。\n", encoding="utf-8")
            self.write_json(f"site/zh/{episode_id}.json", {
                "id": episode_id, "title_zh": title, "published": published,
                "source_url": "https://www.hubermanlab.com/episode/example",
                "sections": [{"title": "第一章", "source_seconds": 10}],
            })
        (self.root / "site/zh/essay-git.md").write_text("# 只有提交时间\n\n导语。\n\n## 第一章\n\n正文来自提交。\n", encoding="utf-8")
        self.write_json("site/zh/essay-git.json", {
            "id": "essay-git", "title_zh": "只有提交时间",
            "source_url": "https://www.hubermanlab.com/episode/example",
            "sections": [{"title": "第一章", "source_seconds": None}],
        })
        env = os.environ.copy()
        env.update({
            "GIT_AUTHOR_NAME": "Feed Test", "GIT_AUTHOR_EMAIL": "feed@example.com",
            "GIT_COMMITTER_NAME": "Feed Test", "GIT_COMMITTER_EMAIL": "feed@example.com",
            "GIT_AUTHOR_DATE": "2022-05-06T07:08:09Z", "GIT_COMMITTER_DATE": "2022-05-06T07:08:09Z",
        })
        subprocess.run(["git", "init"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "add", "site/zh/essay-git.md", "site/zh/essay-git.json"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add essay"], cwd=self.root, check=True, capture_output=True, env=env)
        pages = "https://tolsonhuddy-collab.github.io/huberman-tolson-cn"
        manifest = site.build_site(self.root, Path("dist"), published=True, base_url=pages + "/")
        self.assertEqual(manifest["feed_entry_count"], 3)
        atom = "{http://www.w3.org/2005/Atom}"
        feed = ET.parse(self.root / "dist/feed.xml")
        root = feed.getroot()
        self.assertEqual(root.findtext(f"{atom}updated"), "2025-07-07T08:00:00Z")
        self.assertEqual(root.find(f"{atom}link[@rel='self']").get("href"), pages + "/feed.xml")
        entries = root.findall(f"{atom}entry")
        self.assertEqual([entry.findtext(f"{atom}id").rsplit(":", 1)[-1] for entry in entries], ["essay-new", "essay-git", "essay-old"])
        self.assertEqual(entries[0].findtext(f"{atom}published"), "2025-07-07T08:00:00Z")
        self.assertEqual(entries[1].findtext(f"{atom}published"), "2022-05-06T07:08:09Z")
        self.assertEqual(entries[2].findtext(f"{atom}published"), "2021-01-11T09:00:00Z")
        raw = (self.root / "dist/feed.xml").read_text(encoding="utf-8")
        self.assertNotIn("1970-01-01", raw)
        self.assertNotIn("1990-01-01", raw)
        self.assertNotIn("huberman-reading-001.tolsonhuddy.chatgpt.site/episodes/", raw)
        self.assertIn(pages + "/episodes/essay-new.html", raw)
        self.assertIn(pages + "/og/essay-new.jpg", raw)
        opml = ET.parse(self.root / "dist/tolson-rss.opml")
        self.assertEqual([node.get("xmlUrl") for node in opml.getroot().iter("outline") if node.get("xmlUrl")], [pages + "/podcasts/huberman/feed.xml"])
        page = (self.root / "dist/episodes/essay-new.html").read_text(encoding="utf-8")
        self.assertIn(f'property="og:image" content="{pages}/og/essay-new.jpg"', page)
        from PIL import Image
        with Image.open(self.root / "dist/og/essay-new.jpg") as card:
            self.assertEqual(card.size, (1200, 630))
        self.write_json("site/zh/essay-old.json", {
            "id": "essay-old", "title_zh": "较早的中文标题", "published": "1999-12-31T00:00:00Z",
            "sections": [{"title": "第一章", "source_seconds": 10}],
        })
        with self.assertRaisesRegex(ValueError, "before 2000"):
            site.build_site(self.root, Path("dist/too-old"), published=True)

    def test_card_title_does_not_orphan_a_glyph(self):
        title = "神经系统如何工作，又如何被经验改变"
        font = site.load_font("sans-bold", 72)
        lines = site.balanced_title_lines(title, font, 900, 3)
        self.assertIsNotNone(lines)
        self.assertEqual("".join(lines), title)
        self.assertTrue(all(len(line) >= 2 for line in lines))
        self.assertTrue(all(not line.startswith(tuple("，。、：；")) for line in lines))
        fitted, wrapped, _size = site.fit_title(title, "sans-bold", 1056, 86, 48)
        self.assertGreaterEqual(fitted.getlength(wrapped[-1]), fitted.getlength("变") * 2)


if __name__ == "__main__":
    unittest.main()
