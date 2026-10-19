# Huberman Lab 中文精读

把一场长谈，读成一篇长文。面向不懂英语的读者，按节目自然结构保留核心论证、机制解释、原有例子与研究限制，删除广告、寒暄和无意义重复。访谈保留发言人归属，转写疑误明确标注。

**正式站点：[huberman-reading-001.tolsonhuddy.chatgpt.site](https://huberman-reading-001.tolsonhuddy.chatgpt.site)**

本次网站已开放公开访问，首发为 **41 篇**；托管端已直接打开首页验证。源码仓库与网站分别发布，线上篇数不由本地审核总数推算。

源码仓库：[tolsonhuddy-collab/huberman-tolson-cn](https://github.com/tolsonhuddy-collab/huberman-tolson-cn)。这里保存构建代码、目录元数据、合成演示与工程说明，真实英文转写、中文全文、节目图片和托管凭据均不进入 Git。

## 当前范围

| 项目 | 已确认状态 |
|---|---|
| 网站首发 | 41 篇，站点已开放公开访问 |
| 本地独立全文审核通过 | 44 篇、1,203 节；其中新增 3 篇尚未计为线上首发 |
| 在制稿 | 016 批三篇已安全暂停，不算完成；本次不开新批 |
| 长节目总目录 | 279 份候选，含 16 份 Guest Series；没有全部完成 |
| 其他分类 | Essentials 62、AMA 19、现场问答 10；16 份 AMA 明确为节选 |

全部目录共 370 份 TXT，审计约 797 万英文词。目录条目、输入准备、完整初稿、独立审核通过与线上发布分别记录。93 篇保留为后续制作里程碑，此次先发布现有 41 篇。逐篇快照见 [生产进度](docs/PROGRESS.md)。

## 阅读示例与版式展示

站点中的中文精读示例：

- [神经系统如何工作，又如何被经验改变](https://huberman-reading-001.tolsonhuddy.chatgpt.site/episodes/001-nervous-system.html)
- [好睡眠从白天开始：清醒、光照与入睡的生物学](https://huberman-reading-001.tolsonhuddy.chatgpt.site/episodes/002-master-sleep.html)

示例链接沿用站点的实际访问权限。仓库不复制这些文章的全文或截图。下图用纯文字展示阅读结构；下方的 `--demo` 命令可生成完全原创的虚构文章，查看真实页面和交互。

```text
桌面：首页报头 → 搜索/类别/阅读状态 → 图文精选 → 三栏目录
      文章：人物与标题 → 白底中文正文       右侧章节目录
手机：同一页面自然堆叠 → 可折叠章节目录 → 字号与底色设置
      文末：默认折叠的编辑与来源说明
```

虚构演示标题为“读一篇长文，留出一点时间”，人物、短文和目录均为占位内容，不对应真实节目，也不代表已完成一篇精读。节目来源、真实时间定位及科学疑误注按篇保留在正式阅读页。

## 快速运行

需要 Python 3.10+，构建与测试只用标准库，无需安装 Python 包、Node 或模型 API。克隆代码后即可运行合成演示；真实全文不随仓库提供。

```sh
git clone https://github.com/tolsonhuddy-collab/huberman-tolson-cn.git
cd huberman-tolson-cn
python3 -m unittest discover -s tests -v
python3 scripts/build_site.py --demo --out dist
python3 -m http.server 8000 --bind 127.0.0.1 --directory dist
```

打开 `http://127.0.0.1:8000`。它是本机预览地址，不是互联网部署。服务目录应为输出目录，避免把项目根目录暴露出去。更多依赖与成本说明见 [DEPENDENCIES.md](DEPENDENCIES.md)。

## 内容输入与编辑流水线

原始输入为 UTF-8 TXT 与同名 WebVTT，分别位于相邻的 `txt/`、`vtt/` 目录；盘点 CSV 包含文件名、SHA-256、类型和词数。原始文件只读，路径配置、生成分块与编辑材料保存在被忽略的 `private/` 中。

```sh
python3 scripts/pipeline.py ingest --source-dir inputs/final/txt --inventory inputs/inventory-audit.csv
python3 scripts/pipeline.py prepare --id 001-nervous-system
python3 scripts/pipeline.py record --id 001-nervous-system --state drafting --note '开始阅读全文'
python3 scripts/pipeline.py status
python3 scripts/pipeline.py check-sources
```

以上输入路径是占位示例，需替换为自己的授权资料。导入操作核对清单、TXT 与 VTT 哈希，重新导入保留已有状态；分块保留全部字幕 cue，不自动翻译、删广告或完成语义审核。

编辑与构建输入包括：

| 文件 | 格式与用途 |
|---|---|
| `catalog/episodes.json` | `episodes` 列表：稳定 ID、英文标题、类别、节选标识及来源哈希 |
| `private/articles/{id}.md` | 实际 `# 中文标题`、自然 `## 章节` 和中文段落；保留疑误注与真实来源定位 |
| `private/articles/{id}.glossary.json` | 本篇专有名词及译法 |
| `private/reviews/{id}.author-review.json` | 作者完整阅读、覆盖、疑点及自查记录 |
| `private/reviews/{id}.independent-review.json` | 独立编辑全文对照、具体修订和最终哈希绑定 |
| `private/metadata/{id}.json` | 展示标题、人物、来源、已核封面与按顺序对应 H2 的章节时间 |
| `private/progress.json` | 逐篇状态及历史，不把输入准备计为完成 |

`source_url` 或章节时间未知时保留 `null`，不编造视频 ID、首发日期或时间戳。frontmatter 不作为可见标题解析；metadata 的章节标题须与 Markdown H2 严格一致。完整输入协议见 [网站文档](docs/website.md#输入协议)，编辑要求见 [编辑规范](docs/EDITORIAL.md)。

状态依次记录实际写作、完整初稿、必要修订和独立审核通过。长度与布尔检查只能拦截空壳，不能替代全文语义对照。修改已审稿后，旧审核哈希失效，必须重新审核。源完整阅读不等于原音逐秒校准或外部医学事实核验。

## 构建与部署

合成演示使用 `--demo --out dist`，可以用于展示本仓库的排版与交互。具有完整授权和编辑输入时，可构建本地工作台：

```sh
python3 scripts/pipeline.py check-sources
python3 scripts/build_site.py --private --out private/site
python3 -m http.server 8001 --bind 127.0.0.1 --directory private/site
```

`--private` 是本地工作台模式，可能显示待审核初稿和未发布目录，不能把它直接等同于线上首发版本。本次线上使用托管端已经验收的 41 篇清单，不将本地 44 篇候选自动扩入首发。

部署已有静态站点时：

1. 运行测试并构建，确定此次发布清单及对应产物；源码推送不触发本项目的网页部署。
2. 仅交付构建输出中的 `index.html`、`episodes/`、CSS、JS 与此次授权的本地资源，保留相对目录；不要上传项目根目录、原始字幕、审稿记录或隐藏配置。
3. 通过已有托管流程导入输出目录。本次沿用上方既有站点，由托管端按明确授权开放访问，不新建域名或凭据。
4. 分别验证首页筛选、正文、手机目录、来源链接和匿名访问权限，记录实际发布篇数与网址。Library 保存、本机可读和仓库开源不代替这项验收。

详细检查见 [网站验收清单](docs/SITE_ACCEPTANCE.md) 和 [恢复记录说明](docs/RECOVERY.md)。

## 来源、非官方声明与许可

本项目为独立中文编译与阅读工具，**不是 Huberman Lab 官方项目，也不代表其背书或合作关系**。原节目及官方资料见 [Huberman Lab](https://www.hubermanlab.com/)。每篇正式阅读页提供其已核来源，并保留研究条件、讲者观点和转写疑点；内容不作为个人医疗诊断或治疗方案。

- 本仓库原创代码与工程文档采用 [MIT License](LICENSE)。改编版式保留 [原模板 MIT 声明](web/qiaomu-LICENSE.txt)，来源为 [乔木的 lexfridman-cn](https://github.com/joeseesun/lexfridman-cn)。
- 用户已确认本次代码开源及线上现有 41 篇的公开发布授权；这不把原音视频、转写、中文译写、节目封面、人物肖像或商标改为 MIT 再许可。
- 网站内容与素材的权利单独处理，详见 [CONTENT_RIGHTS.md](CONTENT_RIGHTS.md)。仓库不附全文、原始字幕、节目图片、真实内容压缩包或托管凭据。

提交前运行 `python3 scripts/pipeline.py audit-git`，并检查全部 Git 历史与构建产物。忽略规则不能清除曾经提交的内容；完整稿和 `dist/`、`private/`、`content/` 等输出始终与源码分离。
