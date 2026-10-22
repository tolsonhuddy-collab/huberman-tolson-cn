# 静态阅读网站

网站代码位于 `web/`，构建器为 `scripts/build_site.py`。它复用交接包中已经认可的杂志阅读模板，保留暖纸色长文、人物栏、中文标题与英文原题、字号设置、深浅底色、阅读进度、桌面右侧目录和手机折叠目录。新增首页的节目类别、阅读状态和本地搜索。原模板的 MIT 声明保存在 `web/qiaomu-LICENSE.txt`。

首页采用报刊式层级：大报头“Huberman Lab 中文精读”，下方一行“把一场长谈，读成一篇长文。”，紧凑的搜索、阅读范围及类别筛选，左侧真实 16:9 节目封面与右侧编辑标题，随后为三栏图文目录。手机将精选图文上下排列、目录改为单栏。筛选按关键词、类别、阅读状态同时匹配；有筛选时隐藏精选，清空后恢复。范围按钮同步 `aria-pressed`，空结果显示可恢复提示。

新读者默认20px，字号仍可在16–24px之间按2px调整；已有用户保存的字号与深浅主题继续生效。浅色背景为暖纸色`#f6f3ec`，正文为`#343833`；深色使用对应纸面与墨色。桌面正文行高1.95，640px及以下为1.9，680px正文宽度与手机20px边距保持。

审核完成的阅读页面不展示“已审核”或“已校读”标签；首页使用“中文精读”计数，目录卡片、文章元信息和阅读底栏不展示完成审核状态。内部逐篇审核与交付门槛保留，私有工作台中的未审核初稿仍明确提示“完整初稿 · 待审核”。

首页优先排列已有本地完整初稿或已审核稿，其余节目随后列出；组内保留原目录顺序，不修改目录输入文件。目录数字仅表示当前页面的位置，不代表原节目期号。章节标题中的既有阿拉伯或中文编号只在显示时移除，避免与目录及章节标号重复；元信息仍与 Markdown 原始标题严格匹配。

页首只显示一句简短编译说明。Markdown 标题与首个 H2 之间的编辑和来源文字、详细编辑说明，以及每章开头单独成段的 VTT/本地时间轴定位，保存在文末默认折叠的“编辑与来源说明”中；正文不重复这些制作信息。若定位与科学正文混在同一段，整段留在阅读区，避免误折叠。章节保留小号时间标记，原稿疑误与研究限制的正文注仍留在原处。目录缩略图的 alt 只标照片中的人物，多参与者姓名保留在卡片正文；使用主持人单人照片的来宾卡片另有“主持人”标注。最终验收项见 [SITE_ACCEPTANCE.md](SITE_ACCEPTANCE.md)。

