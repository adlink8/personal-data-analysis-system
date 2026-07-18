#requires -Version 7.0
<#! Thin compatibility wrapper. Canonical implementation: ops/runtime/start-agent-stack.ps1 #>
[CmdletBinding()]
param(
  [switch]$CheckOnly,
  [int]$HealthIntervalSeconds = 5,
  [int]$MaxRestarts = 3,
  [int]$StartTimeoutSeconds = 30,
  [string]$TunnelProxy = '',
  [string]$TunnelDirectory = '',
  [string]$TunnelProfile = 'personal-data-app',
  [switch]$SkipTunnel,
  [switch]$DryRun,
  [int]$RunForSeconds = 0,
  [switch]$PauseOnExit
)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$canonical = Join-Path $projectRoot 'ops\runtime\start-agent-stack.ps1'
$arguments = @(
  '-NoProfile', '-File', $canonical,
  '-Mode', $(if ($CheckOnly) {'Check'} else {'Run'}),
  '-ProjectRoot', $projectRoot,
  '-HealthIntervalSeconds', [string]$HealthIntervalSeconds,
  '-MaxRestarts', [string]$MaxRestarts,
  '-StartTimeoutSeconds', [string]$StartTimeoutSeconds,
  '-RunForSeconds', [string]$RunForSeconds,
  '-TunnelProxy', $TunnelProxy,
  '-TunnelProfile', $TunnelProfile
)
if ($TunnelDirectory) { $arguments += @('-TunnelDirectory', $TunnelDirectory) }
if ($SkipTunnel) { $arguments += '-SkipTunnel' }
if ($DryRun) { $arguments += '-DryRun' }
if ($PauseOnExit) { $arguments += '-PauseOnExit' }
& pwsh @arguments
exit $LASTEXITCODE
