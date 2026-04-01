# 📚 ArXiv Daily Digest

> 每天早上打开邮箱，高质量论文摘要已为你准备好。

自动抓取 arXiv 论文 → ID 去重 → LLM 翻译总结 → 邮件推送 → 持久化记账，**零服务器成本**。

## ✨ 核心特性

- 🔍 **智能漏斗过滤**：历史去重 → 时间窗过滤 → 关键词过滤 → 分类豁免
- 🤖 **LLM 深度总结**：中文标题 + 一句话总结 + 摘要中文全文
- 📧 **精美 HTML 邮件**：折叠式设计、关键字高亮、按分类展示
- 💾 **防丢机制**：只有邮件发送成功后才记录论文 ID，失败可重试
- 🔄 **自动同步**：GitHub Actions 自动更新已读论文列表
- ⏰ **定时运行**：北京时间每天上午 10:00
- 🔌 **兼容多种 LLM**：DeepSeek / 智谱 AI / OpenAI

## 🚀 快速部署

### Step 1: Fork 本仓库

点击右上角 **Fork**。

### Step 2: 修改配置

编辑 `config.yaml`：

```yaml
search:
  categories:
    - cs.SE
    - cs.CL
    - cs.DC
    - cs.AI

  keywords:
    - "code"
    - "program"
    - "software"

  keyword_mode: "filter"

  filter_exempt_categories:
    - cs.SE
    - cs.DC

  max_papers: 300
  days_back: 4
  timezone: "Asia/Shanghai"

llm:
  model: "deepseek-chat"
  language: "中文"
  base_url: "https://api.deepseek.com/v1"

email:
  smtp_server: "smtp.gmail.com"
  smtp_port: 587
```

### Step 3: 设置 Secrets

仓库 → Settings → Secrets and variables → Actions → New repository secret：

| Secret | 说明 | 必填 |
|--------|------|------|
| `OPENAI_API_KEY` | LLM API 密钥 | ✅ |
| `OPENAI_BASE_URL` | API 地址 | ❌ |
| `EMAIL_ADDRESS` | 发件邮箱 | ✅ |
| `EMAIL_PASSWORD` | 邮箱应用密码 | ✅ |
| `TO_EMAIL` | 收件邮箱 | ❌ |
| `LLM_MODEL` | 模型名称 | ❌ |

### Step 4: 运行

Actions → Daily ArXiv Digest → Run workflow

## ⚙️ 配置说明

### 关键字模式

| 模式 | 说明 |
|------|------|
| `none` | 只按分类搜索 |
| `filter` | 按分类搜索，关键字本地过滤 |

### 分类豁免

`filter_exempt_categories` 中的分类可以豁免关键字过滤，直接收录。

### 时间窗机制

`days_back=4` 表示自动扫描过去 4 天的论文，结合 `seen_papers.txt` 去重，不会重复发送。

## 📊 运行流程

```
┌─────────────────┐
│  扫描 arXiv     │  ← 最多抓取 1000 篇
└────────┬────────┘
         ▼
┌─────────────────┐
│  历史去重        │  ← 对比 seen_papers.txt
└────────┬────────┘
         ▼
┌─────────────────┐
│  时间窗过滤      │  ← 过滤 days_back 外的论文
└────────┬────────┘
         ▼
┌─────────────────┐
│  关键词过滤      │  ← filter 模式时生效
└────────┬────────┘
         ▼
┌─────────────────┐
│  LLM 总结       │  ← 生成中文摘要
└────────┬────────┘
         ▼
┌─────────────────┐
│  发送邮件       │
└────────┬────────┘
         ▼
┌─────────────────┐
│  记录 ID        │  ← 仅发送成功后才记录
└─────────────────┘
```

## 🤖 LLM 提供商

| 提供商 | 模型 | BASE_URL |
|--------|------|----------|
| DeepSeek | `deepseek-chat` | `https://api.deepseek.com/v1` |
| 智谱 AI | `glm-4-flash` | `https://open.bigmodel.cn/api/paas/v4` |
| OpenAI | `gpt-4o-mini` | 不需要 |

## 💰 费用

| 项目 | 费用 |
|------|------|
| GitHub Actions | ✅ 免费 |
| LLM API | ~$0.01/天 |
| 邮件 | ✅ 免费 |

## 📂 项目结构

```
arxiv-daily-digest/
├── .github/workflows/   # GitHub Actions
├── main.py              # 主脚本
├── config.yaml          # 配置文件
├── seen_papers.txt      # 已读论文记录
└── README.md           # 文档
```

## 📄 License

MIT
