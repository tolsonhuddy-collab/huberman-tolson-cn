"""Boundary tests: source immutability, resumability and publication isolation."""
import hashlib
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

    def test_code_path_allowlist_excludes_rendered_fulltext(self):
        for path in ["private/articles/a.md", "dist/index.html", "content/article_zh.md", ".openai/hosting.json", ".env", "web/../../private/a.md", "web/photo.jpg"]:
            self.assertFalse(p.public_path(path), path)
        for path in ["README.md", "scripts/pipeline.py", "web/style.css", "web/app.js", "catalog/episodes.json"]:
            self.assertTrue(p.public_path(path), path)


if __name__ == "__main__":
    unittest.main()
