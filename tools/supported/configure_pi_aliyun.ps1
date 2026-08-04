#requires -Version 7.0
<#
.SYNOPSIS
  Persist Pi's non-secret DashScope settings and a Windows DPAPI-protected API key.
  The plaintext key is read only into this process and is never written to source.
#>
[CmdletBinding()]
param(
  [string]$ProjectRoot = '',
  [string]$BaseUrl = 'https://ws-5z3x3ey9xg0x32ya.cn-beijing.maas.aliyuncs.com/compatible-mode/v1',
  [string]$Model = 'deepseek-v4-flash-0731',
  [ValidateRange(0, 100000)][double]$CostCeiling = 0
)

$ErrorActionPreference = 'Stop'
if (-not $ProjectRoot) { $ProjectRoot = Join-Path $PSScriptRoot '..\..' }
$ProjectRoot = [IO.Path]::GetFullPath($ProjectRoot)
$configDir = Join-Path $ProjectRoot 'var\config'
$secretDir = Join-Path $ProjectRoot 'var\secrets'
$configPath = Join-Path $configDir 'pi-provider.json'
$secretPath = Join-Path $secretDir 'dashscope.api.dpapi.txt'
New-Item -ItemType Directory -Force -Path $configDir, $secretDir | Out-Null

$secure = Read-Host 'DashScope API Key (input is hidden)' -AsSecureString
$encrypted = ConvertFrom-SecureString -SecureString $secure
Set-Content -LiteralPath $secretPath -Value $encrypted -NoNewline -Encoding utf8

$config = [ordered]@{
  schema = 'pi-provider-config-v1'
  provider = 'dashscope'
  mode = 'aliyun'
  base_url = $BaseUrl
  model = $Model
  cost_ceiling = $CostCeiling
  secret_path = 'var/secrets/dashscope.api.dpapi.txt'
}
$config | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $configPath -Encoding utf8
Write-Output ("Pi provider config persisted: {0}" -f $configPath)
Write-Output ("DPAPI secret persisted: {0}" -f $secretPath)
Write-Output 'The key was not printed and is bound to this Windows user/machine.'
