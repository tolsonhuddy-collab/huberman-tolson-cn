# 依赖与成本

内容流水线与静态构建：Python 3.10+，标准库 `argparse/csv/hashlib/html/json/pathlib/re/tempfile/unittest` 等，无第三方 Python 包，无安装步骤。

前端：原生 HTML、CSS、JavaScript，无打包器、数据库、服务端或运行时 API。浏览器本地存储仅保存字号和阅读底色。构建应使用本地静态素材，不依赖外链字体/CDN。

开发验证：Python `unittest`；JavaScript 可选用现有 Node 执行 `node --check web/app.js`。视觉检查可使用本机已安装浏览器；不为此自动安装浏览器或其他软件。

仓库操作：系统 Git、现有 GitHub CLI 及已登录账号。不读取或输出凭据，不新建 token，不扩大 OAuth 权限。

中文编辑：在当前会话的模型与子任务内阅读全文、写作和复核。本仓库没有把 `prepare` 伪装成批量翻译，没有自动调用收费 API。大量内容仍需持续的模型写作与编辑时间；脚本不能自行创造已验收稿件。若当前会话结束，没有配置后台任务继续写作。

托管：已有静态站点使用既有子域名与托管流程；已上线 84 篇中文精读，访问开放及验证由托管端执行。本轮未新增域名、服务器、套餐或凭据；代码推送和本地构建不等于部署成功。本文不承诺第三方的永久免费配额。

GitHub Pages：`.github/workflows/pages.yml` 在推送到 `main` 时，用仓库里能够构建的 `--demo` 结果发布备用站。不新增域名、服务器或凭据。中文全文不在 Git 中，此工作流不能代替主站的手工发布。
