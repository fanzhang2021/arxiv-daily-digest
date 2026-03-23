# 📚 ArXiv Daily Digest

> 每天早上打开邮箱，高质量论文摘要已为你准备好。

自动抓取 arXiv 论文 → LLM 翻译总结 → 邮件推送，完全运行在 GitHub Actions 上，**零服务器成本**。

## ✨ 功能

- 🔍 按关键词 + 分类自动搜索 arXiv 最新论文
- 🤖 LLM 智能总结：动机 / 方法 / 结果 / 贡献
- 📧 精美 HTML 邮件，支持多收件人
- ⏰ 每天定时运行，也支持手动触发
- 🔌 兼容 OpenAI / DeepSeek / SiliconFlow 等多种 LLM

## 🚀 5 分钟部署

### Step 1: Fork 本仓库

点击右上角 **Fork**。

### Step 2: 修改配置

编辑 `config.yaml`，设置你关心的**关键词**和**分类**。

### Step 3: 设置 Secrets

进入仓库 **Settings → Secrets and variables → Actions → New repository secret**：

| Secret 名称 | 说明 | 必填 | 示例 |
|---|---|---|---|
| `OPENAI_API_KEY` | LLM API 密钥 | ✅ | `sk-xxx...` |
| `OPENAI_BASE_URL` | 自定义 API 地址 | ❌ | `https://api.deepseek.com` |
| `EMAIL_ADDRESS` | 发件邮箱 | ✅ | `you@gmail.com` |
| `EMAIL_PASSWORD` | 邮箱密码/应用密码 | ✅ | `abcd efgh ijkl mnop` |
| `TO_EMAIL` | 收件邮箱（多个用逗号分隔） | ❌ | `a@qq.com,b@163.com` |
| `SMTP_SERVER` | SMTP 服务器 | ❌ | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP 端口 | ❌ | `587` |

### Step 4: 测试运行

进入 **Actions** 标签 → 选择 **Daily ArXiv Digest** → **Run workflow**。

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

## 💰 费用估算

| 项目 | 费用 |
|---|---|
| GitHub Actions | ✅ 公开仓库完全免费 |
| LLM API（10 篇/天） | ~$0.01（GPT-4o-mini）|
| 邮件发送 | ✅ 免费 |
| **月总计** | **< $0.5** |

## 📄 License

MIT