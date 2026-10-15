# MarketStream Engine v1.3 — GitHub 公开上传指南

本文件随 **GitHub-ready 仓库包** 提供。它不是私人/公司真实交易数据仓库；默认生成的是 synthetic demo。请不要上传任何原始公司数据、笔试题、个人秘密或 Token。

## A. 推荐方式：在 Mac / Windows / Linux 使用 Git 上传

1. 到 https://github.com/new 创建一个 **名为 `marketstream-engine`** 的新仓库。首次建议设为 **Private**，审核完 CI 与内容再转 Public。**不要**勾选自动添加 README、.gitignore 或 License，因为这些文件已经包含在项目里。
2. **先解压** `MarketStream_Engine_v1.3_GitHub_Ready.zip`，进入里面的 `marketstream-engine` 文件夹；不要把 ZIP 本身当作 GitHub 代码上传。
3. Mac/Linux Terminal（Windows 推荐 Git Bash）执行：

```bash
cd /path/to/marketstream-engine
git init
git branch -M main
git add -A
python tools/check_public_repo.py
git status --short
git diff --cached --stat
git commit -m "Initial public portfolio release: MarketStream Engine v1.3"
git remote add origin https://github.com/YOUR_USERNAME/marketstream-engine.git
git push -u origin main
```

请将 `YOUR_USERNAME` 换成你的 GitHub 用户名，将 `/path/to/marketstream-engine` 换成自己的解压路径。GitHub 若要求认证，可通过 `gh auth login` 或 Git Credential Manager；不要在聊天、文件或命令中嵌入访问 Token。

4. 在 GitHub 仓库 **Actions** 页面确认 `MarketStream Python CI` 和 `Public repository secret audit` 的实际执行状态。出现红色失败时先修复问题，不要把“有 CI 文件”写成“CI 已通过”。Gitleaks Action 的许可或权限要求可能随组织账号环境不同而变化。
5. 检查 `Code` 标签里的源码目录、README 图表、License、`.github/workflows` 是否正确，并进行人工文件/历史秘密检查。确认无保密问题后，再到仓库 **Settings → General → Danger Zone → Change repository visibility** 考虑将 Private 改为 Public。

## B. 不会使用 Git 时：网页上传

1. 创建空仓库，打开 **Add file → Upload files**，上传**解压后的仓库文件和子目录**，而不是上传 ZIP 作为单个文件。
2. 留意以点开头的隐藏项（`.gitignore`、`.dockerignore`、`.github/`）必须一同上传；大量文件或文件夹结构更推荐方法 A。
3. 提交后检查 GitHub 文件树是否与本地一致，特别是 `src/`、`tests/`、`docs/`、`.github/workflows/`。

## C. 上传前的本地检查

```bash
python -m venv .venv
source .venv/bin/activate   # Windows Git Bash: source .venv/Scripts/activate
python -m pip install -e ".[dev]"
python -m pytest -q
marketstream validate
marketstream run --format csv
marketstream current --output-dir outputs/demo --verify
```

这个公开版默认不含真实交易 CSV、账号凭据、`.env`、本地输出 `outputs/`、历史原始 Notebook 和版本整改 Word 文档。单独运行 `python tools/check_public_repo.py` 只检查 Git 路径，**不能**证明文件内容及 Git 历史没有秘密。请人工复核，并使用专门的 Secret Scanner。

## D. 常见问题

- **`git push` 要用户名密码？** GitHub 不接受账号密码用于 Git HTTPS 推送，使用浏览器登录的 GitHub CLI/Credential Manager 或经过授权的 Personal Access Token；不要泄露 Token。
- **GitHub 上传的是 ZIP，打不开代码？** 需要先解压，再把里面所有文件作为仓库内容提交；ZIP 本身适合存档/Release Asset，不是源代码的替代。
- **测试因 pyarrow/hypothesis 缺失而跳过？** 先确认安装了 `.[dev]`，然后重新运行全部测试；不要把跳过的测试标为通过。
- **Actions 显示失败？** 查看工作流日志，区分程序错误、依赖版本、第三方扫描工具配置；本包只表示工作流配置齐全，不代表 GitHub 已经运行成功。

## E. 推荐仓库介绍

- **Repository name:** `marketstream-engine`
- **Description:** `Python market data processing engine with event-time alignment, validated analytics, immutable artifacts, and automated testing.`
- **Topics:** `python`, `software-engineering`, `data-engineering`, `market-data`, `order-book`, `pytest`, `github-actions`, `pandas`
- **License:** MIT（保留原项目内版权信息；公开前确认你有相应授权）
