"""Optional catalog coverage; no changes to reader pages, assets, or feeds."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest
from xml.etree import ElementTree as ET

import test_site as fixtures

PROJECT, site = fixtures.PROJECT, fixtures.site


class EssentialsCoverageTests(unittest.TestCase):
    setUp = fixtures.SiteTests.setUp
    write_json = fixtures.SiteTests.write_json
    inputs = fixtures.SiteTests.inputs

    def coverage(self, entries=None, **extra):
        self.write_json("catalog/essentials-coverage.json", {
            "schema_version": 1,
            "episodes": entries if entries is not None else [{
                "episode_id": "episode-essentials", "classification": "covered_by_original",
                "original_episode_id": "episode-b", "public_note": "本条内容可从原集精读阅读。",
            }], **extra,
        })

    def data(self):
        return site.read_private(self.root)

    def catalog(self):
        return site.render_catalog(self.root, *self.data(), True)

    @staticmethod
    def card(html, episode_id):
        return next(part for part in re.findall(r'<article class="episode-card".*?</article>', html, re.S)
                    if episode_id in part or (episode_id == "episode-essentials" and "An Essentials episode" in part))

    @staticmethod
    def tree(path):
        return {str(p.relative_to(path)): p.read_bytes() for p in path.rglob("*") if p.is_file()}

    def test_optional_file_absent_or_empty_keeps_catalog_bytes(self):
        self.inputs()
        expected = self.catalog()
        self.assertEqual(hashlib.sha256(expected.encode()).hexdigest(), "9983d398d12258c813c3fcf09bbe13e500171c16c87c01be69456ba8e262087a")
        self.coverage([])
        self.assertEqual(self.catalog(), expected)
        self.coverage([], outside_catalog=[{"title": "External Essentials", "classification": "difference_unresolved"}])
        self.assertEqual(self.catalog(), expected)

    def test_covered_card_has_plain_title_and_only_real_original_cta(self):
        self.inputs()
        self.coverage()
        html = self.catalog()
        card = self.card(html, "episode-essentials")
        self.assertIn('data-availability="covered"', card)
        self.assertIn('<h3>An Essentials episode</h3>', card)
        self.assertIn('href="episodes/episode-b.html">阅读原集精读</a>', card)
        self.assertNotIn("episodes/episode-essentials.html", card)
        self.assertIn("原集已有精读", card)
        self.assertNotIn("已审核", card)
        self.assertNotIn("已校读", card)
        self.assertIn("不计作新增精读或待整理", html)

    def test_original_must_have_actual_article_not_only_review_state(self):
        episodes = self.inputs()
        episodes.append({"id": "original-next", "title_en": "Original awaiting publication", "kind": "long_episode"})
        self.write_json("catalog/episodes.json", {"episodes": episodes})
        self.write_json("private/progress.json", {"episodes": {"original-next": {"status": "reviewed"}}})
        self.coverage([{"episode_id": "episode-essentials", "classification": "covered_by_original", "original_episode_id": "original-next"}])
        card = self.card(self.catalog(), "episode-essentials")
        self.assertIn('data-availability="pending"', card)
        self.assertIn("原集精读待上线", card)
        self.assertNotIn("原集已有精读", card)
        self.assertNotIn('href="episodes/original-next.html"', card)

    def test_unresolved_difference_remains_pending_with_explicit_label(self):
        self.inputs()
        self.coverage([{"episode_id": "episode-essentials", "classification": "difference_unresolved", "original_episode_id": "episode-b"}])
        card = self.card(self.catalog(), "episode-essentials")
        self.assertIn('data-availability="pending"', card)
        self.assertIn("内容差异待核", card)
        self.assertNotIn("原集已有精读", card)
        self.assertIn('href="episodes/episode-b.html">查看相关原集精读</a>', card)

    def test_existing62_transition_uses_article_membership_without_claiming_site_counts(self):
        episodes = [{"id": "original-live", "kind": "long_episode", "title_en": "Available original"},
                    {"id": "original-next", "kind": "long_episode", "title_en": "Future original"}]
        entries = []
        for n in range(62):
            eid = f"essential-{n:02d}"
            episodes.append({"id": eid, "kind": "essentials", "title_en": eid})
            entries.append({"episode_id": eid, "classification": "difference_unresolved" if n == 61 else "covered_by_original",
                            "original_episode_id": "original-next" if n == 60 else "original-live"})
        self.coverage(entries)
        progress = {"original-live": {"status": "reviewed"}, "original-next": {"status": "reviewed"}}
        articles = {"original-live": "actual available article"}
        html = site.render_catalog(self.root, episodes, progress, {}, articles, True)
        essentials = [x for x in re.findall(r'<article class="episode-card".*?</article>', html, re.S) if 'data-kind="essentials"' in x]
        self.assertEqual(sum('data-availability="covered"' in x for x in essentials), 60)
        self.assertEqual(sum('data-availability="pending"' in x for x in essentials), 2)
        articles["original-next"] = "actual newly available article"
        html = site.render_catalog(self.root, episodes, progress, {}, articles, True)
        essentials = [x for x in re.findall(r'<article class="episode-card".*?</article>', html, re.S) if 'data-kind="essentials"' in x]
        self.assertEqual(sum('data-availability="covered"' in x for x in essentials), 61)
        self.assertEqual(sum('data-availability="pending"' in x for x in essentials), 1)

    def test_only_catalog_index_changes_and_true_articles_and_feeds_stay_exact(self):
        self.inputs()
        before_manifest = site.build_site(self.root, Path("private/before"), private=True)
        before = self.tree(self.root / "private/before")
        self.coverage(outside_catalog=[{"title": "Outside catalog data only", "classification": "difference_unresolved"}])
        after_manifest = site.build_site(self.root, Path("private/after"), private=True)
        after = self.tree(self.root / "private/after")
        self.assertEqual(before_manifest, after_manifest)
        self.assertEqual(after_manifest["article_count"], 2)
        self.assertEqual(after_manifest["feed_entry_count"], 2)
        self.assertEqual(set(before), set(after))
        self.assertEqual([p for p in before if before[p] != after[p]], ["index.html"])
        self.assertEqual(site.directory_numbers(*self.data()[:2], self.data()[3]), {"episode-a": 1, "episode-b": 2, "episode-excerpt": 3, "episode-essentials": 4, "episode-live": 5})
        for rel in ["feed.xml", "podcasts/huberman/feed.xml"]:
            entries = ET.fromstring(after[rel]).findall("{http://www.w3.org/2005/Atom}entry")
            self.assertEqual(len(entries), 2)
            self.assertNotIn(b"episode-essentials", after[rel])
        self.assertIn("待整理 <span>2</span>", after["index.html"].decode())
        self.assertNotIn("Outside catalog data only", after["index.html"].decode())

    def test_removed_unresolved_entry_stays_out_of_catalog_and_keeps_original(self):
        episodes = self.inputs()
        self.coverage([{"episode_id": "episode-essentials", "classification": "difference_unresolved", "original_episode_id": "episode-b"}])
        site.build_site(self.root, Path("private/before-removal"), private=True)
        before = self.tree(self.root / "private/before-removal")
        self.write_json("catalog/episodes.json", {"episodes": [ep for ep in episodes if ep["id"] != "episode-essentials"]})
        self.coverage([])
        result = site.build_site(self.root, Path("private/after-removal"), private=True)
        after = self.tree(self.root / "private/after-removal")
        self.assertEqual(result["article_count"], 2)
        self.assertNotIn("An Essentials episode", after["index.html"].decode())
        self.assertNotIn("内容差异待核", after["index.html"].decode())
        self.assertEqual(before["episodes/episode-b.html"], after["episodes/episode-b.html"])
        for rel in ["feed.xml", "podcasts/huberman/feed.xml", "tolson-rss.opml"]:
            self.assertEqual(before[rel], after[rel])

    def test_bad_relationships_cannot_override_catalog_or_articles(self):
        self.inputs()
        valid = {"episode_id": "episode-essentials", "classification": "covered_by_original", "original_episode_id": "episode-b"}
        cases = [[{**valid, "episode_id": "episode-a"}], [{**valid, "episode_id": "missing"}], [valid, valid],
                 [{**valid, "classification": "approved"}], [{k: v for k, v in valid.items() if k != "original_episode_id"}],
                 [{**valid, "original_episode_id": "missing"}], [{**valid, "original_episode_id": "episode-essentials"}],
                 [{**valid, "original_episode_id": "episode-live"}], [{**valid, "public_note": ["not text"]}]]
        for entries in cases:
            with self.subTest(entries=entries):
                self.coverage(entries)
                with self.assertRaises(ValueError):
                    self.catalog()
        self.coverage([valid])
        episodes, progress, metadata, articles = self.data()
        articles["episode-essentials"] = "an existing independent article"
        with self.assertRaises(ValueError):
            site.read_essentials_coverage(self.root, episodes, articles)

    def test_public_note_is_escaped(self):
        self.inputs()
        self.coverage([{"episode_id": "episode-essentials", "classification": "difference_unresolved", "public_note": "<script>alert(1)</script>"}])
        self.assertIn("&lt;script&gt;", self.catalog())
        self.assertNotIn("<script>alert(1)</script>", self.catalog())

    @unittest.skipUnless(shutil.which("node"), "Uses existing optional Node; no installation")
    def test_unchanged_js_excludes_covered_from_both_filters_but_keeps_essentials_all(self):
        self.inputs()
        self.coverage()
        html = self.catalog()
        cards = [{"kind": a, "availability": b, "search": c} for a, b, c in re.findall(r'data-kind="([^"]+)" data-availability="([^"]+)" data-search="([^"]+)"', html)]
        stub = """
