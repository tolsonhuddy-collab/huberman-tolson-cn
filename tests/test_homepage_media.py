"""Homepage imagery must never leak into existing article pages or feeds."""
import hashlib
import json
from pathlib import Path
import shutil
import unittest
from PIL import Image

import test_site as fixtures

site = fixtures.site


class HomepageMediaTests(unittest.TestCase):
    setUp = fixtures.SiteTests.setUp
    inputs = fixtures.SiteTests.inputs
    write_json = fixtures.SiteTests.write_json

    def prepare(self):
        self.inputs()
        target = self.root / "site/zh"
        target.mkdir(parents=True)
        for suffix in ("a", "b"):
            eid = "episode-" + suffix
            shutil.copyfile(self.root / f"private/articles/{eid}.md", target / f"{eid}.md")
            shutil.copyfile(self.root / f"private/metadata/{eid}.json", target / f"{eid}.json")
        # Public builds must not depend on the presence of private records.
        shutil.rmtree(self.root / "private")

    def register(self):
        rows = {}
        for eid in ("episode-a", "episode-b"):
            rows[eid] = {}
            for kind, relative in [("cover", f"covers/{eid}.png"), ("portrait", f"portraits/{eid}-0.png")]:
                path = self.root / "site/homepage-media" / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (12, 12), "red").save(path)
                rows[eid][kind] = {"path": relative, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                   "source_url": "https://example.org/published.png", "alt": "Existing verified image"}
        data = {"schema_version": 1, "featured_episode_id": "episode-b", "episodes": rows}
        self.write_json("site/homepage.json", data)
        return data

    def test_homepage_only_with_existing_body_feed_card_design_bytes_preserved(self):
        self.prepare()
        site.build_site(self.root, Path("dist/before"), published=True)
        self.register()
        site.build_site(self.root, Path("dist/after"), published=True)
        before, after = self.root / "dist/before", self.root / "dist/after"
        for p in before.rglob("*"):
            if p.is_file() and p.name != "index.html":
                self.assertEqual(p.read_bytes(), (after / p.relative_to(before)).read_bytes(), p.name)
        html = (after / "index.html").read_text()
        self.assertIn('id="front-story"', html)
        self.assertIn('id="front-story-title"><a href="episodes/episode-b.html"', html)
        self.assertIn('src="portraits/episode-b-0.png"', html)
        self.assertNotIn('portraits/episode-b-0.png', (after / "episodes/episode-b.html").read_text())
        self.assertEqual((after / "covers/episode-b.png").read_bytes(), (self.root / "site/homepage-media/covers/episode-b.png").read_bytes())

    def test_wrong_hash_fails_without_replacing_last_good_build(self):
        self.prepare()
        self.register()
        site.build_site(self.root, Path("dist/keep"), published=True)
        old = (self.root / "dist/keep/index.html").read_bytes()
        (self.root / "site/homepage-media/covers/episode-b.png").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "hash/source"):
            site.build_site(self.root, Path("dist/keep"), published=True)
        self.assertEqual((self.root / "dist/keep/index.html").read_bytes(), old)

    def test_traversal_symlink_and_unknown_program_are_rejected(self):
        self.prepare()
        data = self.register()
        original = json.loads(json.dumps(data))
        data["episodes"]["episode-b"]["cover"]["path"] = "../secret.png"
        self.write_json("site/homepage.json", data)
        with self.assertRaisesRegex(ValueError, "registered raster"):
            site.build_site(self.root, Path("dist/bad"), published=True)
        data = original
        self.write_json("site/homepage.json", data)
        path = self.root / "site/homepage-media/covers/episode-b.png"
        outside = self.root / "other.png"
        shutil.copyfile(path, outside)
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "non-symlink"):
            site.build_site(self.root, Path("dist/bad"), published=True)
        data["episodes"]["not-a-published-program"] = {}
        data["episodes"].pop("episode-b")
        data["featured_episode_id"] = "episode-a"
        self.write_json("site/homepage.json", data)
        with self.assertRaisesRegex(ValueError, "existing essay"):
            site.build_site(self.root, Path("dist/bad"), published=True)
