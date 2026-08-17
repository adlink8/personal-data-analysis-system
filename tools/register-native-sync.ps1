# Register-NativeSync.ps1 - 定时同步 AI 客户端会话 (Phase 62 native discovery seam)
# 用法:
#   pwsh -File tools\register-native-sync.ps1            # 注册每日 23:00 定时任务
#   pwsh -File tools\register-native-sync.ps1 -Unregister # 删除任务
#   pwsh -File tools\register-native-sync.ps1 -RunNow     # 立即执行一次
#
# 任务执行: pk-sync conversations --v2-native
#   = discover 客户端目录 -> stage 新/变更文件 -> NON-active shadow (metadata-only)
#   永不自动激活 (D-18: 激活需人工 --v2-activate + 批准语)。
param(
    [switch]$Unregister,
    [switch]$RunNow,
    [string]$TaskName = "pk-native-conversation-sync",
    [string]$At = "23:00"
)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "[ok] removed scheduled task: $TaskName"
    exit 0
}

$inner = "python -m personal_knowledge.application.sync conversations --v2-native"
$log = Join-Path $repoRoot "var\logs\native-sync.log"
$cmd = "cd /d `"$repoRoot`" && set PYTHONPATH=$repoRoot\src && $inner"

if ($RunNow) {
    Write-Host "[run] $cmd"
    cmd /c $cmd 2>&1
    exit $LASTEXITCODE
}

$trigger = New-ScheduledTaskTrigger -Daily -At $At
$psAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -Command `"$cmd 2>&1 | Out-File -FilePath '$log' -Append; exit `$LASTEXITCODE`"" -WorkingDirectory $repoRoot
Register-ScheduledTask -TaskName $TaskName -Action $psAction -Trigger $trigger -Description "Phase 62 native client-directory conversation sync (discover->stage->shadow, never activates)" -Force | Out-Null
Write-Host "[ok] registered scheduled task: $TaskName @ daily $At"
Write-Host "     $inner"
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State | Format-List
