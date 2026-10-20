# Huberman Lab 中文精读

**中文** | [English](#english)

把 [Huberman Lab](https://www.hubermanlab.com/) 的长访谈整理成中文长文，给读不懂英文原片的人看。文章顺着节目原来的顺序，保留核心论证、机制解释、例子和研究限制，去掉广告、寒暄和重复。访谈标明是谁在说；转写里对不上的地方会注明。

[**在线阅读 →**](https://huberman-reading-001.tolsonhuddy.chatgpt.site)

目前站上有 **41 篇**。例如：[神经系统如何工作，又如何被经验改变](https://huberman-reading-001.tolsonhuddy.chatgpt.site/episodes/001-nervous-system.html)、[好睡眠从白天开始](https://huberman-reading-001.tolsonhuddy.chatgpt.site/episodes/002-master-sleep.html)。

非官方阅读项目。Huberman Lab 没有参与，也不代表其背书或合作。

## 这是什么

1. **目录。** 仓库收录 370 条节目元数据：长节目 279（含 Guest Series 16）、Essentials 62、AMA 19、现场问答 10。可以按中文标题、英文标题、人物姓名和类别筛选，也可以只看已有精读或待整理。
2. **中文精读。** 按节目结构写成的长文，一集一个页面。线上目前放出 41 篇；其余条目只列目录。
3. **静态阅读页。** 桌面右侧章节目录，手机上可折叠。字号 16–24px，浅色或深色底，页内显示阅读进度。文末默认收起编辑与来源说明。

## 核心能力

| 能力 | 说明 |
|---|---|
| 中文精读 | 保留论证、机制、例子和研究限制；删广告、寒暄、重复。访谈写明发言人。转写疑误留在正文里。 |
| 节目目录 | 370 条元数据在 `catalog/episodes.json`。有正文的卡片链到独立页面，没有正文的只显示标题和类别。 |
| 筛选 | 首页匹配中文标题、英文标题、人物和类别，并可只看已有精读或待整理。筛选时精选区隐藏。 |
| 阅读页 | 桌面目录随滚动高亮；手机目录可折叠。字号与底色记在本机。文末可展开来源。 |
| 来源 | 核实过的节目链接写在文末。没有核实的视频地址留空，不编造。章节时间来自本地字幕。 |
| 本地构建 | Python 3.10+ 标准库。`--demo` 只做虚构版式；真实转写和中文全文不在 Git 里。 |

## 快速开始

需要 Python 3.10 或更新版本。测试和演示只用标准库，不用安装 Python 包、Node 或模型接口。

```sh
git clone https://github.com/tolsonhuddy-collab/huberman-tolson-cn.git
cd huberman-tolson-cn
python3 -m unittest discover -s tests -v
python3 scripts/build_site.py --demo --out dist
python3 -m http.server 8000 --bind 127.0.0.1 --directory dist
```

打开 `http://127.0.0.1:8000`。这是本机预览。演示页标题是「读一篇长文，留出一点时间」，人物和正文都是虚构的，用来看版式。请把服务目录指到 `dist/`，不要把仓库根目录暴露出去。

依赖说明见 [DEPENDENCIES.md](DEPENDENCIES.md)。

## 工作原理

脚本负责登记、分块、状态和静态构建。写作和审稿在脚本之外完成。脚本不调用模型，也不自动翻译。

```text
TXT + 同名 VTT + 盘点 CSV
        │  scripts/pipeline.py ingest
        ▼
catalog/episodes.json          目录元数据（入库）
        │  prepare --id          只切分字幕
        ▼
private/chunks、source-maps    本地，不入库
        │  写作、审稿、record     正文与状态写入 private/
        ▼
private/articles、metadata、reviews、progress.json
        │  scripts/build_site.py
        ▼
dist/（--demo，虚构稿）或 private/site/（--private，本地稿）
        │  手工交给静态托管
        ▼
https://huberman-reading-001.tolsonhuddy.chatgpt.site
```

命令、审稿状态和部署检查见 [流水线说明](docs/PIPELINE.md)。稿件字段见 [网站与输入协议](docs/website.md)，写法见 [编辑规范](docs/EDITORIAL.md)。

## 项目结构

```text
├── scripts/
│   ├── build_site.py        # 静态站构建（标准库）
│   └── pipeline.py          # 导入、分块、状态、源核对、Git 路径审计
├── tests/                   # unittest
├── catalog/episodes.json    # 370 条目录元数据，不含正文
├── web/                     # 首页与文章模板、样式、阅读脚本
│   └── qiaomu-LICENSE.txt   # 版式来源的 MIT 声明
├── docs/                    # 流水线、输入协议、编辑规范、验收
├── private/                 # 本地稿件与素材（.gitignore，克隆后没有）
├── CONTENT_RIGHTS.md        # 代码许可与内容权利
├── DEPENDENCIES.md
├── LICENSE                  # MIT，仅代码与工程文档
└── Makefile                 # test、demo、private-site、status、audit
```

## 内容与版权边界

- 代码采用 [MIT](LICENSE)，**只覆盖代码和工程文档**。阅读页版式改编自 [乔木的 lexfridman-cn](https://github.com/joeseesun/lexfridman-cn)，原声明在 [web/qiaomu-LICENSE.txt](web/qiaomu-LICENSE.txt)。
- 中文精读是独立整理的二次创作和综述，不是官方译文。原节目音频、视频和转写的版权归 Huberman Lab 与嘉宾。本仓库不托管、不分发这些原件，也不收录节目封面和人物肖像。
- 网站上的正文和素材不随 MIT 再许可。范围见 [CONTENT_RIGHTS.md](CONTENT_RIGHTS.md)。
- 权利人如需移除，请开 [Issue](https://github.com/tolsonhuddy-collab/huberman-tolson-cn/issues)。
- 文章保留讲者观点、研究条件和转写疑点，不能当作个人诊断或治疗方案。

## 已知限制

- 克隆这个仓库只能跑测试和 `--demo`。真实转写、中文全文、封面和托管凭据都在 Git 之外。`--private` 需要本机自行准备 `private/`。
- `prepare` 只对长节目切分字幕。Essentials、AMA、现场问答目前只在目录中。16 条 AMA 标明为节选。
- 目录里的索引日期未独立核实，不能当成节目首发日期。章节时间来自本地字幕，不表示已经与原音逐秒对齐。
- 推送代码不会更新线上站点。线上篇数以站点实际页面为准，目前是 41 篇。

## 贡献

- 错字、人名、数字或明显误读：开 Issue，写上篇目标题或页面地址。
- 构建、阅读页、流水线的修复：提 Pull Request。提交前可跑 `python3 scripts/pipeline.py audit-git`。
- 不要把原片、转写、中文全文、节目图片或凭据提交进仓库。

## 联系

taopatric58@gmail.com

---

## English

A static Chinese reading companion to the [Huberman Lab](https://www.hubermanlab.com/) podcast, for people who do not follow the English episodes. Essays keep the original order, arguments, examples, and limits, and drop ads and filler. The public site has **41** essays: [huberman-reading-001.tolsonhuddy.chatgpt.site](https://huberman-reading-001.tolsonhuddy.chatgpt.site).

This repository holds catalog metadata (370 entries), a stdlib Python site builder, and bookkeeping scripts. Transcripts and Chinese full text are not in Git. `python3 scripts/build_site.py --demo --out dist` builds a fictional layout only.

Unofficial, and not endorsed by Huberman Lab. Code is [MIT](LICENSE) for code only. The Chinese essays are an independent summary; original audio and transcripts belong to Huberman Lab and the guests. Nothing original is hosted here. Rights holders can request removal via an [Issue](https://github.com/tolsonhuddy-collab/huberman-tolson-cn/issues). See [CONTENT_RIGHTS.md](CONTENT_RIGHTS.md). The reading layout is adapted from [joeseesun/lexfridman-cn](https://github.com/joeseesun/lexfridman-cn).
