# Huberman 中文精读

将用户提供的 Huberman Lab 英文转写稿编辑成可独立阅读的中文科普长文，并沿用已认可的杂志阅读版式。本仓库保存代码、目录元数据和工作规范；英文稿、中文全文、节目封面、真人头像及生成的全文 HTML 默认保留在本地 `private/`。

当前远端为私有仓库：[tolsonhuddy-collab/huberman-tolson-cn](https://github.com/tolsonhuddy-collab/huberman-tolson-cn)。本地工作目录暂用此前名称 `huberman-lab-cn`。全文仅用于已授权的拥有者私有预览；未购买域名或租用服务器。

## 内容范围与真实进度

只读盘点有 370 份 TXT，共 7,970,555 英文词。第一阶段为 279 份长节目候选（包含 16 份 Guest Series），共 7,401,563 词。另有 62 份 Essentials、19 份 AMA、10 份现场问答；其中 16 份 AMA 明确是公开节选。分类保留在目录中，不能把它们标成完整长节目。

候选不等于已独立核实原视频完整。日期来自原索引，时间轴来自同批 VTT，均不能直接当作已核实首发日期或完整视频时长。未知视频链接保持为空。

首批为神经系统、睡眠、Robert Sapolsky 访谈三篇。执行 `python3 scripts/pipeline.py status` 查看本机逐篇状态；`docs/PROGRESS.md` 为交付时的汇总快照。准备分块、创建空文件和生成目录均不算完成中文稿。

## 环境与使用

需要 Python 3.10+，所有处理脚本仅用标准库；无模型 API、付费服务或安装步骤。Git 与已登录的 GitHub CLI 只用于经授权的仓库操作。详细说明见 [DEPENDENCIES.md](DEPENDENCIES.md)。

在项目根目录运行（将占位路径替换为本机路径）：

```sh
python3 scripts/pipeline.py ingest --source-dir /absolute/path/final/txt --inventory /absolute/path/inventory-audit.csv
python3 scripts/pipeline.py prepare --id 001-nervous-system
python3 scripts/pipeline.py record --id 001-nervous-system --state drafting --note '开始阅读全文'
python3 scripts/pipeline.py status
python3 scripts/pipeline.py check-sources
python3 -m unittest discover -s tests -v
```

`ingest` 核对实际目录、盘点清单和每份 TXT 的 SHA-256，解析 VTT，记录字幕哈希；不修改输入。重新导入会保留已有状态。`prepare` 把每条 VTT cue 分配到恰好一个本地分块，保留时间范围，不自动删广告或声称翻译完成。

本机输入路径存在 `private/local-config.json`。清单在 `catalog/episodes.json`，逐篇状态与历史在 `private/progress.json`。状态文件原子替换；修改已独立校读稿后需重新校读，审核哈希失效。

网站的安全演示、私有本地构建、封面协议及托管交接见 [docs/website.md](docs/website.md)。首页为大报头、紧凑筛选、图文精选和三栏目录，正文保留桌面右侧目录、手机折叠目录。节目全文不公开分发，不配置 `huberman.tolson.ai`。

## 编辑与验收

中文稿以不懂英语的读者为对象，保留整期核心论证、解释、原有例子和限制，按自然结构形成长文。删除广告、寒暄和无意义重复；不用提纲或短摘要代替全文精读。采访保留双方归属，疑似识别错误显式标记，科学不确定性不能改成确定结论。文风采用自然中文科普杂志写法。具体规范见 [docs/EDITORIAL.md](docs/EDITORIAL.md)。

`draft_complete` 需要实稿、作者全文覆盖记录与术语核对；`reviewed` 还需要对应当前稿件哈希的独立编辑检查。程序的长度和结构门槛只能拦截空壳，不能代替语义校读或医学事实核验。

## 开源边界

本项目自有代码使用 [MIT](LICENSE)。改编版式保留 `web/qiaomu-LICENSE.txt`。两者均不授予节目音视频、英文转写、中文译写、人物头像、商标或品牌的内容权利。用户提供文件允许本次本地完整翻译与编辑；全文对外分发另有权限边界，见 [CONTENT_RIGHTS.md](CONTENT_RIGHTS.md)。

提交前必须运行 `python3 scripts/pipeline.py audit-git`，它检查整个 Git 索引的路径白名单。还需人工检查新代码/模板是否嵌入真实正文。忽略规则不能阻止强制添加，也不能清除历史：默认不提交 `dist/`、`content/`、`private/`、压缩包、头像和私有托管配置。
