# 线香每日资讯摘要

每日自动抓取线香相关资讯 → LLM 中文分类摘要 → 推送飞书会话。

## 当前状态（2026-10-23 已上线）

- **仓库**：https://github.com/lbq19851326003/incense-daily-digest
- **部署**：GitHub Actions 云端已跑通 ✅（海外服务器抓 Google News + Reddit，国内源兜底）
- **推送**：飞书 email 直发 ✅（实测成功）
- **调度**：每天早上 08:00（北京时间）自动执行
- **首跑数据**：44 条（Google News 关键词 22 条 + 少数派 10 + IT之家 12）

## 项目结构

```
incense-daily-digest/
├── config.yaml              # RSS 源 + 分类配置（源按运行环境分类）
├── daily_digest.py         # 主脚本（支持 --no-send 本地调试）
├── requirements.txt
├── .github/workflows/
│   └── daily.yml           # GitHub Actions 定时任务（每天 08:00 北京时间）
└── README.md
```

## 数据源（三层结构）

| 层 | 源 | 运行环境 | 作用 |
|---|---|---|---|
| 关键词新闻 | Google News × 8（线香/沉香/香道/檀香品香/日本线香/incense/oud/Japanese incense） | **仅 GitHub Actions 云端**（海外服务器） | 线香关键词命中主力 |
| 社区 | Reddit r/incense | **仅 GitHub Actions 云端** | 海外香友玩法/测评 |
| 国内垂直+通用 | 沉香网（行业垂直）/ 少数派 / IT之家 / 新浪科技 | 本地 + 云端都能跑 | 国内垂直资讯 + 兜底 |

> **重要**：本地网络访问不了 Google/Reddit（超时属正常，会被自动跳过）。
> GitHub Actions 的服务器在海外，能正常访问，所以关键词源在云端是主力。
> 国内源里「沉香网」是线香行业垂直门户（有官方 RSS），命中率最高。

## 部署步骤

### 1. 飞书应用

已配置好：App ID / App Secret / 收件邮箱。发送方式为 **email 直发**（`receive_id_type=email`），实测无需额外通讯录权限。

> 想发到群聊？把 `FEISHU_RECEIVE_ID` 改为群 chat_id，`FEISHU_RECEIVE_ID_TYPE` 改为 `chat_id`。

### 2. 推到 GitHub

```bash
cd incense-daily-digest
git init
git add .
git commit -m "init"
# 在 GitHub 建一个公开仓库（免费 Actions 额度）
git remote add origin https://github.com/<你的用户名>/incense-daily-digest.git
git push -u origin main
```

### 3. 配置 Secrets（不要提交明文凭证）

GitHub 仓库 → Settings → Secrets and variables → Actions → New repository secret：

| Secret 名 | 值 |
|---|---|
| `LLM_API_KEY` | DeepSeek API Key |
| `FEISHU_APP_ID` | 飞书应用 App ID |
| `FEISHU_APP_SECRET` | 飞书应用 App Secret |
| `FEISHU_RECEIVE_ID` | 飞书收件邮箱 |
| `FEISHU_RECEIVE_ID_TYPE` | `email` |

### 4. 跑通

- 首次：Actions 页面 → "线香每日资讯" → Run workflow（手动触发一次）
- 之后：每天早上 08:00 自动跑，结果直接发到你飞书

## 本地调试

```bash
pip install -r requirements.txt

# Windows PowerShell（凭证用环境变量，别写进代码）
$env:LLM_API_KEY = "sk-xxx"
$env:FEISHU_APP_ID = "cli_xxx"
$env:FEISHU_APP_SECRET = "xxx"
$env:FEISHU_RECEIVE_ID = "xxx@qq.com"
$env:FEISHU_RECEIVE_ID_TYPE = "email"

# 只抓取+摘要不发飞书
python daily_digest.py --no-send

# 完整跑（抓取→摘要→发送）
python daily_digest.py
```

## 自定义

- **加 RSS 源**：编辑 `config.yaml` 的 `feeds` 列表；本地网络用不了的源保持 `enabled: true`（云端可用），本地调试可临时改 `enabled: false`
- **改分类**：编辑 `config.yaml` 的 `categories`
- **改推送时间**：编辑 `.github/workflows/daily.yml` 的 `cron`（UTC 时间，UTC+8 减 8 小时，现在是 `0 0 * * *` = 北京时间 08:00）
- **换 LLM**：改 `config.yaml` 的 `llm.model` 和 `llm.base_url`

## 已知限制

- GitHub Actions 定时任务可能延迟 5-15 分钟
- 飞书 text 消息不渲染 markdown，所以 prompt 要求纯文本 + emoji
- 中文站「沉香网」是织梦系统 RSS，条目较少但垂直命中率高
- Google News 本地网络不可达，本地调试看不到关键词源效果（云端正常）
