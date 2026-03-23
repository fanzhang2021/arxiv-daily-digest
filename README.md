# 📚 ArXiv Daily Digest

> 每天早上打开邮箱，高质量论文摘要已为你准备好。

自动抓取 arXiv 论文 → LLM 翻译总结 → 邮件推送，完全运行在 GitHub Actions 上，**零服务器成本**。

## ✨ 功能

- 🔍 按关键词 + 分类自动搜索 arXiv 最新论文
- 🤖 LLM 智能总结：标题 / 摘要
- 📧 精美 HTML 邮件，支持多收件人
- ⏰ 每天定时运行，也支持手动触发
- 🔌 兼容 OpenAI / DeepSeek / SiliconFlow 等多种 LLM
- 🎯 智能跳过周末（arXiv 周末不更新）
- ⚙️ 灵活的配置选项：关键字模式、日期模式、时区等

## 🚀 5 分钟部署

### Step 1: Fork 本仓库

点击右上角 **Fork**。

### Step 2: 修改配置

编辑 `config.yaml`，设置你关心的**关键词**和**分类**。

```yaml
search:
  categories:
    - cs.SE
    - cs.CL
  keywords:
    - "code generation"
    - "LLM"
  keyword_mode: "filter"  # none/filter/query
  max_papers: 50
  fetch_mode: "yesterday"  # yesterday/today/custom
  days_back: 3  # 仅 fetch_mode: "custom" 时生效
  timezone: "Asia/Shanghai"
  skip_no_arxiv_days: true  # 跳过周日、周一

llm:
  model: "gpt-4o-mini"
  language: "中文"
  base_url: ""  # 可选，自定义 API 地址

email:
  smtp_server: "smtp.gmail.com"
  smtp_port: 587
  subject_prefix: "📚 每日ArXiv论文精选"
```

### Step 3: 设置 Secrets

进入仓库 **Settings → Secrets and variables → Actions → New repository secret**：

| Secret 名称 | 说明 | 必填 | 示例 |
|---|---|---|---|
| `OPENAI_API_KEY` | LLM API 密钥 | ✅ | `sk-xxx...` |
| `OPENAI_BASE_URL` | 自定义 API 地址 | ❌ | `https://api.deepseek.com` |
| `LLM_MODEL` | 模型名称（覆盖配置文件） | ❌ | `deepseek-chat` |
| `LLM_INTERVAL_SECONDS` | LLM 调用间隔（秒） | ❌ | `5` |
| `EMAIL_ADDRESS` | 发件邮箱 | ✅ | `you@gmail.com` |
| `EMAIL_PASSWORD` | 邮箱密码/应用密码 | ✅ | `abcd efgh ijkl mnop` |
| `TO_EMAIL` | 收件邮箱（多个用逗号分隔） | ❌ | `a@qq.com,b@163.com` |
| `SMTP_SERVER` | SMTP 服务器 | ❌ | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP 端口 | ❌ | `587` |

### Step 4: 测试运行

进入 **Actions** 标签 → 选择 **Daily ArXiv Digest** → **Run workflow**。

## ⚙️ 配置详解

### 关键字模式 (keyword_mode)

| 模式 | 说明 | 适用场景 |
|---|---|---|
| `none` | 只按分类搜索，完全忽略关键字 | 想要某个分类的所有论文 |
| `filter` | 按分类搜索，用关键字本地过滤 | **推荐**，精准控制 |
| `query` | 分类+关键字一起发给 arXiv 查询 | 想要更广泛的搜索结果 |

### 日期模式 (fetch_mode)

| 模式 | 说明 | 适用场景 |
|---|---|---|
| `yesterday` | 只抓昨天的论文 | **推荐**，配合凌晨定时任务 |
| `today` | 只抓今天的论文 | 实时性要求高 |
| `custom` | 使用 days_back 自定义范围 | 灵活控制时间范围 |

### 智能跳过周末

arXiv 周六周日不更新论文，开启 `skip_no_arxiv_days: true` 后：
- **周日跳过**：昨天是周六，arXiv 不更新
- **周一跳过**：昨天是周日，arXiv 不更新
- **周二~周六正常运行**

## 📮 邮箱配置指南

### Gmail
1. 开启两步验证：https://myaccount.google.com/security
2. 生成应用密码：https://myaccount.google.com/apppasswords
3. `SMTP_SERVER=smtp.gmail.com`, `SMTP_PORT=587`

### QQ 邮箱
1. 设置 → 账户 → 开启 SMTP → 获取授权码
2. `SMTP_SERVER=smtp.qq.com`, `SMTP_PORT=465`

### 163 邮箱
1. 设置 → POP3/SMTP → 开启 → 获取授权码
2. `SMTP_SERVER=smtp.163.com`, `SMTP_PORT=465`

### Outlook
1. 直接使用账号密码
2. `SMTP_SERVER=smtp.office365.com`, `SMTP_PORT=587`

## 🤖 LLM 提供商

| 提供商 | 模型 | 费用 | BASE_URL |
|---|---|---|---|
| OpenAI | `gpt-4o-mini` | ~$0.01/天 | 不需要 |
| DeepSeek | `deepseek-chat` | ~¥0.01/天 | `https://api.deepseek.com` |
| SiliconFlow | `Qwen/Qwen2.5-7B-Instruct` | 免费额度 | `https://api.siliconflow.cn/v1` |
| 智谱 AI | `glm-4-flash` | 免费额度 | `https://open.bigmodel.cn/api/paas/v4` |

### 通过环境变量配置模型

你可以通过 GitHub Secrets 的 `LLM_MODEL` 变量覆盖配置文件中的模型设置：

```
LLM_MODEL=deepseek-chat
```

## 📅 定时任务

项目配置了自动定时运行：
- **运行时间**：北京时间周二~周六凌晨 1:00
- **跳过时间**：周日、周一（arXiv 周末不更新）
- **手动触发**：支持在 Actions 页面手动运行

## 💰 费用估算

| 项目 | 费用 |
|---|---|
| GitHub Actions | ✅ 公开仓库完全免费 |
| LLM API（10 篇/天） | ~$0.01（GPT-4o-mini）|
| 邮件发送 | ✅ 免费 |
| **月总计** | **< $0.5** |

## 🔧 本地运行

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 设置环境变量

```bash
# Windows PowerShell
$env:OPENAI_API_KEY = "your-api-key"
$env:EMAIL_ADDRESS = "your-email@gmail.com"
$env:EMAIL_PASSWORD = "your-app-password"
$env:TO_EMAIL = "recipient@example.com"

# macOS/Linux
export OPENAI_API_KEY="your-api-key"
export EMAIL_ADDRESS="your-email@gmail.com"
export EMAIL_PASSWORD="your-app-password"
export TO_EMAIL="recipient@example.com"
```

### 3. 运行脚本

```bash
python main.py
```

## 📂 项目结构

```
arxiv-daily-digest/
├── .github/
│   └── workflows/
│       └── daily_digest.yml    # GitHub Actions 工作流
├── main.py                     # 主脚本
├── config.yaml                 # 配置文件
├── requirements.txt            # 依赖
└── README.md                   # 说明文档
```

## 📄 License

MIT
