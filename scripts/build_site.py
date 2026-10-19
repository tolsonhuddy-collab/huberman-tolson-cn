#!/usr/bin/env python3
"""Build a synthetic demo or an owner-private static reading site (stdlib only)."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from html import escape
import json
import math
from pathlib import Path
import re
import shutil
from string import Template
import tempfile
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
KINDS = {"long_episode": "长节目", "essentials": "Essentials", "ama": "AMA", "live_qa": "现场问答"}
STATUSES = {"pending": "尚未开始", "drafting": "正在编写", "draft_complete": "完整初稿 · 待审核", "reviewed": "已审核", "needs_revision": "待修订"}
READY = {"draft_complete", "reviewed"}
ID = re.compile(r"[a-z0-9][a-z0-9-]{0,79}\Z")


def safe_url(value: object) -> str | None:
    """Allow ordinary http(s) links, never script/data/file URLs or credentials."""
    if not isinstance(value, str) or not value or value != value.strip():
        return None
    if re.search(r"[\x00-\x20\x7f\\]", value):
        return None
    try:
        parts = urlsplit(value)
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            return None
        if parts.username is not None or parts.password is not None:
            return None
        parts.port  # Invalid ports and unmatched IPv6 brackets raise ValueError.
    except ValueError:
        return None
    return value


def inline(text: str) -> str:
    """Small Markdown subset; unrecognized markup and all HTML remain escaped."""
    pattern = re.compile(r"\[([^\]\n]+)\]\(([^\s)]+)\)|\*\*([^*\n]+)\*\*|(?<!\*)\*([^*\n]+)\*(?!\*)|`([^`\n]+)`")
    chunks, end = [], 0
    for match in pattern.finditer(text):
        chunks.append(escape(text[end:match.start()]))
        if match[1] is not None:
            url = safe_url(match[2])
            chunks.append(f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{escape(match[1])}</a>' if url else escape(match[0]))
        else:
            tag, content = ("strong", match[3]) if match[3] is not None else ("em", match[4]) if match[4] is not None else ("code", match[5])
            chunks.append(f"<{tag}>{escape(content)}</{tag}>")
        end = match.end()
    chunks.append(escape(text[end:]))
    return "".join(chunks)


def blocks(text: str) -> str:
    result, paragraph, items, quotes, code = [], [], [], [], []
    list_type, fenced = None, False

    def flush() -> None:
        nonlocal list_type
        if paragraph:
            result.append("<p>" + inline(" ".join(paragraph)) + "</p>")
            paragraph.clear()
        if items:
            result.append(f"<{list_type}>" + "".join("<li>" + inline(item) + "</li>" for item in items) + f"</{list_type}>")
            items.clear()
            list_type = None
        if quotes:
            result.append("<blockquote><p>" + inline(" ".join(quotes)) + "</p></blockquote>")
            quotes.clear()

    for raw in text.splitlines() + [""]:
        line = raw.strip()
        if line.startswith("```"):
            flush()
            if fenced:
                result.append("<pre><code>" + escape("\n".join(code)) + "</code></pre>")
                code.clear()
            fenced = not fenced
            continue
        if fenced:
            code.append(raw)
            continue
        if not line:
            flush()
            continue
        heading = re.match(r"^#{3,6}\s+(.+)$", line)
        item = re.match(r"^(?:([-*+])\s+|\d+\.\s+)(.+)$", line)
        if heading:
            flush()
            result.append("<h3>" + inline(heading[1]) + "</h3>")
        elif re.fullmatch(r"---+", line):
            flush()
            result.append("<hr>")
        elif item:
            typ = "ul" if item[1] else "ol"
            if paragraph or quotes or (list_type and list_type != typ):
                flush()
            list_type = typ
            items.append(item[2])
        elif line.startswith("> "):
            if paragraph or items:
                flush()
            quotes.append(line[2:])
        else:
            if items or quotes:
                flush()
            paragraph.append(line)
    if fenced:
        result.append("<pre><code>" + escape("\n".join(code)) + "</code></pre>")
    return "\n".join(result)


def parse_article(markdown: str) -> tuple[str, str, list[tuple[str, str]]]:
    # Editorial files may carry private source paths in YAML-style frontmatter.
    # Strip it as opaque metadata; never render it and do not require a YAML parser.
    lines = markdown.lstrip("\ufeff").strip().splitlines()
    if lines and lines[0].strip() == "---":
        closing = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
        if closing is None:
            raise ValueError("Unclosed article frontmatter")
        lines = lines[closing + 1:]
    title, intro, sections, body = "", [], [], []
    section_title = None
    fenced = False
    for line in lines:
        if line.strip().startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("# ") and not title and section_title is None:
            title = line[2:].strip()
        elif not fenced and line.startswith("## "):
            if section_title is not None:
                sections.append((section_title, "\n".join(body)))
            section_title, body = line[3:].strip(), []
        elif section_title is None:
            intro.append(line)
        else:
            body.append(line)
    if section_title is not None:
        sections.append((section_title, "\n".join(body)))
    if not sections:
        raise ValueError("Article must contain H2 sections")
    return title, "\n".join(intro).strip(), sections


def inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def private_file(root: Path, relative: str) -> Path:
    if not inside((root / "private").resolve(), root.resolve()):
        raise ValueError("private/ cannot point outside the project")
    path = (root / relative).resolve()
    if not inside(path, (root / "private").resolve()):
        raise ValueError(f"Private input is outside private/: {relative}")
    return path


def output_path(root: Path, out: Path, private: bool) -> Path:
    raw = out if out.is_absolute() else root / out
    if raw.is_symlink():
        raise ValueError("Output cannot be a symlink")
    result = raw.resolve()
    allowed = (root / ("private" if private else "dist")).resolve()
    if not inside(allowed, root):
        raise ValueError("Output base cannot point outside the project")
    if not inside(result, allowed) or (private and result == allowed):
        raise ValueError("Private builds must stay below private/; demo builds must stay inside dist/")
    protected = [root / name for name in ("private/articles", "private/metadata", "private/handoff", "private/chunks", "private/source-maps", "private/reviews")]
    if any(inside(result, p.resolve()) or inside(p.resolve(), result) for p in protected):
        raise ValueError("Output overlaps a private input directory")
    if result.exists() and (not result.is_dir() or (any(result.iterdir()) and not (result / ".huberman-build.json").is_file())):
        raise ValueError("Refusing to overwrite a directory not created by this builder")
    return result


def read_private(root: Path) -> tuple[list[dict], dict, dict, dict]:
    catalog = json.loads((root / "catalog/episodes.json").read_text(encoding="utf-8"))
    episodes = catalog.get("episodes")
    if not isinstance(episodes, list):
        raise ValueError("catalog/episodes.json must contain an episodes list")
    progress = json.loads(private_file(root, "private/progress.json").read_text(encoding="utf-8")).get("episodes", {})
    if not isinstance(progress, dict):
        raise ValueError("progress.episodes must be an object")
    metadata, articles, seen = {}, {}, set()
    for ep in episodes:
        episode_id = ep.get("id", "")
        if not isinstance(episode_id, str) or not ID.fullmatch(episode_id) or episode_id in seen:
            raise ValueError("Episode IDs must be unique safe slugs")
        if ep.get("kind") not in KINDS:
            raise ValueError(f"Unknown episode kind: {episode_id}")
        seen.add(episode_id)
        state = progress.get(episode_id, {})
        if not isinstance(state, dict) or state.get("status", "pending") not in STATUSES:
            raise ValueError(f"Invalid progress state: {episode_id}")
        md_path = private_file(root, f"private/articles/{episode_id}.md")
        meta_path = private_file(root, f"private/metadata/{episode_id}.json")
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if not isinstance(meta, dict) or meta.get("id") != episode_id:
                raise ValueError(f"Metadata ID mismatch: {episode_id}")
            metadata[episode_id] = meta
        if state.get("status") in READY and md_path.is_file():
            md_bytes = md_path.read_bytes()
            metrics = state.get("metrics")
            recorded_sha = metrics.get("sha256") if isinstance(metrics, dict) else None
            if recorded_sha is not None and recorded_sha != hashlib.sha256(md_bytes).hexdigest():
                # A recorded review applies to one exact file version. Downgrade
                # this build's state only; the source progress file stays read-only.
                progress[episode_id] = {**state, "status": "needs_revision"}
                continue
            if episode_id not in metadata:
                raise ValueError(f"Completed article lacks metadata: {episode_id}")
            articles[episode_id] = md_bytes.decode("utf-8")
    return episodes, progress, metadata, articles


def demo_data() -> tuple[list[dict], dict, dict, dict]:
    """Fictional text only. Never inspect catalog/, private/, or the handoff bundle."""
    ep = {"id": "demo-reading", "title_en": "A Fictional Conversation About Reading", "kind": "long_episode", "explicit_excerpt": False}
    meta = {"id": ep["id"], "title_zh": "读一篇长文，留出一点时间", "title_en": ep["title_en"], "dek": "这是为测试版式创作的虚构文章，不来自任何一期节目。", "hosts": [{"name": "示例编辑", "role": "虚构人物", "bio": "用占位人物测试阅读页面。"}], "source_url": None, "sections": [{"title": "从一个小问题开始", "source_seconds": None}, {"title": "为理解留出空间", "source_seconds": None}], "editor_note": "纯版式演示。人物、标题与正文均为本项目原创的虚构占位内容。"}
    md = "# 读一篇长文，留出一点时间\n\n这篇短文只用来查看文字在页面上的样子。它不对应真实节目，也不陈述科学结论。\n\n## 从一个小问题开始\n\n阅读长文时，可以先找一个自己关心的问题。带着这个问题继续读，前后段落的联系会更容易看清。这里的文字只是版式占位，长度也不代表真实精读的标准。\n\n## 为理解留出空间\n\n段落之间留一点空白，目录放在手边。窄屏收起目录，读者仍可从文章上方跳到需要的位置。字号与底色也可以按习惯调整。\n"
    pending = {"id": "demo-excerpt", "title_en": "Fictional AMA Excerpt — Not Yet Written", "kind": "ama", "explicit_excerpt": True}
    return [ep, pending], {ep["id"]: {"status": "reviewed"}}, {ep["id"]: meta}, {ep["id"]: md}


def source_marker(source: str | None, seconds: object) -> str:
    if seconds is None:
        return ""
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
        raise ValueError("source_seconds must be a finite nonnegative number or null")
    sec = int(seconds)
    hours, remainder = divmod(sec, 3600)
    minute, second = divmod(remainder, 60)
    stamp = f"{hours}:{minute:02}:{second:02}" if hours else f"{minute:02}:{second:02}"
    if source:
        parts = urlsplit(source)
        host = (parts.hostname or "").lower()
        if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
            query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in {"t", "start"}]
            target = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query + [("t", str(sec))]), parts.fragment))
            return f'<a href="{escape(target, quote=True)}" target="_blank" rel="noopener noreferrer" aria-label="回听原节目 {stamp}">{stamp} <span>↗</span></a>'
    return f'<span class="chapter-time" title="本地 VTT 定位，未独立核对原音">{stamp}</span>'


def chapter_provenance(body: str) -> tuple[str, str]:
    """Move only a standalone opening timestamp paragraph, never prose notes."""
    paragraphs = re.split(r"\n[ \t]*\n", body.lstrip(), maxsplit=1)
    first = paragraphs[0].strip()
    stamp = r"\d{2}:\d{2}:\d{2}(?:\.\d{3})?"
    bracketed = re.fullmatch(r"〔VTT\s*定位[：:][^〕\r\n]*〕", first)
    plain = re.fullmatch(r"本地(?:时间轴|字幕定位)[：:]\s*" + stamp + r"(?:\s*[–—\-－~～至]\s*" + stamp + r")?\s*起?[。.]?", first)
    if (bracketed or plain) and re.search(stamp, first):
        return paragraphs[1] if len(paragraphs) == 2 else "", first
    return body, ""


def speakers_html(root: Path, staging: Path, episode_id: str, hosts: object, private: bool) -> str:
    if not hosts:
        return ""
    if not isinstance(hosts, list):
        raise ValueError("hosts must be a list")
    strips = []
    for index, host in enumerate(hosts):
        name = str(host.get("name", "主讲人"))
        portrait, credit, actual = "../portrait-placeholder.svg", "头像占位 · 未展示真人肖像", False
        if private and host.get("portrait"):
            path = private_file(root, str(host["portrait"]))
            if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"} or not path.is_file():
                raise ValueError("Private portrait must be an existing JPG, PNG, or WebP under private/")
            target = f"{episode_id}-{index}{path.suffix.lower()}"
            (staging / "portraits").mkdir(exist_ok=True)
            shutil.copyfile(path, staging / "portraits" / target)
            portrait, credit, actual = "../portraits/" + target, str(host.get("portrait_credit", "本地参考头像；分发权限尚未确认")), True
        alt = name if actual else name + "的头像占位"
        strips.append(f'<section class="speaker-strip" aria-label="本期主讲人"><div class="portrait-link"><img class="speaker-portrait" src="{portrait}" width="350" height="350" alt="{escape(alt, quote=True)}"></div><div class="speaker-info"><span class="speaker-kicker">{escape(str(host.get("role", "本期主讲人")))}</span><h2>{escape(name)}</h2><p>{escape(str(host.get("bio", "")))}</p><span class="portrait-credit">{escape(credit)}</span></div></section>')
    return "\n".join(strips)


def display_section_title(title: str, number: int) -> str:
    """Hide source heading ordinals while retaining raw titles for validation."""
    numeric = re.match(r"^\s*(\d{1,3})(?:[.．、)）]\s+|\s+)(\S.*)$", title)
    if numeric and int(numeric[1]) == number:
        return numeric[2].strip()
    chinese = re.match(r"^\s*[一二三四五六七八九十百零〇两]+[、.．]\s*(\S.*)$", title)
    return chinese[1].strip() if chinese else title


def render_article(root: Path, staging: Path, ep: dict, state: dict, meta: dict, md: str, private: bool) -> str:
    title, intro, sections = parse_article(md)
    section_meta = meta.get("sections", [])
    if section_meta and (not isinstance(section_meta, list) or any(not isinstance(s, dict) for s in section_meta) or [s.get("title") for s in section_meta] != [t for t, _ in sections]):
        raise ValueError(f"Section metadata must match Markdown H2 titles and order: {ep['id']}")
    source = safe_url(meta.get("source_url"))
    article, source_details = [], [blocks(intro)] if intro else []
    for number, (section_title, body) in enumerate(sections, 1):
        sec = section_meta[number - 1].get("source_seconds") if section_meta else None
        shown_title = display_section_title(section_title, number)
        reading_body, provenance = chapter_provenance(body)
        if provenance:
            source_details.append(f'<div class="chapter-source"><h3>{number:02} {escape(shown_title)}</h3>{blocks(provenance)}</div>')
        article.append(f'<section id="section-{number}" class="chapter"><div class="chapter-kicker"><span>{number:02}</span>{source_marker(source, sec)}</div><h2>{escape(shown_title)}</h2>{blocks(reading_body)}</section>')
    visible_text = "\n".join([title, intro] + [part for pair in sections for part in pair])
    count = len(re.findall(r"[\u4e00-\u9fff]", visible_text))
    source_note = "独立整理的非官方中文精读。原始转写与中文全文仅供本地私有审阅，尚未获得公开分发确认。"
    if not private:
        source_note = "本页为原创虚构版式演示，不对应真实节目；没有使用节目转写、翻译全文或真人肖像。"
    if source is None:
        source_note += " 原节目链接尚未核验，未生成回听链接。"
    title_zh = str(meta.get("title_zh") or title or ep["title_en"])
    values = {
        "page_title": escape(title_zh + " · Huberman Lab 中文精读", quote=True), "description": escape(str(meta.get("dek") or "中文长文阅读"), quote=True),
        "title_zh": escape(title_zh), "title_en": escape(str(meta.get("title_en") or ep["title_en"])),
        "dek": '<p class="dek">' + escape(str(meta["dek"])) + "</p>" if meta.get("dek") else "",
        "edition": "本地私有审阅" if private else "虚构版式演示", "status": STATUSES[state.get("status", "pending")],
        "episode_meta": f'<span>{KINDS[ep["kind"]]}</span><span>{escape(STATUSES[state.get("status", "pending")])}</span><span>约 {count:,} 字 · 阅读 {max(1, math.ceil(count / 450))} 分钟</span>',
        "toc": "".join(f'<a href="#section-{i}"><span>{i:02}</span>{escape(display_section_title(t, i))}</a>' for i, (t, _) in enumerate(sections, 1)),
        "mobile_toc": "".join(f'<a href="#section-{i}">{i:02} {escape(display_section_title(t, i))}</a>' for i, (t, _) in enumerate(sections, 1)),
        "speakers": speakers_html(root, staging, ep["id"], meta.get("hosts", []), private), "article": "\n".join(article),
        "editor_note": escape(str(meta.get("editor_note") or "依据本地英文稿件整理，待逐段核验。")),
        "reading_note": "依据英文原稿编译，编辑与来源说明见文末。" if private else "原创虚构版式演示，人物与正文均为占位内容。",
        "source_details": "\n".join(source_details),
        "source_note": escape(source_note),
        "source_tab": f'<a class="source-tab" href="{escape(source, quote=True)}" target="_blank" rel="noopener noreferrer">原节目 ↗</a>' if source else "",
        "source_link": f'<a href="{escape(source, quote=True)}" target="_blank" rel="noopener noreferrer">原节目来源 ↗</a>' if source else "",
    }
    return Template((root / "web/article.html").read_text(encoding="utf-8")).substitute(values)


def render_catalog(root: Path, episodes: list[dict], progress: dict, metadata: dict, articles: dict, private: bool) -> str:
    cards = []
    # Stable grouping keeps readable work visible while preserving source order
    # inside each group. Display numbers are positions, never episode numbers.
    ordered = sorted(episodes, key=lambda ep: not (ep["id"] in articles and progress.get(ep["id"], {}).get("status") in READY))
    for number, ep in enumerate(ordered, 1):
        episode_id = ep["id"]
        meta = metadata.get(episode_id, {})
        status = progress.get(episode_id, {}).get("status", "pending")
        readable = episode_id in articles and status in READY
        state_text = STATUSES[status] if not (status in READY and not readable) else "稿件文件缺失 · 暂不可读"
        title = str(meta.get("title_zh") or ep["title_en"])
        host_names = " · ".join(str(h.get("name", "")) for h in meta.get("hosts", []))
        search = " ".join((title, ep["title_en"], host_names, KINDS[ep["kind"]])).lower()
        title_html = f'<a href="episodes/{episode_id}.html">{escape(title)}<span aria-hidden="true"> ↗</span></a>' if readable else escape(title)
        badges = f'<span>{KINDS[ep["kind"]]}</span>'
        if ep.get("guest_series"):
            badges += '<span>Guest Series</span>'
        if ep.get("explicit_excerpt"):
            badges += '<span class="excerpt-badge">仅节选</span>'
        english = f'<p class="card-english" lang="en">{escape(ep["title_en"])}</p>' if title != ep["title_en"] else ""
        portrait = "portrait-placeholder.svg"
        hosts = meta.get("hosts", [])
        if private and readable and hosts and hosts[0].get("portrait"):
            suffix = Path(str(hosts[0]["portrait"])).suffix.lower()
            portrait = f"portraits/{episode_id}-0{suffix}"
        actual_portrait = portrait != "portrait-placeholder.svg"
        alt = str(hosts[0].get("name", "本期主讲人")) if actual_portrait else "头像占位"
        portrait_label = '<span class="card-portrait-label">主持人</span>' if actual_portrait and len(hosts) > 1 else ""
        cards.append(f'<article class="episode-card" data-kind="{ep["kind"]}" data-availability="{"readable" if readable else "pending"}" data-search="{escape(search, quote=True)}"><span class="card-number" title="目录顺序 {number}；不是原节目期号" aria-label="目录顺序 {number}">{number:03}</span><div class="card-content"><div class="card-category">{badges}</div><h3>{title_html}</h3>{english}<p class="card-people">{escape(host_names)}</p><p class="card-status {"is-readable" if readable else ""}">{escape(state_text)}</p></div><div class="card-portrait-wrap"><img class="card-portrait" src="{escape(portrait, quote=True)}" alt="{escape(alt, quote=True)}" width="52" height="60" loading="lazy">{portrait_label}</div></article>')
    counts = Counter(ep["kind"] for ep in episodes)
    readable_count = len(articles)
    notice = "本地私有工作台。完整初稿仍需内容核验；未完成节目仅列目录。全文与人物肖像尚未获准公开分发。" if private else "纯版式演示：目录、人物与短文均为虚构占位，不代表真实节目或制作进度。"
    values = {"description": escape(notice, quote=True), "notice": escape(notice), "total": str(len(episodes)), "cards": "\n".join(cards),
        "counts": escape(" · ".join(f"{KINDS[k]} {counts[k]}" for k in KINDS if counts[k]) + f" · 已有本地稿 {readable_count}"),
        "kind_options": "".join(f'<option value="{kind}">{label}</option>' for kind, label in KINDS.items()),
        "footer_note": "非官方独立编辑项目。当前构建仅供私有审阅，未部署到公开网站。" if private else "代码可以独立部署为静态演示。真实节目全文、原始字幕与真人头像不包含在演示中。"}
    return Template((root / "web/index.html").read_text(encoding="utf-8")).substitute(values)


def build_site(root: Path, out: Path, private: bool = False) -> dict:
    root = root.resolve()
    destination = output_path(root, out, private)
    episodes, progress, metadata, articles = read_private(root) if private else demo_data()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".huberman-build-", dir=destination.parent) as tmp:
        staging = Path(tmp) / "site"
        (staging / "episodes").mkdir(parents=True)
        for name in ("style.css", "app.js", "qiaomu-LICENSE.txt", "portrait-placeholder.svg"):
            shutil.copyfile(root / "web" / name, staging / name)
        for ep in episodes:
            if ep["id"] in articles:
                html = render_article(root, staging, ep, progress[ep["id"]], metadata[ep["id"]], articles[ep["id"]], private)
                (staging / "episodes" / (ep["id"] + ".html")).write_text(html, encoding="utf-8")
        (staging / "index.html").write_text(render_catalog(root, episodes, progress, metadata, articles, private), encoding="utf-8")
        manifest = {"schema_version": 1, "mode": "private" if private else "synthetic_demo", "episode_count": len(episodes), "article_count": len(articles), "deployed": False}
        (staging / ".huberman-build.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        if destination.exists():
            shutil.rmtree(destination)
        staging.rename(destination)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--demo", action="store_true", help="Build only fictional demo content; no private inputs")
    modes.add_argument("--private", action="store_true", help="Build owner-private articles below private/")
    parser.add_argument("--out", type=Path, help="Output path; defaults to dist or private/site")
    args = parser.parse_args()
    try:
        manifest = build_site(ROOT, args.out or Path("private/site" if args.private else "dist"), args.private)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(1, f"Build failed: {error}\n")
    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