const assert=require('node:assert/strict');
const control=(value)=>({value,listeners:{},addEventListener(k,f){this.listeners[k]=f;}});
const nodes={'episode-search':control(''),'kind-filter':control('all'),'status-filter':control('all'),'result-count':{},'no-results':{},'front-story':{}};
const testCards=CARDS.map(dataset=>({dataset}));
global.document={documentElement:{dataset:{},style:{setProperty(){}},scrollHeight:800},getElementById(k){return nodes[k]||null;},querySelectorAll(s){return s==='.episode-card'?testCards:[];}};
global.window={innerHeight:800,scrollY:0,addEventListener(){}};global.requestAnimationFrame=f=>f();
""".replace("CARDS", json.dumps(cards))
        checks = """
assert.equal(testCards.filter(x=>!x.hidden).length,5);
for(const value of ['readable','pending']) {nodes['status-filter'].value=value;nodes['status-filter'].listeners.input();assert(testCards.filter(x=>x.dataset.availability==='covered').every(x=>x.hidden));}
nodes['status-filter'].value='all';nodes['kind-filter'].value='essentials';nodes['kind-filter'].listeners.input();
assert.equal(testCards.filter(x=>!x.hidden).length,1);assert.equal(testCards.find(x=>!x.hidden).dataset.availability,'covered');
"""
        result = subprocess.run([shutil.which("node"), "-e", stub + (PROJECT / "web/app.js").read_text() + checks], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

if __name__ == "__main__":
    unittest.main()
