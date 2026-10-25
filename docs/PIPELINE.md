# 流水线、审稿状态与部署

给维护者。读者向说明在仓库根目录的 [README.md](../README.md)。

脚本只做目录导入、字幕分块、状态登记、源文件核对和静态 HTML 构建。不调用模型，不翻译，不删广告，也不判定科学对错。进行中的正文写在本机 `private/`，不进入 Git。已发布的中文精读在 `site/zh/`。

## 命令

下面的输入路径是示例，换成自己的资料目录。`inputs/` 被 Git 忽略。TXT 目录与同级的 `vtt/` 放在一起：`--source-dir inputs/final/txt` 时，字幕在 `inputs/final/vtt/`，文件名与 TXT 相同、扩展名为 `.vtt`。

```sh
python3 scripts/pipeline.py ingest --source-dir inputs/final/txt --inventory inputs/inventory-audit.csv
python3 scripts/pipeline.py check-sources
python3 scripts/pipeline.py prepare --id 001-nervous-system
python3 scripts/pipeline.py record --id 001-nervous-system --state drafting --note '开始阅读全文'
python3 scripts/pipeline.py status
python3 scripts/pipeline.py audit-git

python3 scripts/build_site.py --demo --out dist
python3 -m http.server 8000 --bind 127.0.0.1 --directory dist

python3 scripts/build_site.py --private --out private/site
python3 -m http.server 8001 --bind 127.0.0.1 --directory private/site

python3 scripts/build_site.py --published --out dist
```

`Makefile` 里有对应目标：`test`、`demo`、`private-site`、`published`、`status`、`check-sources`、`audit`。

## 各步做什么

`ingest` 读取盘点 CSV，核对 TXT 目录里的文件名与 CSV 一致、没有重复，并核对每个 TXT 的 SHA-256。同时解析同名 VTT 的全部 cue。结果写入 `catalog/episodes.json` 和 `private/local-config.json`。已有 `private/progress.json` 里的状态按节目 id 保留；新 id 记为 `pending`。若某份 VTT 的哈希与目录里已记录的不同，命令停止，不改这条基线。`ingest` 把 `source_url` 和 `video_id` 写成空，不根据标题猜测视频。

盘点 CSV 使用这些列：`文件名`、`SHA256`、`类型初筛`、`Guest Series`、`英文词数`、`索引日期_未独立核实`、`来源_来自索引`、`明确AMA节选`。类型取值为 `常规长节目/Guest Series 候选`、`Essentials 精编`、`AMA`、`现场问答`。

`check-sources` 按上次 `ingest` 写下的 `private/local-config.json`，复核全部 TXT 与 VTT 是否仍在、哈希是否一致。报告写到 `private/reports/source-integrity.json`。有缺失或改动时命令失败。

`prepare --id` 只接受长节目。它把 VTT cue 按词数切到 `private/chunks/{id}/`，并写 `private/source-maps/{id}.json`。默认每块最多 1200 个英文词，`--max-words` 不能小于 100。返回状态是 `input_prepared_only`。切块完成不等于稿件完成。

`record` 只接受长节目。`--note` 必填。它把状态写入 `private/progress.json`，并追加历史。

`status` 只打印长节目各状态的数量。若 `draft_complete` 或 `reviewed` 记录过正文 SHA-256，而当前 Markdown 已变，这一条在输出里显示为 `needs_revision`。`status` 不改文件。

`audit-git` 检查已跟踪路径是否落在允许的代码、文档、目录和模板范围内，并拒绝符号链接。它不阅读正文质量。

`docs/screenshot-home.png` 与 `docs/xiaohongshu.jpg` 是两项固定例外：索引必须为普通非可执行文件，索引和工作区的 SHA256 都须匹配 `PUBLIC_DOC_IMAGES` 中已核定的值。更换这两张图片需要同步审核指纹。其他图片、节目封面和原始转写仍不在允许范围内。`site/zh/` 下的 `.md` 与 `.json` 可以入库。

`build_site.py --demo` 不读取 `catalog/`、`private/` 或 `site/zh/`。输出必须在 `dist/` 内，默认就是 `dist/`。页面是虚构短文。

`build_site.py --private` 读取目录、`private/progress.json`、`private/articles/{id}.md` 和 `private/metadata/{id}.json`。输出必须在 `private/` 下面，且不能盖住文章、元数据、分块、来源映射或审稿目录。默认输出是 `private/site`。构建器只覆盖带有自己标记 `.huberman-build.json` 的旧输出；失败时留下上一份成功结果。构建器不联网，也不部署。

`build_site.py --published` 读取 `catalog/episodes.json` 和 `site/zh/{id}.md`、`site/zh/{id}.json`。不读取 `private/`，也不读取英文转写。输出必须在 `dist/` 内。有稿的条目按已审精读渲染；没有稿的条目只留在目录里。节目封面和人物肖像不在 `site/zh/` 中，页面使用占位肖像，封面显示「节目封面待核实」。

## 每次发布的顺序

