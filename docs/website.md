# 静态阅读网站

网站代码位于 `web/`，构建器为 `scripts/build_site.py`。它复用交接包中已经认可的杂志阅读模板，保留白底长文、人物栏、中文标题与英文原题、字号设置、深浅底色、阅读进度、桌面右侧目录和手机折叠目录。新增首页的节目类别、阅读状态和本地搜索。原模板的 MIT 声明保存在 `web/qiaomu-LICENSE.txt`。

首页优先排列已有本地完整初稿或已审核稿，其余节目随后列出；组内保留原目录顺序，不修改目录输入文件。左侧数字仅表示当前页面的目录位置，不代表原节目期号。章节标题中的既有阿拉伯或中文编号只在显示时移除，避免与目录及章节标号重复；元信息仍与 Markdown 原始标题严格匹配。

页首只显示一句简短编译说明。Markdown 标题与首个 H2 之间的编辑和来源文字、详细编辑说明，以及每章开头单独成段的 VTT/本地时间轴定位，保存在文末默认折叠的“编辑与来源说明”中；正文不重复这些制作信息。若定位与科学正文混在同一段，整段留在阅读区，避免误折叠。章节保留小号时间标记，原稿疑误与研究限制的正文注仍留在原处。目录缩略图的 alt 只标照片中的人物，多参与者姓名保留在卡片正文；使用主持人单人照片的来宾卡片另有“主持人”标注。最终验收项见 [SITE_ACCEPTANCE.md](SITE_ACCEPTANCE.md)。

项目远端是私有仓库 [tolsonhuddy-collab/huberman-tolson-cn](https://github.com/tolsonhuddy-collab/huberman-tolson-cn)。本机目录名仍为 `huberman-lab-cn`。构建器不会联网、调用模型、创建仓库或执行部署。

## 构建与本机预览

依赖 Python 3.10 或更新版本的标准库，无需 `pip install`、Node、打包器或收费 API。可选 Node 仅用于执行一项 JavaScript 健壮性测试。

```sh
python3 scripts/build_site.py --demo --out dist
python3 -m http.server 8000 --bind 127.0.0.1 --directory dist
```

浏览器访问 `http://127.0.0.1:8000`。演示构建只采用脚本内原创的虚构标题、人物和短文，不读取 `catalog/`、`private/`、交接包或真人肖像。虚构短文仅测试版式，不是精读成稿。`dist/` 是构建产物，不应提交 Git。

私有阅读稿使用独立命令：

```sh
python3 scripts/build_site.py --private --out private/site
python3 -m http.server 8001 --bind 127.0.0.1 --directory private/site
```

本地预览地址是 `http://127.0.0.1:8001`。私有输出必须在项目的 `private/` 下，不能覆盖文章、元信息、交接包、来源映射、分块或审阅目录。构建器只替换带有自身构建标记的既有输出目录，错误输入不会替换上一份有效页面。不要将项目根目录作为 HTTP 服务目录。

构建结果为普通 HTML、CSS、JavaScript 和本地图片，采用相对路径，便于以后迁移到提供免费子域名的静态托管。目前未部署、未购买或绑定域名，不支持真实内容的公开 release 模式。代码许可不授予原始节目、转写、中文全文及真人肖像的分发权。

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
  "sections": [
    {"title": "与 Markdown H2 完全一致的标题", "source_seconds": null}
  ],
  "editor_note": "编辑说明与原稿限制"
}
```

`sections` 可留空，届时没有章节来源时间。提供该列表时，标题、数量与顺序必须严格匹配 Markdown H2，否则停止构建。时间只使用显式输入的非负秒数，不推测节目位置。已核验的 YouTube 节目 URL 可生成该节目自己的时间链接；其他来源只显示小号本地时间定位，提示与完整声明说明其核验范围，不推测第三方站点的定位语法。来源 URL 缺失或不安全时不生成原节目链接。

正文源码中的绝对路径只用于本地工作，不能写入 `source_url`。来源链接仅接受无凭据的 http(s) URL。人物头像默认显示本项目的中性占位图；`portrait` 仅能指向 `private/` 内已存在的 JPG、PNG 或 WebP，相对项目根目录填写。私有构建会复制到私有输出；演示构建不复制任何真人头像。

## 检查

```sh
python3 -m unittest discover -s tests -p 'test_site.py' -v
```

测试覆盖两篇不同节目各自的标题、来源与时间戳，未知链接保持缺失，章节错配失败，哈希失配的完成稿或已审核稿自动显示待修订且不改写源记录，未完成稿不出链接，AMA 节选和其他类别标记，目录锚点及本地资源，HTML/URL 转义，frontmatter 隐藏，私有路径边界，演示与私有全文隔离，以及目录页没有文章控件时 JavaScript 仍可运行。回归检查也覆盖来源证据转入默认折叠区后完整保留、正文科学限制注不被移走，以及单人照片 alt 与多参与者文字的区别。

程序测试不替代内容验收。是否覆盖原节目前中后、论证与例子是否完整、转写疑点是否标注、双人访谈的发言人是否清楚，仍由逐篇编辑记录判断。网站不会把这些编辑判断自动设为通过。
