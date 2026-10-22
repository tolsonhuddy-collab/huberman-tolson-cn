"""Boundary tests: source immutability, resumability and publication isolation."""
import hashlib
import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("pipeline", Path(__file__).resolve().parents[1] / "scripts/pipeline.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patch = patch.object(p, "ROOT", self.root)
        self.patch.start()
        p.write_json(self.root / "catalog/episodes.json", {"episodes": [{"id": "test", "kind": "long_episode", "title_en": "Test"}]})
        p.write_json(self.root / "private/progress.json", {"episodes": {"test": {"status": "pending", "history": []}}})

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_no_completion_from_preparation_or_missing_draft(self):
        p.record("test", "drafting", "start")
        with self.assertRaisesRegex(ValueError, "finished draft"):
            p.record("test", "draft_complete", "not done")
        self.assertEqual(p.progress()["episodes"]["test"]["status"], "drafting")

    def test_review_is_invalidated_by_article_edit(self):
        article = self.root / "private/articles/test.md"
        article.parent.mkdir(parents=True)
        article.write_text("# 测试\n" + "".join(f"## 第{i}节\n\n" + "文" * 1100 + "\n\n" for i in range(8)))
        checks = {k: True for k in ["source_read_in_full", "beginning", "middle", "end", "speaker_attribution", "uncertainty_preserved", "ad_removed"]}
        p.write_json(self.root / "private/reviews/test.author-review.json", {"episode_id": "test", "checks": checks, "coverage": [{}] * 8})
        p.record("test", "drafting", "start")
        p.record("test", "draft_complete", "author checked")
        independent_checks = {k: True for k in ["beginning", "middle", "end", "speaker_attribution", "uncertainty_preserved", "examples_retained", "natural_prose"]}
        p.write_json(self.root / "private/reviews/test.independent-review.json", {"review_kind": "independent_editorial_review", "verdict": "pass", "source_read_in_full": True, "checks": independent_checks, "article_sha256": p.sha(article)})
        article.write_text(article.read_text() + "改动")
        self.assertEqual(p.status()["active"][0]["status"], "needs_revision")
        self.assertTrue(p.status()["active"][0]["verification_stale"])
        with self.assertRaisesRegex(ValueError, "changed since"):
            p.record("test", "reviewed", "stale review")

    def test_review_requires_distinct_editorial_record(self):
        with self.assertRaises(ValueError):
            p.record("test", "reviewed", "skip steps")
        self.assertEqual(p.progress()["episodes"]["test"]["status"], "pending")

    def test_vtt_chunks_keep_every_cue_once(self):
        source = self.root / "input/txt"
        vtt_dir = source.parent / "vtt"
        source.mkdir(parents=True)
        vtt_dir.mkdir()
        txt = source / "Test.txt"
        txt.write_text("original untouched")
        vtt = vtt_dir / "Test.vtt"
        vtt.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\none &amp; two\n\n00:00:01.000 --> 00:00:02.000\nthree four\n\n00:00:02.000 --> 00:00:03.000\nfive\n")
        before = (txt.read_bytes(), vtt.read_bytes())
        p.write_json(self.root / "private/local-config.json", {"source_dir": str(source)})
        p.write_json(self.root / "catalog/episodes.json", {"episodes": [{"id": "test", "kind": "long_episode", "source_file": "Test.txt", "source_sha256": p.sha(txt), "vtt_sha256": p.sha(vtt)}]})
        result = p.prepare("test", max_words=3)
        covered = [cue for chunk in result["chunks"] for cue in range(chunk["first_cue"], chunk["last_cue"] + 1)]
        self.assertEqual(covered, [1, 2, 3])
        self.assertEqual(before, (txt.read_bytes(), vtt.read_bytes()))
        self.assertEqual(p.progress()["episodes"]["test"]["status"], "pending")

    def test_source_paths_cannot_escape_or_follow_symlink(self):
        with self.assertRaises(ValueError):
            p.safe_source(self.root, "../secret.txt")
        target = self.root / "actual.txt"
        target.write_text("example")
        (self.root / "link.txt").symlink_to(target)
        with self.assertRaises(ValueError):
            p.safe_source(self.root, "link.txt")

    def test_vtt_whitespace_payload_line_does_not_drop_following_text(self):
        source = self.root / "input/txt"
        vtt_dir = source.parent / "vtt"
        source.mkdir(parents=True)
        vtt_dir.mkdir()
        txt = source / "Test.txt"
        txt.write_text("Welcome to the podcast. [Music]")
        vtt = vtt_dir / "Test.vtt"
        payload = ("WEBVTT\n\n00:00:00.320 --> 00:00:02.149 align:start position:0%\n \n"
                   "Welcome<00:00:00.500><c> to the podcast.</c>\n\n"
                   "00:00:02.149 --> 00:00:03.000\n \n\n"
                   "00:00:03.000 --> 00:00:04.000\n \n[Music]\n")
        vtt.write_bytes(payload.replace("\n", "\r\n").encode())
        before = (txt.read_bytes(), vtt.read_bytes())
        cues = p.vtt_cues(vtt)
        self.assertEqual([c["text"] for c in cues], ["Welcome to the podcast.", "", "[Music]"])
        self.assertEqual([(c["start"], c["end"]) for c in cues], [(0.32, 2.149), (2.149, 3.0), (3.0, 4.0)])
        p.write_json(self.root / "private/local-config.json", {"source_dir": str(source)})
        p.write_json(self.root / "catalog/episodes.json", {"episodes": [{"id": "test", "kind": "long_episode", "source_file": "Test.txt", "source_sha256": p.sha(txt), "vtt_sha256": p.sha(vtt)}]})
        result = p.prepare("test", max_words=4)
        self.assertEqual(result["cue_count"], 3)
        chunks = "".join((self.root / "private/chunks/test" / c["file"]).read_text() for c in result["chunks"])
        self.assertIn("[0.320–2.149] Welcome to the podcast.", chunks)
        self.assertIn("[2.149–3.000] \n", chunks)
        self.assertIn("[3.000–4.000] [Music]", chunks)
        self.assertEqual(before, (txt.read_bytes(), vtt.read_bytes()))
        self.assertEqual(p.progress()["episodes"]["test"]["status"], "pending")

    def test_reingest_cannot_silently_reset_changed_subtitle_baseline(self):
        source = self.root / "input/txt"
        vtt_dir = source.parent / "vtt"
        source.mkdir(parents=True)
        vtt_dir.mkdir()
        txt = source / "Test.txt"
        txt.write_text("source unchanged")
        vtt = vtt_dir / "Test.vtt"
        vtt.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nfirst version\n")
        audit = self.root / "audit.csv"
        row = {"文件名": "Test.txt", "SHA256": p.sha(txt), "类型初筛": "常规长节目/Guest Series 候选", "Guest Series": "False", "英文词数": "2", "索引日期_未独立核实": "", "来源_来自索引": "synthetic", "明确AMA节选": "False"}
        with audit.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)
        p.ingest(source, audit)
        baseline = (self.root / "catalog/episodes.json").read_bytes()
        vtt.write_text(vtt.read_text().replace("first version", "changed subtitle"))
        with self.assertRaisesRegex(ValueError, "do not reset the baseline"):
            p.ingest(source, audit)
        self.assertEqual((self.root / "catalog/episodes.json").read_bytes(), baseline)

    def test_code_path_allowlist_excludes_rendered_fulltext(self):
        for path in ["private/articles/a.md", "dist/index.html", "content/article_zh.md", ".openai/hosting.json", ".env", "web/../../private/a.md", "web/photo.jpg"]:
            self.assertFalse(p.public_path(path), path)
        for path in ["README.md", "scripts/pipeline.py", "web/style.css", "web/app.js", "catalog/episodes.json", ".github/workflows/pages.yml"]:
            self.assertTrue(p.public_path(path), path)

    def test_documentation_images_do_not_allow_other_raster_paths(self):
        for name in ("docs/screenshot-home.png", "docs/xiaohongshu.jpg"):
            self.assertTrue(p.public_path(name), name)
        for name in ("docs/episode.jpg", "docs/new.png", "web/screenshot-home.png", "docs/../docs/xiaohongshu.jpg"):
            self.assertFalse(p.public_path(name), name)

    def test_git_audit_checks_documentation_worktree_bytes(self):
        name = "docs/screenshot-home.png"
        payload = b"approved documentation image fixture"
        image = self.root / name
        image.parent.mkdir()
        image.write_bytes(payload)
        pins = {name: hashlib.sha256(payload).hexdigest()}
        entry = b"100644 " + b"0" * 40 + b" 0\t" + name.encode() + b"\n"
        with patch.object(p, "PUBLIC_DOC_IMAGES", pins), patch.object(p.subprocess, "check_output", side_effect=[name.encode() + b"\0", entry, payload]):
            self.assertEqual(p.audit_git()["path_allowlist"], "pass")
        image.write_bytes(b"different worktree image")
        with patch.object(p, "PUBLIC_DOC_IMAGES", pins), patch.object(p.subprocess, "check_output", side_effect=[name.encode() + b"\0", entry, payload]):
            with self.assertRaisesRegex(ValueError, "Pinned documentation image bytes changed"):
                p.audit_git()

    def test_git_audit_rejects_staged_image_change_and_symlink(self):
        name = "docs/screenshot-home.png"
        payload = b"approved documentation image fixture"
        image = self.root / name
        image.parent.mkdir()
        image.write_bytes(payload)
        pins = {name: hashlib.sha256(payload).hexdigest()}
        entry = b"100644 " + b"0" * 40 + b" 0\t" + name.encode() + b"\n"
        with patch.object(p, "PUBLIC_DOC_IMAGES", pins), patch.object(p.subprocess, "check_output", side_effect=[name.encode() + b"\0", entry, b"different staged image"]):
            with self.assertRaisesRegex(ValueError, "Pinned documentation image bytes changed"):
                p.audit_git()
        target = self.root / "private/image.png"
        target.write_bytes(payload)
        image.unlink()
        image.symlink_to(target)
        with patch.object(p, "PUBLIC_DOC_IMAGES", pins), patch.object(p.subprocess, "check_output", return_value=name.encode() + b"\0"):
            with self.assertRaisesRegex(ValueError, "symlinks"):
                p.audit_git()

    def test_git_audit_requires_normal_image_index_mode(self):
        name = "docs/screenshot-home.png"
        image = self.root / name
        image.parent.mkdir()
        image.write_bytes(b"documentation image fixture")
        for mode in (b"100755", b"120000"):
            entry = mode + b" " + b"0" * 40 + b" 0\t" + name.encode() + b"\n"
            with self.subTest(mode=mode), patch.object(p.subprocess, "check_output", side_effect=[name.encode() + b"\0", entry]):
                with self.assertRaisesRegex(ValueError, "non-executable indexed file"):
                    p.audit_git()

    def test_git_audit_rejects_documentation_symlink_parent(self):
        name = "docs/screenshot-home.png"
        real_docs = self.root / "real-docs"
        real_docs.mkdir()
        (real_docs / "screenshot-home.png").write_bytes(b"documentation image fixture")
        (self.root / "docs").symlink_to(real_docs, target_is_directory=True)
        with patch.object(p.subprocess, "check_output", return_value=name.encode() + b"\0"):
            with self.assertRaisesRegex(ValueError, "symlinked parent"):
                p.audit_git()


if __name__ == "__main__":
    unittest.main()
