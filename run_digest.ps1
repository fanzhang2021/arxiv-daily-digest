# run_digest.ps1 - 启动脚本

# 加载环境变量配置
. .\env_config.ps1

# 运行主脚本
Write-Host "🚀 开始运行 arXiv Daily Digest..."
python main.py

# 等待用户按键
Write-Host "`n✅ 运行完成！按任意键退出..."
$host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown") | Out-Null
