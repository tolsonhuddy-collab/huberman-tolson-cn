#!/usr/bin/env python3
"""Read-only source intake and resumable editorial bookkeeping; no model/API calls."""
import argparse
import collections
import csv
import hashlib
import html
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KINDS = {"常规长节目/Guest Series 候选": "long_episode", "Essentials 精编": "essentials", "AMA": "ama", "现场问答": "live_qa"}
PILOT = {
    "How Your Nervous System Works & Changes.txt": "001-nervous-system",
    "Master Your Sleep & Be More Alert When Awake.txt": "002-master-sleep",
    "Science of Stress, Testosterone & Free Will ｜ Dr. Robert Sapolsky.txt": "003-sapolsky",
}
STATES = {"pending", "drafting", "draft_complete", "needs_revision", "reviewed"}
TRANSITIONS = {
    "pending": {"drafting"}, "drafting": {"draft_complete", "needs_revision"},
    "draft_complete": {"reviewed", "needs_revision"},
    "needs_revision": {"drafting", "draft_complete"}, "reviewed": {"needs_revision"},
}
PUBLIC_ROOT_FILES = {".gitignore", "README.md", "LICENSE", "CONTENT_RIGHTS.md", "DEPENDENCIES.md", "Makefile"}
PUBLIC_DIRS = {"scripts", "tests", "docs", "catalog", "web", ".github"}
STAMP = re.compile(r"^(?P<a>\d{2}:\d{2}:\d{2}\.\d{3})\s+-->\s+(?P<b>\d{2}:\d{2}:\d{2}\.\d{3})")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    """Replace atomically: an interrupted run retains either the old or new record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)


def safe_source(base, filename):
    if Path(filename).name != filename or filename in {".", ".."}:
        raise ValueError("source filename must be a basename")
    candidate = base / filename
    if candidate.is_symlink() or candidate.resolve().parent != base.resolve():
        raise ValueError("source path escapes its configured directory")
    return candidate


def seconds(value):
    h, m, s = value.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def vtt_cues(path):
    cues = []
    # A whitespace-only payload line can precede more text in the same cue.
    # Only an actually empty line separates cue blocks in these source files.
    for block in re.split(r"\n\n+", path.read_text(encoding="utf-8").replace("\r\n", "\n")):
        lines = block.splitlines()
        for index, line in enumerate(lines):
            match = STAMP.match(line)
            if match:
                start, end = seconds(match["a"]), seconds(match["b"])
                if end < start:
                    raise ValueError("VTT cue has a negative duration")
                text = html.unescape(re.sub(r"<[^>]*>", "", " ".join(lines[index + 1:]))).strip()
                cues.append({"cue": len(cues) + 1, "start": start, "end": end, "text": text})
                break
    if not cues:
        raise ValueError("no timestamped VTT cues")
    return cues


def catalog():
    return read_json(ROOT / "catalog/episodes.json")


def episode(episode_id):
    for item in catalog()["episodes"]:
        if item["id"] == episode_id:
            return item
    raise ValueError("unknown episode id: " + episode_id)


def progress():
    p = ROOT / "private/progress.json"
    return read_json(p) if p.exists() else {"schema_version": 1, "episodes": {}}


def ingest(source_dir, inventory):
    source_dir = source_dir.resolve()
    previous_path = ROOT / "catalog/episodes.json"
    previous = {item["source_file"]: item for item in read_json(previous_path)["episodes"] if "source_file" in item} if previous_path.exists() else {}
    with inventory.open(encoding="utf-8-sig", newline="") as inventory_file:
        rows = list(csv.DictReader(inventory_file))
    filenames = [r["文件名"] for r in rows]
    if len(filenames) != len(set(filenames)):
        raise ValueError("inventory contains duplicate filenames")
    actual = {p.name for p in source_dir.glob("*.txt")}
    if actual != set(filenames):
        raise ValueError("inventory and TXT directory do not match")
    items = []
    for row in rows:
        filename = row["文件名"]
        txt = safe_source(source_dir, filename)
        vtt = safe_source(source_dir.parent / "vtt", Path(filename).with_suffix(".vtt").name)
        if sha(txt) != row["SHA256"]:
            raise ValueError("source hash differs from read-only audit: " + filename)
        txt.read_text(encoding="utf-8", errors="strict")
        cues = vtt_cues(vtt)
        vtt_hash = sha(vtt)
        if filename in previous and previous[filename].get("vtt_sha256") not in {None, vtt_hash}:
            raise ValueError("VTT changed since previous intake; do not reset the baseline: " + filename)
        items.append({
            "id": PILOT.get(filename, "ep-" + hashlib.sha256(filename.encode()).hexdigest()[:12]),
            "title_en": Path(filename).stem, "source_file": filename,
            "kind": KINDS[row["类型初筛"]], "guest_series": row["Guest Series"] == "True",
            "word_count": int(row["英文词数"]), "source_sha256": row["SHA256"],
            "vtt_sha256": vtt_hash, "source_index_date": row["索引日期_未独立核实"] or None,
            "source_provider": row["来源_来自索引"], "source_url": None, "video_id": None,
            "explicit_excerpt": row["明确AMA节选"] == "True",
            "timeline": {"start_seconds": cues[0]["start"], "end_seconds": cues[-1]["end"], "provenance": "local_vtt_unverified"},
        })
    counts = dict(collections.Counter(item["kind"] for item in items))
    write_json(ROOT / "catalog/episodes.json", {
        "schema_version": 1, "counts": counts,
        "metadata_caution": "Local audit only. Dates and VTT duration are unverified; long episodes are candidates, not certified complete videos.",
        "episodes": items,
    })
    write_json(ROOT / "private/local-config.json", {"source_dir": str(source_dir), "inventory": str(inventory.resolve())})
    p = progress()
    for item in items:
        p["episodes"].setdefault(item["id"], {"status": "pending", "history": []})
    write_json(ROOT / "private/progress.json", p)
    return {"files": len(items), "counts": counts, "english_words": sum(i["word_count"] for i in items), "source_hashes_match": True}


def check_sources():
    source = Path(read_json(ROOT / "private/local-config.json")["source_dir"])
    failed = []
    for item in catalog()["episodes"]:
        for kind, base, name, expected in [
            ("txt", source, item["source_file"], item["source_sha256"]),
            ("vtt", source.parent / "vtt", Path(item["source_file"]).with_suffix(".vtt").name, item["vtt_sha256"]),
        ]:
            path = safe_source(base, name)
            if not path.is_file() or sha(path) != expected:
                failed.append({"id": item["id"], "format": kind})
    result = {"checked_at": now(), "txt_files": len(catalog()["episodes"]), "vtt_files": len(catalog()["episodes"]), "changed_or_missing": failed}
    write_json(ROOT / "private/reports/source-integrity.json", result)
    if failed:
        raise ValueError("changed or missing source files; see private/reports/source-integrity.json")
    return result


def prepare(episode_id, max_words=1200):
    item = episode(episode_id)
    if item["kind"] != "long_episode":
        raise ValueError("only long-episode candidates enter the current production queue")
    source = Path(read_json(ROOT / "private/local-config.json")["source_dir"])
    vtt = safe_source(source.parent / "vtt", Path(item["source_file"]).with_suffix(".vtt").name)
    if sha(vtt) != item["vtt_sha256"] or sha(safe_source(source, item["source_file"])) != item["source_sha256"]:
        raise ValueError("source changed; stop and investigate")
    cues = vtt_cues(vtt)
    chunks, current, size = [], [], 0
    for cue in cues:
        n = len(re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)*", cue["text"]))
        if current and size + n > max_words:
            chunks.append(current)
            current, size = [], 0
        current.append(cue)
        size += n
    if current:
        chunks.append(current)
    folder = ROOT / "private/chunks" / episode_id
    folder.mkdir(parents=True, exist_ok=True)
    metadata = []
    for index, group in enumerate(chunks, 1):
        name = f"{index:04}.txt"
        text = "\n".join(f"[{x['start']:.3f}–{x['end']:.3f}] {x['text']}" for x in group)
        (folder / name).write_text(text + "\n", encoding="utf-8")
        metadata.append({"file": name, "first_cue": group[0]["cue"], "last_cue": group[-1]["cue"], "start": group[0]["start"], "end": group[-1]["end"]})
    result = {"episode_id": episode_id, "source_sha256": item["source_sha256"], "vtt_sha256": item["vtt_sha256"], "cue_count": len(cues), "chunks": metadata, "status": "input_prepared_only"}
    write_json(ROOT / "private/source-maps" / (episode_id + ".json"), result)
    return result


def article_metrics(episode_id):
    path = ROOT / "private/articles" / (episode_id + ".md")
    if not path.exists():
        return {"exists": False, "chinese_characters": 0, "sections": 0}
    text = path.read_text(encoding="utf-8")
    return {"exists": True, "chinese_characters": len(re.findall(r"[\u4e00-\u9fff]", text)), "sections": len(re.findall(r"^## ", text, re.M)), "sha256": sha(path)}


def validate_review(episode_id, state):
    metrics = article_metrics(episode_id)
    if not metrics["exists"] or metrics["chinese_characters"] < 8000 or metrics["sections"] < 8:
        raise ValueError("finished draft must exist with substantial prose; length alone never certifies completeness")
    review = read_json(ROOT / "private/reviews" / (episode_id + ".author-review.json"))
    required = ("source_read_in_full", "beginning", "middle", "end", "speaker_attribution", "uncertainty_preserved", "ad_removed")
    if review.get("episode_id") != episode_id or not all(review.get("checks", {}).get(k) is True for k in required):
        raise ValueError("missing author coverage checks")
    if len(review.get("coverage", [])) < 8:
        raise ValueError("source-to-article coverage map missing")
    if state == "reviewed":
        independent = read_json(ROOT / "private/reviews" / (episode_id + ".independent-review.json"))
        if independent.get("review_kind") != "independent_editorial_review" or independent.get("verdict") != "pass":
            raise ValueError("independent editorial review has not passed")
        required_checks = ("beginning", "middle", "end", "speaker_attribution", "uncertainty_preserved", "examples_retained", "natural_prose")
        if independent.get("source_read_in_full") is not True or not all(independent.get("checks", {}).get(k) is True for k in required_checks):
            raise ValueError("independent source coverage checks are incomplete")
        if independent.get("article_sha256") != metrics["sha256"]:
            raise ValueError("article changed since independent review")
    return metrics


def record(episode_id, state, note):
    item = episode(episode_id)
    if item["kind"] != "long_episode":
        raise ValueError("other categories are catalogued, not in the current production scope")
    p = progress()
    row = p["episodes"].setdefault(episode_id, {"status": "pending", "history": []})
    old = row["status"]
    if state != old and state not in TRANSITIONS[old]:
        raise ValueError(f"invalid transition: {old} -> {state}")
    if state in {"draft_complete", "reviewed"}:
        row["metrics"] = validate_review(episode_id, state)
    row["status"] = state
    row["updated_at"] = now()
    row["history"].append({"at": now(), "from": old, "to": state, "note": note})
    write_json(ROOT / "private/progress.json", p)
    return {"id": episode_id, "status": state}


def status():
    p = progress()["episodes"]
    items = catalog()["episodes"]
    long = [i for i in items if i["kind"] == "long_episode"]
    counts, active = collections.Counter(), []
    for item in long:
        row = p.get(item["id"], {})
        recorded = row.get("status", "pending")
        metrics = article_metrics(item["id"]) if recorded != "pending" else None
        expected = row.get("metrics", {}).get("sha256")
        stale = recorded in {"draft_complete", "reviewed"} and expected is not None and metrics.get("sha256") != expected
        effective = "needs_revision" if stale else recorded
        counts[effective] += 1
        if recorded != "pending":
            active.append({"id": item["id"], "title": item["title_en"], "status": effective, "recorded_status": recorded, "verification_stale": stale, "metrics": metrics})
    return {"long_episode_candidates": len(long), "states": dict(counts), "other_categories": dict(collections.Counter(i["kind"] for i in items if i["kind"] != "long_episode")), "active": active}


def public_path(name):
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        return False
    return name in PUBLIC_ROOT_FILES or (len(path.parts) > 1 and path.parts[0] in PUBLIC_DIRS and not any(part.startswith(".") and part != ".github" for part in path.parts) and "__pycache__" not in path.parts and path.suffix in {".py", ".md", ".json", ".html", ".css", ".js", ".svg", ".txt", ".yml", ".yaml"})


def audit_git():
    # Inspect the entire index, including previously committed files, not only this diff.
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    bad = [name for name in names if name and not public_path(name)]
    symlinks = [name for name in names if name and (ROOT / name).is_symlink()]
    if bad or symlinks:
        raise ValueError("Git index contains non-allowlisted paths or symlinks: " + ", ".join(bad + symlinks))
    return {"tracked_files": sum(bool(name) for name in names), "path_allowlist": "pass", "note": "Path isolation check; editorial/content inspection is still required."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    ingest_p = sub.add_parser("ingest")
    ingest_p.add_argument("--source-dir", type=Path, required=True)
    ingest_p.add_argument("--inventory", type=Path, required=True)
    sub.add_parser("check-sources")
    sub.add_parser("status")
    prepare_p = sub.add_parser("prepare")
    prepare_p.add_argument("--id", required=True)
    prepare_p.add_argument("--max-words", type=int, default=1200)
    rec = sub.add_parser("record")
    rec.add_argument("--id", required=True)
    rec.add_argument("--state", choices=sorted(STATES), required=True)
    rec.add_argument("--note", required=True)
    sub.add_parser("audit-git")
    args = parser.parse_args()
    if args.command == "ingest":
        result = ingest(args.source_dir, args.inventory)
    elif args.command == "check-sources":
        result = check_sources()
    elif args.command == "prepare":
        if args.max_words < 100:
            raise ValueError("max-words must be >=100")
        result = prepare(args.id, args.max_words)
    elif args.command == "record":
        result = record(args.id, args.state, args.note)
    elif args.command == "audit-git":
        result = audit_git()
    else:
        result = status()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, FileNotFoundError) as error:
        print("error: " + str(error), file=sys.stderr)
        sys.exit(1)