项目源码仓库为 [tolsonhuddy-collab/huberman-tolson-cn](https://github.com/tolsonhuddy-collab/huberman-tolson-cn)。本机目录名仍为 `huberman-lab-cn`。构建器不会联网、调用模型、创建仓库或执行部署。

## 构建与本机预览

依赖 Python 3.10 或更新版本的标准库，无需 `pip install`、Node、打包器或收费 API。可选 Node 用于 JavaScript 健壮性与筛选组合测试。

```sh
python3 scripts/build_site.py --demo --out dist
python3 -m http.server 8000 --bind 127.0.0.1 --directory dist
```

浏览器访问 `http://127.0.0.1:8000`。演示构建只采用脚本内原创的虚构标题、人物和短文，不读取 `catalog/`、`private/`、`site/zh/`、交接包或真人肖像。虚构短文仅测试版式，不是精读成稿。`dist/` 是构建产物，不应提交 Git。

已发布精读：

```sh
python3 scripts/build_site.py --published --out dist
```

它只读 `catalog/episodes.json` 与 `site/zh/`，输出到 `dist/`。页面用与主站相同的读者文案。Feed 链接仍指向主站。`site/zh/` 不含节目封面和人物肖像，构建结果使用占位肖像。

私有阅读稿使用独立命令：

```sh
python3 scripts/build_site.py --private --out private/site
python3 -m http.server 8001 --bind 127.0.0.1 --directory private/site
```

本地预览地址是 `http://127.0.0.1:8001`。私有输出必须在项目的 `private/` 下，不能覆盖文章、元信息、交接包、来源映射、分块或审阅目录。构建器只替换带有自身构建标记的既有输出目录，错误输入不会替换上一份有效页面。不要将项目根目录作为 HTTP 服务目录。

构建结果为普通 HTML、CSS、JavaScript 和本地图片，采用相对路径。构建器本身不部署、不购买或绑定域名。代码以 MIT 许可，仅限代码。中文精读与原始转写不在该许可内。`--private` 是本地工作台，和已上线 84 篇中文精读不是同一份清单。`--published` 构建仓库 `site/zh/` 里的这 84 篇。部署步骤见 [PIPELINE.md](PIPELINE.md)。

每次构建还会重写 `feed.xml`、`podcasts/huberman/feed.xml` 和 `tolson-rss.opml`，并用标准库确认这些 XML 可以解析。`feed.xml` 是 Atom，收录本次构建中最近 20 篇可读精读的全文（`content type="html"`），含稳定 id、标题、主站页面链接、published、updated、类别，以及已核验时的原节目链接。Tolson-RSS 按播客分文件，目前只有 Huberman；OPML 列出这些 Feed。首页和正文的 `<head>` 用相对地址自动发现 Atom，因此主站根路径和 GitHub Pages 的 `/huberman-tolson-cn/` 子路径都能找到订阅。Feed 里的链接固定指向主站 https://huberman-reading-001.tolsonhuddy.chatgpt.site 。

## 输入协议

私有构建读取：

- `catalog/episodes.json`：对象中的 `episodes` 列表，使用 `id`、`title_en`、`kind`、`guest_series` 与 `explicit_excerpt`。类别为 `long_episode`、`essentials`、`ama`、`live_qa`。
- `private/progress.json`：`episodes[id].status` 为 `pending`、`drafting`、`draft_complete`、`reviewed` 或 `needs_revision`。
- `private/articles/{id}.md`：可选 H1，首个 H2 之前为编辑与来源说明区，H2 划分自然正文；读者导语应放首节或使用 `dek`。保留段落、H3、粗体、引用、列表及 http(s) 链接。原始 HTML 一律转义。开头完整的 `---` frontmatter 被剥离，里面的私有来源路径不会进入页面。
- `private/metadata/{id}.json`：以下字段。只有正文存在且进度为 `draft_complete` 或 `reviewed` 时，首页才提供文章链接。`draft_complete` 明确显示“完整初稿 · 待审核”，不能据此当作审核通过。

内容流水线的 `record` 操作会在进度记录中写入 `metrics.sha256`，把状态绑定到当时 Markdown 文件的完整字节。网站构建会核对这项哈希：`draft_complete` 或 `reviewed` 的稿件若已被修改，本次构建显示“待修订”并撤下文章链接，其他稿件不受影响，构建器不修改原始 `progress.json`。未带 `metrics.sha256` 的既有或虚构输入仍按原状态处理，以兼容旧记录和演示测试；正式流水线应使用带哈希的记录。

```json
{
  "id": "episode-slug",
  "title_zh": "中文标题",
  "title_en": "Original episode title",
  "dek": "可选导语",
  "hosts": [
    {
      "name": "人物姓名",
      "role": "主讲人或访谈者",
      "bio": "简要身份信息",
      "portrait": null,
      "portrait_credit": null
    }
  ],
  "source_url": null,
  "cover": {
    "path": "private/assets/covers/episode-slug.jpg",
    "source_url": "https://example.org/verified-official-full-episode",
    "alt": "节目封面：已核实的完整节目标题",
    "verified": false
  },
  "homepage_featured": false,
  "homepage_dek": "可选的首页精选短介绍",
  "sections": [
    {"title": "与 Markdown H2 完全一致的标题", "source_seconds": null}
  ],
  "editor_note": "编辑说明与原稿限制",
  "source_intro": "可选：当前已核实的来源说明，保留尚未完成原音对齐等限定"
}
```

`sections` 可留空，届时没有章节来源时间。提供该列表时，标题、数量与顺序必须严格匹配 Markdown H2，否则停止构建。时间只使用显式输入的非负秒数，不推测节目位置。已核验的 YouTube 节目 URL 可生成该节目自己的时间链接；其他来源只显示小号本地时间定位，提示与完整声明说明其核验范围，不推测第三方站点的定位语法。来源 URL 缺失或不安全时不生成原节目链接。

`source_intro` 是可选文本，只替换页面文末原有的稿前来源说明；省略时保留 Markdown 中的原说明。它用于在节目身份补充核实后更新读者可见的来源信息，不修改已审核稿、章节正文或审稿哈希。应逐条保留原说明中的实质限制，不能将来源身份核验写成原音或科学事实核验，也不应出现制作协调术语。

正文源码中的绝对路径只用于本地工作，不能写入 `source_url`。来源链接仅接受无凭据的 http(s) URL。人物头像默认显示本项目的中性占位图；`portrait` 仅能指向 `private/` 内已存在的 JPG、PNG 或 WebP，相对项目根目录填写。私有构建会复制到私有输出；演示构建不复制任何真人头像。

节目封面与人物头像分别管理。封面必须先核对官方完整期页面、实际图片 URL、尺寸和画面题字，记录证据后才能将 `cover.verified` 设为 `true`。构建器只复制 `private/` 内已有的 JPG、PNG 或 WebP，输出为相对路径 `covers/{id}.*`；未验证封面保留“节目封面待核实”文字，不拿通用头像或 Essentials 短版替代。首页精选还要求文章状态为 `reviewed`，`homepage_featured` 仅在符合条件者中优先排序。演示构建不读取或复制任何私有节目封面。

官方节目身份与原音对齐是两项证据。已核实的官方节目页面可直接填入 `source_url`，此时文章提供来源链接，章节仍显示带“未独立核对原音”提示的本地字幕时间。只有明确提供已核实的 YouTube URL 时才生成视频时间链接；这本身不证明原音与字幕偏移已经校准。

## 托管交接与发布范围

部署步骤、审稿状态和发布检查见 [PIPELINE.md](PIPELINE.md)。不导入项目根目录、源字幕、审阅记录或任何隐藏配置。静态输出不依赖本地 Python 服务，托管环境须保留 `episodes/`、`covers/`、`portraits/` 相对目录以及 CSS、JS。Git 推送和本地预览都不是远程部署成功。

代码与正文的许可分开，见 [CONTENT_RIGHTS.md](../CONTENT_RIGHTS.md)。构建器不部署、不购买域名、不读取凭据。

## 检查

```sh
python3 -m unittest discover -s tests -p 'test_site.py' -v
```

测试覆盖两篇不同节目各自的标题、来源与时间戳，未知链接保持缺失，章节错配失败，哈希失配的完成稿或已审核稿自动显示待修订且不改写源记录，未完成稿不出链接，AMA 节选和其他类别标记，目录锚点及本地资源，HTML/URL 转义，frontmatter 隐藏，私有路径边界，演示与私有全文隔离，以及目录页没有文章控件时 JavaScript 仍可运行。回归检查也覆盖来源证据转入默认折叠区后完整保留、正文科学限制注不被移走，以及单人照片 alt 与多参与者文字的区别。

程序测试不替代内容验收。是否覆盖原节目前中后、论证与例子是否完整、转写疑点是否标注、双人访谈的发言人是否清楚，仍由逐篇编辑记录判断。网站不会把这些编辑判断自动设为通过。
