# Development

Reader-facing notes are in the [README](../README.md). Quick start, how the scripts fit together, and the repository tree are in [开发说明.md](开发说明.md).

## Repository and build

This repository holds catalog metadata (370 entries), the published Chinese essays in `site/zh/` (one Markdown file and one metadata file per essay), a stdlib Python site builder, and bookkeeping scripts. English transcripts and original podcast files are not in Git. `python3 scripts/build_site.py --demo --out dist` builds a fictional layout only. `python3 scripts/build_site.py --published --out dist` builds the committed essays.

The backup site is built from those essays. Its feed links point at the backup site. A primary-site build omits `--base-url` and keeps primary-site links.

## What this is

Chinese close readings of [Huberman Lab](https://www.hubermanlab.com/) interviews. Essays follow the original order and keep the core arguments, mechanisms, examples, and research limits. They drop ads, small talk, and repetition. Interviews mark who is speaking. Places where the transcript does not line up are noted.

Examples: [神经系统如何工作，又如何被经验改变](https://huberman-reading-001.tolsonhuddy.chatgpt.site/episodes/001-nervous-system.html), [好睡眠从白天开始](https://huberman-reading-001.tolsonhuddy.chatgpt.site/episodes/002-master-sleep.html).

1. **Catalog.** The repository lists 370 episode records: 279 long episodes (including 16 Guest Series), 62 Essentials, 19 AMAs, and 10 live Q&As. Filter by Chinese title, English title, person, and kind, or show only essays that exist or entries still waiting.
2. **Chinese essays.** Long essays that follow the episode structure, one page each. The published count is in the [README](../README.md). Other entries are catalog only.
3. **Static reading pages.** A chapter list on the right on desktop, collapsible on phones. Type size 16–24px, light or dark background, and reading progress on the page. Editing and source notes at the end are collapsed by default.

## Capabilities

| Capability | What it does |
|---|---|
| Chinese essays | Keep the arguments, mechanisms, examples, and research limits. Drop ads, small talk, and repetition. Interviews name the speaker. Transcript doubts stay in the text. |
| Catalog | 370 records in `catalog/episodes.json`. Cards with an essay link to their own page. Cards without one show the title and kind only. |
| Filters | The home page matches Chinese title, English title, person, and kind, and can show only published essays or entries still waiting. The featured block hides while a filter is on. |
| Reading page | The desktop chapter list highlights with scrolling. The phone list collapses. Type size and background are stored on the device. Source notes at the end can be expanded. |
| Sources | Verified episode links are at the end of the essay. An unverified video address is left blank, not invented. Chapter times come from the local subtitles. |
| Local build | Python 3.10+ standard library. `--demo` is a fictional layout. `--published` builds the essays in `site/zh/`. English transcripts are not in Git. |
| Feeds | Each build rewrites the full-text Atom feed (every readable essay in that build), `podcasts/huberman/feed.xml`, and `tolson-rss.opml`. |

## Limits

- A clone can run the tests, `--demo`, and `--published`. Published Chinese essays are in `site/zh/`. English transcripts, episode covers, portraits, and hosting credentials are outside Git. `--private` needs a local `private/` directory.
- `prepare` splits subtitles for long episodes only. Essentials, AMAs, and live Q&As are catalog entries for now. 16 AMAs are marked as excerpts.
- Index dates in the catalog are not independently verified and are not episode publish dates. Chapter times come from the local subtitles and are not a claim of second-by-second alignment with the audio.
- A push to `main` updates the GitHub Pages backup. The primary site still follows its existing hosting process. The live site is the authority for how many essays are online. The current count is in the [README](../README.md).

## Contributing

- Typos, names, numbers, or a clear misreading: open an issue with the essay title or page address.
- Fixes to the build, the reading page, or the pipeline: open a pull request. `python3 scripts/pipeline.py audit-git` can be run before submitting.
- Do not commit original audio, English transcripts, episode images, or credentials. Published Chinese essays belong in `site/zh/`.
