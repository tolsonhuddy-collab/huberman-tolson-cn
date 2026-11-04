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

    def nonlong_draft(self, kind="ama", excerpt=True):
        item = {"id": "test", "kind": kind, "title_en": "Released source", "explicit_excerpt": excerpt, "word_count": 4000}
        scope = "public_excerpt" if kind == "ama" and excerpt else {"ama": "full_episode", "live_qa": "released_qa", "essentials": "independent_essentials"}[kind]
        p.write_json(self.root / "catalog/episodes.json", {"episodes": [item]})
        meta = {"id": "test", "title_zh": "本次提供话题（公开节选）", "source_scope": scope,
                "source_scope_note": "仅覆盖本次公开来源实际提供的问答与解释，不包含未提供的会员话题或整场演讲。"}
        meta_path = self.root / "private/metadata/test.json"
        p.write_json(meta_path, meta)
        count = 6 if scope in {"full_episode", "released_qa"} else 3
        article = self.root / "private/articles/test.md"
        article.parent.mkdir(parents=True, exist_ok=True)
        article.write_text("# 本次来源精读\n" + "".join(f"## 话题{i}\n\n" + "文" * 810 + "\n\n" for i in range(count)))
        checks = {k: True for k in ["source_read_in_full", "beginning", "middle", "end", "speaker_attribution", "uncertainty_preserved", "ad_removed", *p.SCOPE_CHECKS]}
        author = {"episode_id": "test", "author": "writer", "checks": checks, "coverage": [{}] * count,
                  "article_sha256": p.sha(article), "metadata_sha256": p.sha(meta_path)}
        independent = {"review_kind": "independent_editorial_review", "reviewer": "editor", "verdict": "pass", "source_read_in_full": True,
                       "checks": {k: True for k in ["beginning", "middle", "end", "speaker_attribution", "uncertainty_preserved", "examples_retained", "natural_prose", *p.SCOPE_CHECKS]},
                       "article_sha256": p.sha(article), "metadata_sha256": p.sha(meta_path)}
        p.write_json(self.root / "private/reviews/test.author-review.json", author)
        p.write_json(self.root / "private/reviews/test.independent-review.json", independent)
        return item, meta, author, independent

    def test_nonlong_short_drafts_have_scoped_thresholds_and_keep_review_gates(self):
        for kind, excerpt, sections in [("ama", True, 3), ("ama", False, 6), ("live_qa", False, 6), ("essentials", False, 3)]:
            with self.subTest(kind=kind, excerpt=excerpt):
                item, meta, _, _ = self.nonlong_draft(kind, excerpt)
                p.write_json(self.root / "private/progress.json", {"episodes": {"test": {"status": "pending", "history": []}}})
                self.assertLess(p.article_metrics("test")["chinese_characters"], 8000)
                self.assertEqual(p.quality_requirements(item, meta)["chinese_characters"], 2400)
                self.assertEqual(p.quality_requirements(item, meta)["sections"], sections)
                self.assertEqual(p.quality_requirements(item, meta)["coverage"], sections)
                p.record("test", "drafting", "read available source")
                p.record("test", "draft_complete", "author covered actual scope")
                p.record("test", "reviewed", "different editor checked source")
                state = p.status()
                self.assertEqual(state["states"], {})
                self.assertEqual(state["all_states"], {"reviewed": 1})
                self.assertEqual(state["by_kind"][kind]["states"], {"reviewed": 1})

    def test_nonlong_cannot_skip_scope_checks_or_reuse_edited_scope_review(self):
        _, meta, author, independent = self.nonlong_draft()
        p.record("test", "drafting", "start")
        author["checks"]["unprovided_topics_not_invented"] = False
        p.write_json(self.root / "private/reviews/test.author-review.json", author)
        with self.assertRaisesRegex(ValueError, "author source-scope"):
            p.record("test", "draft_complete", "missing scope check")
        author["checks"]["unprovided_topics_not_invented"] = True
        p.write_json(self.root / "private/reviews/test.author-review.json", author)
        p.record("test", "draft_complete", "author checked")
        independent["checks"]["source_scope_correct"] = False
        p.write_json(self.root / "private/reviews/test.independent-review.json", independent)
        with self.assertRaisesRegex(ValueError, "independent source-scope"):
            p.record("test", "reviewed", "missing independent check")
        independent["checks"]["source_scope_correct"] = True
        independent["reviewer"] = "writer"
        p.write_json(self.root / "private/reviews/test.independent-review.json", independent)
        with self.assertRaisesRegex(ValueError, "different independent"):
            p.record("test", "reviewed", "same author")
        meta["source_scope_note"] += "新增范围说明。"
        p.write_json(self.root / "private/metadata/test.json", meta)
        self.assertEqual(p.status()["active"][0]["status"], "needs_revision")
        with self.assertRaisesRegex(ValueError, "changed since author"):
            p.record("test", "reviewed", "stale scope review")
        author["metadata_sha256"] = p.sha(self.root / "private/metadata/test.json")
        p.write_json(self.root / "private/reviews/test.author-review.json", author)
        independent["reviewer"] = "editor"
        p.write_json(self.root / "private/reviews/test.independent-review.json", independent)
        with self.assertRaisesRegex(ValueError, "metadata changed since independent"):
            p.record("test", "reviewed", "old independent metadata hash")

    def test_nonlong_edited_article_cannot_reuse_independent_pass(self):
        _, _, author, _ = self.nonlong_draft()
        p.record("test", "drafting", "start")
        p.record("test", "draft_complete", "author checked")
        article = self.root / "private/articles/test.md"
        article.write_text(article.read_text() + "修改正文。")
        author["article_sha256"] = p.sha(article)
        p.write_json(self.root / "private/reviews/test.author-review.json", author)
        with self.assertRaisesRegex(ValueError, "changed since independent"):
            p.record("test", "reviewed", "old independent hash")
        (self.root / "private/reviews/test.independent-review.json").unlink()
        with self.assertRaises(FileNotFoundError):
            p.record("test", "reviewed", "missing independent record")

    def test_scope_mismatch_missing_note_and_unscoped_excerpt_title_are_rejected(self):
        item, meta, _, _ = self.nonlong_draft()
        for change in [{"source_scope": "full_episode"}, {"source_scope_note": " "}, {"title_zh": "未提供话题的整期标题"}, {"id": "wrong"}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                p.validate_source_scope(item, {**meta, **change})
        with self.assertRaises(ValueError):
            p.validate_source_scope(item, {k: v for k, v in meta.items() if k != "source_scope"})

    def test_long_thresholds_are_not_reduced_by_short_source_metadata(self):
        item = {"id": "test", "kind": "long_episode", "word_count": 500}
        self.assertEqual(p.quality_requirements(item, {"source_scope": "public_excerpt"}), {"chinese_characters": 8000, "sections": 8, "coverage": 8})
        article = self.root / "private/articles/test.md"
        article.parent.mkdir(parents=True)
        article.write_text("# 短壳\n" + "".join("## 话题\n" + "文" * 500 for _ in range(8)))
        p.record("test", "drafting", "start")
        with self.assertRaisesRegex(ValueError, "finished draft"):
            p.record("test", "draft_complete", "below unchanged long floor")
        excerpt = {"id": "short", "kind": "ama", "explicit_excerpt": True, "word_count": 1}
        meta = {"id": "short", "title_zh": "公开节选，非完整版", "source_scope": "public_excerpt", "source_scope_note": "仅涵盖提供来源。"}
        self.assertEqual(p.quality_requirements(excerpt, meta)["chinese_characters"], 1600)
        self.assertEqual(p.quality_requirements({**excerpt, "word_count": 20000}, meta)["chinese_characters"], 6000)

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

    def test_prepare_all_kinds_isolates_batches_and_never_overwrites_prior_evidence(self):
        source = self.root / "input/txt"
        source.mkdir(parents=True)
        (source.parent / "vtt").mkdir()
        txt, vtt = source / "Test.txt", source.parent / "vtt/Test.vtt"
        txt.write_text("one two")
        vtt.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\none two\n")
        p.write_json(self.root / "private/local-config.json", {"source_dir": str(source)})
        items = [{"id": kind, "kind": kind, "source_file": "Test.txt", "source_sha256": p.sha(txt), "vtt_sha256": p.sha(vtt)} for kind in p.KINDS.values()]
        p.write_json(self.root / "catalog/episodes.json", {"episodes": items})
        for item in items:
            with self.subTest(kind=item["kind"]):
                first = p.prepare(item["id"])
                map_path = self.root / first["source_map_file"]
                original = map_path.read_bytes()
                with self.assertRaisesRegex(ValueError, "already exist"):
                    p.prepare(item["id"])
                isolated = p.prepare(item["id"], batch="production370-20261104")
                self.assertIn("production370-20261104/", isolated["source_map_file"])
                self.assertEqual(map_path.read_bytes(), original)
                self.assertEqual(isolated["cue_count"], 1)
        for bad in ["../escape", "two/parts", ".", "", "Batch"]:
            with self.subTest(batch=bad), self.assertRaisesRegex(ValueError, "safe lowercase slug"):
                p.prepare(items[0]["id"], batch=bad)

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
        for path in ["private/articles/a.md", "dist/index.html", "content/article_zh.md", ".openai/hosting.json", ".env", "web/../../private/a.md", "web/photo.jpg", "README.private.md"]:
            self.assertFalse(p.public_path(path), path)
        for path in ["README.md", "README.en.md", "scripts/pipeline.py", "web/style.css", "web/app.js", "catalog/episodes.json", ".github/workflows/pages.yml", "site/zh/002-master-sleep.md", "site/zh/002-master-sleep.json"]:
            self.assertTrue(p.public_path(path), path)
        for path in ["site/zh/cover.jpg", "site/zh/portrait.png", "site/zh/episode.txt", "site/zh/episode.vtt", "site/zh/audio.mp3", "site/index.html"]:
            self.assertFalse(p.public_path(path), path)

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