1. 先 `git pull` 拉取 `main` 最新代码，保留已有修改。
2. 每篇同时更新 `site/zh/{id}.md` 与同名 `.json`，沿用现有字段；素材按当前用户授权及适用的版权、隐私约束处理。
3. 运行 `python3 scripts/build_site.py --published`，先解决报错。`--demo` 仅供测试。
4. 核对 README.md、README.en.md 及站点「关于」的实际已发布篇数；英文说明同步维护在 README.en.md。不要改 README 的版权声明或历史记录。
5. commit 后 push 到 `main`，确认 GitHub Actions 的「GitHub Pages」运行成功。
6. 按既有 Sites 流程同步构建结果到主站，保持原网址和公开范围。备用站使用 GitHub Pages 子路径，页面与订阅入口保持相对链接。
7. 核实两站正文及订阅地址，报告新增篇目、实际总数、Actions 和双站结果。

按用户最新要求，不再制作、更新或发送 Library 阅读包；旧包保留。新增精读的交付以 `site/zh/` 入库、GitHub Pages Actions 成功与原 Sites 主站上线为准。

`feed.xml`、`podcasts/huberman/feed.xml` 和 `tolson-rss.opml` 均由构建生成，不手工编辑。私有审稿记录和凭据不上传。此前对英文转写、音频、节目封面和人物照片的一概禁入限制已由用户撤销；这不要求批量上传，仍须按实际需要及适用权利处理。

## 本机文件

| 路径 | 作用 |
|---|---|
| `catalog/episodes.json` | 入库。稳定 id、英文标题、类别、节选标记、来源哈希。 |
| `private/articles/{id}.md` | 中文正文。`#` 标题，`##` 分章。 |
| `private/articles/{id}.glossary.json` | 本篇译名。构建脚本不读它。 |
| `private/metadata/{id}.json` | 展示标题、人物、来源、封面、与 H2 顺序一致的章节时间。字段见 [website.md](website.md#输入协议)。 |
| `private/reviews/{id}.author-review.json` | 作者覆盖自查。 |
| `private/reviews/{id}.independent-review.json` | 独立编辑对照，并绑定正文 SHA-256。 |
| `private/progress.json` | 逐篇状态和历史。 |

`source_url` 或章节时间未知时填 `null`。不要编造视频 id、首发日期或时间戳。metadata 里的章节标题必须与 Markdown 的 H2 完全一致，否则私有构建停止。

## 审稿状态

只允许这些状态：`pending`、`drafting`、`draft_complete`、`needs_revision`、`reviewed`。

```text
pending → drafting → draft_complete → reviewed
                ↘ needs_revision ↗
reviewed → needs_revision → drafting 或 draft_complete
```

从 `drafting` 可以直接记 `needs_revision`。不能从 `pending` 跳到 `draft_complete` 或 `reviewed`。

记 `draft_complete` 或 `reviewed` 时，正文须已存在，且基本汉字不少于 8000、H2 不少于 8。同时要有作者自查：全文读过，前、中、后都覆盖，发言人、不确定性和广告删除都标成完成，并有至少 8 条覆盖映射。这些数字只拦截空壳，不能代替对照原文。

记 `reviewed` 还要有独立审稿文件：`review_kind` 为 `independent_editorial_review`，`verdict` 为 `pass`，规定的覆盖项为真，且 `article_sha256` 等于当前 Markdown。`record` 会把当时的正文 SHA-256 写入进度。之后若改了正文，私有构建把该篇显示为「待修订」并去掉文章链接，不改写 `progress.json`。要再次标为已审，须重新审稿再 `record`。

写法要求见 [EDITORIAL.md](EDITORIAL.md)。页面验收见 [SITE_ACCEPTANCE.md](SITE_ACCEPTANCE.md)。

## 缺少全文的节目

优先处理已有完整 transcript 的未做节目，不用节目摘要替代全文。需要 STT 或付费 API 的节目先跳过，统一登记在本机 `private/STT-paid-backlog.json`，日后集中处理，不逐项打断用户。每条记录精确标题、官方链接、原节目日期、查过的转录来源及全文缺口或付费原因；时长只有核实后才填写，否则记为未知。未经新授权不采购、不转录、不调用付费 API。未检查过的节目不能直接标为需要 STT。403 只记访问未验证警告，不绕过限制。

## 部署检查

源码推送不会更新网页。线上站点目前是 [huberman-reading-001.tolsonhuddy.chatgpt.site](https://huberman-reading-001.tolsonhuddy.chatgpt.site)，已上线 135 篇中文精读。本地 `--private` 构建不是这条发布命令。

1. 跑测试，构建这次要发布的输出，并记下篇数。
2. 只上传构建结果里的 `index.html`、`feed.xml`、`tolson-rss.opml`、`podcasts/`、`episodes/`、CSS、JS，以及这次准备发布的 `covers/`、`portraits/`。保持相对路径。不要上传仓库根目录、原始字幕、审稿记录或隐藏配置。
3. 用现有静态托管导入该输出目录。构建器不创建域名，也不读取凭据。
4. 打开首页筛选、至少一篇正文、手机目录和来源链接，并在未登录状态下再看一遍。记录实际网址和篇数。本地预览通过不等于站点已更新。

推送到 `main` 时，GitHub Actions 用 `--published --base-url https://tolsonhuddy-collab.github.io/huberman-tolson-cn/` 构建 `site/zh/` 并发布到 GitHub Pages。页面里的样式和正文链接仍是相对路径，不使用 `<base>`，这样 `#section` 锚点在 `/huberman-tolson-cn/` 子路径下仍指向当前篇。这次构建的 Feed self、条目链接、OPML 和卡片地址指向备用站。为主站构建时不传 `--base-url`，那些链接仍指向主站。主站页面仍按上面的步骤手工上传。
