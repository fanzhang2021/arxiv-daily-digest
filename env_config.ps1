# env_config.ps1 - 环境变量配置文件

# 设置环境变量
# $env:OPENAI_API_KEY = "5a62436b582241baafa0f9ef1e1cb795.QTesPEx6CtgZIGX4"
$env:OPENAI_API_KEY = "sk-a475b26458b94254a9a386b370179de4"
$env:EMAIL_ADDRESS = "fanzhanghnu@gmail.com"
$env:EMAIL_PASSWORD = "igde nxbq zkow lagk"
$env:TO_EMAIL = "1400970255@qq.com"
# $env:OPENAI_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
$env:OPENAI_BASE_URL = "https://api.deepseek.com/v1"
$env:SMTP_SERVER = "smtp.gmail.com"
$env:SMTP_PORT = "587"
$env:DAYS_BACK = "3"

# 显示配置信息
Write-Host "环境变量配置完成："
Write-Host "  OPENAI_API_KEY: $($env:OPENAI_API_KEY.Substring(0, 5))..."
Write-Host "  EMAIL_ADDRESS: $env:EMAIL_ADDRESS"
Write-Host "  TO_EMAIL: $env:TO_EMAIL"
Write-Host "  OPENAI_BASE_URL: $env:OPENAI_BASE_URL"
Write-Host "  SMTP_SERVER: $env:SMTP_SERVER"
Write-Host "  DAYS_BACK: $env:DAYS_BACK"
