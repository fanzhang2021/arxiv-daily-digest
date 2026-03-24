# 📚 ArXiv Daily Digest

> 每天早上打开邮箱，高质量论文摘要已为你准备好。

自动抓取 arXiv 论文 → LLM 翻译总结 → 邮件推送，完全运行在 GitHub Actions 上，**零服务器成本**。

## ✨ 功能

- 🔍 按分类自动搜索 arXiv 最新论文
- 🤖 LLM 智能翻译摘要
- 📧 精美 HTML 邮件，支持多收件人
- ⏰ 每天定时运行，也支持手动触发
- 🔌 兼容 OpenAI / DeepSeek / 智谱 AI 等多种 LLM
- 🎯 智能跳过周末（arXiv 周末不更新）
- ⚙️ 灵活的配置选项

## 🚀 快速部署

### Step 1: Fork 本仓库

点击右上角 **Fork**。

### Step 2: 修改配置

编辑 `config.yaml`，设置你关心的分类和关键词：

```yaml
search:
  categories:
    - cs.SE
    - cs.CL
  keywords:
    - "Goedel-Code-Prover"
  keyword_mode: "none"
  max_papers: 300
  fetch_mode: "yesterday"
  timezone: "Asia/Shanghai"
  skip_no_arxiv_days: true

llm:
  model: "glm-4-flash"
  language: "中文"
  base_url: "https://open.bigmodel.cn/api/paas/v4"

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
| `OPENAI_BASE_URL` | 自定义 API 地址 | ❌ | `https://open.bigmodel.cn/api/paas/v4` |
| `EMAIL_ADDRESS` | 发件邮箱 | ✅ | `you@gmail.com` |
| `EMAIL_PASSWORD` | 邮箱应用密码 | ✅ | `abcd efgh ijkl mnop` |
| `TO_EMAIL` | 收件邮箱 | ❌ | `a@qq.com` |
| `SMTP_SERVER` | SMTP 服务器 | ❌ | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP 端口 | ❌ | `587` |

### Step 4: 测试运行

进入 **Actions** 标签 → 选择 **Daily ArXiv Digest** → **Run workflow**。

## ⚙️ 配置说明

### 关键字模式 (keyword_mode)

| 模式 | 说明 |
|---|---|
| `none` | 只按分类搜索 |
| `filter` | 按分类搜索，关键字本地过滤 |
| `query` | 分类+关键字一起查询 |

### 日期模式 (fetch_mode)

| 模式 | 说明 |
|---|---|
| `yesterday` | 只抓昨天的论文 |
| `today` | 只抓今天的论文 |
| `custom` | 使用 days_back 自定义 |

### 跳过周末

开启 `skip_no_arxiv_days: true` 后，每天凌晨运行，抓取昨天的论文：

| 运行日 | 目标日 | 范围（精确） | 重复？ |
|--------|--------|--------------|--------|
| 周二 | 周一 | 周一~周一 | ❌ 无 |
| 周三 | 周二 | 周二~周二 | ❌ 无 |
| 周四 | 周三 | 周三~周三 | ❌ 无 |
| 周五 | 周四 | 周四~周四 | ❌ 无 |
| 周六 | 周五 | 周五~周五 | ❌ 无 |
| 周日 | 不运行 | — | — |
| 周一 | 不运行 | — | — |

## 📮 邮箱配置

### Gmail
- 开启两步验证
- 生成应用密码：https://myaccount.google.com/apppasswords
- SMTP: `smtp.gmail.com:587`

### QQ 邮箱
- 设置 → 账户 → 开启 SMTP → 获取授权码
- SMTP: `smtp.qq.com:465`

## 🤖 LLM 提供商

| 提供商 | 模型 | BASE_URL |
|---|---|---|
| 智谱 AI | `glm-4-flash` | `https://open.bigmodel.cn/api/paas/v4` |
| OpenAI | `gpt-4o-mini` | 不需要 |
| DeepSeek | `deepseek-chat` | `https://api.deepseek.com` |
| SiliconFlow | `Qwen/Qwen2.5-7B-Instruct` | `https://api.siliconflow.cn/v1` |

## 💰 费用

| 项目 | 费用 |
|---|---|
| GitHub Actions | ✅ 免费 |
| LLM API | ~$0.01/天 |
| 邮件 | ✅ 免费 |

## 📂 项目结构

```
arxiv-daily-digest/
├── .github/workflows/   # GitHub Actions
├── main.py              # 主脚本
├── config.yaml          # 配置文件
├── requirements.txt     # 依赖
└── README.md           # 文档
```

## 📄 License

MIT
