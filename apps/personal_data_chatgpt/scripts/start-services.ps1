<#
.SYNOPSIS
  One-shot launcher + watchdog for personal-data trio (REST API + MCP Apps + Tunnel).
.DESCRIPTION
  - Sequential startup: REST API(8000) -> MCP(8789) -> Tunnel(8081)
  - Health polling; auto-restart on process exit or unhealthy endpoint
  - Max restarts per service (default 5), then caps and alerts
  - try/finally guarantees child cleanup on Ctrl-C
.PARAMETER CheckOnly
  Run preflight checks only; do not start services.
.PARAMETER HealthIntervalSeconds
  Health poll interval (default 5).
.PARAMETER MaxRestarts
  Max restart attempts per service (default 5).
.PARAMETER StartTimeoutSeconds
  Per-service startup readiness timeout (default 30).
.EXAMPLE
  pwsh -NoProfile -File .\scripts\start-services.ps1
  pwsh -NoProfile -File .\scripts\start-services.ps1 -CheckOnly
#>
[CmdletBinding()]
param(
  [switch]$CheckOnly,
  [int]$HealthIntervalSeconds = 5,
  [int]$MaxRestarts = 5,
  [int]$StartTimeoutSeconds = 30,
  # Proxy for the tunnel-client process (it must reach api.openai.com).
  # Empty = no proxy. localhost/127.0.0.1 is always excluded via NO_PROXY so
  # the tunnel->MCP loopback call does not go through the proxy.
  [string]$TunnelProxy = 'http://127.0.0.1:7897'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot   = Resolve-Path (Join-Path $PSScriptRoot '..\..\..')
$AppDir        = Resolve-Path (Join-Path $PSScriptRoot '..')
$TunnelDir     = 'C:\Users\li\Desktop\tunnel-client'
$TunnelProfile = 'personal-data-app'
$LogDir        = Join-Path $AppDir 'logs'
$null = New-Item -ItemType Directory -Force -Path $LogDir
# Watchdog-level log (separate from per-service logs).
$WatchdogLog     = Join-Path $LogDir 'watchdog.log'
$WatchdogArchive = Join-Path $LogDir 'watchdog-archived.log'
$MaxLogSizeMB    = 10

# Service registry: startup order follows this order.
# FilePath is resolved lazily in Invoke-Preflight (so PATH changes during npm
# install are picked up). Here we only record the lookup hint.
$Services = [ordered]@{
  rest = [pscustomobject]@{
    Name      = 'REST API'
    Port      = 8000
    HealthUrl = 'http://127.0.0.1:8000/health'
    FileHint  = 'rag-api.exe'
    FilePath  = $null
    Args      = @('--host', '127.0.0.1', '--port', '8000')
    WorkDir   = $ProjectRoot
    LogFile   = Join-Path $LogDir 'rest-api.log'
  }
  mcp = [pscustomobject]@{
    Name      = 'GPT Apps MCP'
    Port      = 8789
    HealthUrl = 'http://127.0.0.1:8789/health'
    FileHint  = 'node.exe'
    FilePath  = $null
    Args      = @('server.mjs')
    WorkDir   = $AppDir
    LogFile   = Join-Path $LogDir 'mcp-app.log'
  }
  tunnel = [pscustomobject]@{
    Name      = 'Tunnel'
    Port      = 8081
    HealthUrl = 'http://127.0.0.1:8081/healthz'
    FileHint  = (Join-Path $TunnelDir 'tunnel-client.exe')
    FilePath  = $null
    Args      = @('run', '--profile', $TunnelProfile)
    WorkDir   = $TunnelDir
    LogFile   = Join-Path $LogDir 'tunnel.log'
    # tunnel-client must reach api.openai.com; localhost excluded so the
    # loopback call to MCP (8789) never goes through the proxy.
    Env       = [ordered]@{
      HTTPS_PROXY = $TunnelProxy
      HTTP_PROXY  = $TunnelProxy
      NO_PROXY    = '127.0.0.1,localhost'
    }
  }
}

function Resolve-FilePath {
  param([string]$Hint)
  if (-not $Hint) { return $null }
  if (Test-Path $Hint) { return (Resolve-Path $Hint).Path }
  $cmd = Get-Command $Hint -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Source }
  return $null
}

# Per-service live state.
$State = [ordered]@{}
foreach ($key in $Services.Keys) {
  $State[$key] = [pscustomobject]@{
    Key        = $key
    Proc       = $null
    Restarts   = 0
    FailCount  = 0
    Healthy    = $false
    LastStatus = 'pending'
    StartedAt  = $null
  }
}

# ---------- helpers ----------

# Tee output to console (colored) AND watchdog.log (plain), with rotation.
function Write-Log2 {
  param([string]$Level = 'INFO', [string]$Message)
  $ts = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
  $line = "[$ts] [$Level] $Message"
  $color = switch ($Level) {
    'OK'    { 'Green' }
    'WARN'  { 'Yellow' }
    'ERROR' { 'Red' }
    default { 'Cyan' }
  }
  Write-Host $line -ForegroundColor $color
  try {
    if (Test-Path $WatchdogLog) {
      $sizeMB = (Get-Item $WatchdogLog).Length / 1MB
      if ($sizeMB -ge $MaxLogSizeMB) {
        Copy-Item $WatchdogLog $WatchdogArchive -Force
        '' | Out-File -FilePath $WatchdogLog -Encoding UTF8
      }
    }
    $line | Out-File -FilePath $WatchdogLog -Append -Encoding UTF8
  } catch {}
}
function Write-Step2 { param($m) Write-Log2 'INFO' $m }
function Write-Ok2   { param($m) Write-Log2 'OK'    $m }
function Write-Warn2 { param($m) Write-Log2 'WARN'  $m }
function Write-Err2  { param($m) Write-Log2 'ERROR' $m }

# Network diagnostics: is the proxy up? can we reach the OpenAI control plane?
# Logged at startup and on each restart so control-plane failures are obvious.
function Write-NetworkDiag {
  param([string]$ProxyUrl = $TunnelProxy)
  if (-not $ProxyUrl) { return }
  $proxyHost = ($ProxyUrl -replace '^https?://','')
  $proxyUp = $false
  try {
    $null = Invoke-WebRequest -Uri $ProxyUrl -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
    $proxyUp = $true
  } catch {
    # Connection refused actually means the port is reachable (proxy not on HTTP root).
    if ($_.Exception.Message -match 'refused|actively|protocol|300|400|401|403|404') { $proxyUp = $true }
  }
  $apiStatus = 'unknown'
  try {
    $r = Invoke-WebRequest -Uri 'https://api.openai.com/v1/models' -Proxy $ProxyUrl -TimeoutSec 6 -UseBasicParsing -ErrorAction Stop
    $apiStatus = "OK ($($r.StatusCode))"
  } catch {
    $msg = $_.Exception.Message
    if ($msg -match '401|403') { $apiStatus = 'auth-required (network OK)' }
    else { $apiStatus = 'FAIL (' + $msg.Substring(0, [Math]::Min(70, $msg.Length)) + ')' }
  }
  Write-Log2 'DEBUG' ("net: proxy={0} api.openai.com={1}" -f $(if ($proxyUp) { 'UP' } else { 'DOWN' }), $apiStatus)
}

function Test-Health {
  param([string]$Url)
  try {
    $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 4 -ErrorAction Stop
    return ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300)
  } catch {
    return $false
  }
}

function Test-PortBusy {
  param([int]$Port)
  $conn = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
  return [bool]$conn
}

function Stop-ServiceProc {
  param($Entry)
  if ($Entry.Proc -and -not $Entry.Proc.HasExited) {
    try { taskkill.exe /PID $Entry.Proc.Id /T /F 2>$null | Out-Null } catch {}
    try { $Entry.Proc.Kill() } catch {}
    try { $Entry.Proc.WaitForExit(2000) } catch {}
  }
  $Entry.Proc = $null
}

function Start-ServiceProc {
  param($Key)
  $svc   = $Services[$Key]
  $entry = $State[$Key]

  Stop-ServiceProc -Entry $entry
  # Drop any leftover event subscribers from a previous start of this service,
  # otherwise Register-ObjectEvent throws "subscriber already exists".
  Unregister-Event -SourceIdentifier "out_$Key" -ErrorAction SilentlyContinue
  Unregister-Event -SourceIdentifier "err_$Key" -ErrorAction SilentlyContinue

  # If something else (a stale process) holds the port, free it first.
  if (Test-PortBusy -Port $svc.Port) {
    $owning = Get-NetTCPConnection -State Listen -LocalPort $svc.Port -ErrorAction SilentlyContinue
    foreach ($c in $owning) {
      try { taskkill.exe /PID $c.OwningProcess /T /F 2>$null | Out-Null } catch {}
    }
    Start-Sleep -Milliseconds 800
  }

  $psi = [System.Diagnostics.ProcessStartInfo]::new()
  $psi.FileName               = $svc.FilePath
  $psi.Arguments              = ($svc.Args -join ' ')
  $psi.WorkingDirectory       = $svc.WorkDir
  $psi.UseShellExecute        = $false
  $psi.RedirectStandardOutput = $true
  $psi.RedirectStandardError  = $true
  $psi.CreateNoWindow         = $true

  # Inject per-service environment variables (e.g. HTTPS_PROXY for tunnel).
  # ProcessStartInfo copies the current process env by default; just set/override.
  if ($svc.Env) {
    foreach ($k in $svc.Env.Keys) {
      $psi.EnvironmentVariables[$k] = [string]$svc.Env[$k]
    }
  }

  $proc = [System.Diagnostics.Process]::new()
  $proc.StartInfo = $psi

  # Stream stdout+stderr to the service log file (no console spam).
  $logPath = $svc.LogFile
  $outAction = {
    if ($Event.MessageData -and $EventArgs.Data) {
      try { Add-Content -LiteralPath $Event.MessageData -Value $EventArgs.Data -ErrorAction SilentlyContinue } catch {}
    }
  }
  $null = Register-ObjectEvent -InputObject $proc -EventName OutputDataReceived `
    -Action $outAction -MessageData $logPath -SourceIdentifier "out_$Key"
  $null = Register-ObjectEvent -InputObject $proc -EventName ErrorDataReceived `
    -Action $outAction -MessageData $logPath -SourceIdentifier "err_$Key"

  $null = $proc.Start()
  $proc.BeginOutputReadLine()
  $proc.BeginErrorReadLine()
  $entry.Proc       = $proc
  $entry.StartedAt  = Get-Date
  $entry.LastStatus = 'starting'
}

function Wait-ServiceReady {
  param($Key)
  $svc     = $Services[$Key]
  $entry   = $State[$Key]
  $deadline = (Get-Date).AddSeconds($StartTimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if ($entry.Proc.HasExited) {
      $entry.LastStatus = "exited(code=$($entry.Proc.ExitCode))"
      return $false
    }
    if (Test-Health -Url $svc.HealthUrl) {
      $entry.Healthy    = $true
      $entry.LastStatus = 'healthy'
      return $true
    }
    Start-Sleep -Milliseconds 800
  }
  $entry.LastStatus = 'timeout'
  return $false
}

function Format-Duration {
  param($d)
  if (-not $d) { return '-' }
  return ("{0:dd\.hh\:mm\:ss}" -f $d)
}

function Show-Panel {
  param([string]$Title = '')
  if ($Title) { Write-Host "`n=== $Title ===" }
  $now = Get-Date
  foreach ($key in $State.Keys) {
    $e = $State[$key]
    if ($e.Proc -and -not $e.Proc.HasExited) {
      $pid2   = $e.Proc.Id
      $uptime = Format-Duration ($now - $e.StartedAt)
    } else {
      $pid2   = '-'
      $uptime = '-'
    }
    $mark = switch ($e.LastStatus) {
      'healthy'  { 'OK' }
      'starting' { '..' }
      default    { '!!' }
    }
    $svc = $Services[$key]
    Write-Host ("  [{0}] {1,-14} :{2,-6} pid={3,-7} up={4,-12} restarts={5} status={6}" `
      -f $mark, $svc.Name, $svc.Port, $pid2, $uptime, $e.Restarts, $e.LastStatus)
  }
  Write-Host ("  Ctrl-C to exit and clean up all children | logs: {0}\*.log" -f $LogDir)
}

# ---------- preflight ----------

function Invoke-Preflight {
  $ok = $true
  Write-Host "`n=== Preflight ==="
  $profile = Join-Path $env:APPDATA "tunnel-client\$TunnelProfile.yaml"
  if (Test-Path $profile) {
    Write-Ok2 ("tunnel profile -> {0}" -f $profile)
  } else {
    Write-Err2 ("Missing tunnel profile: {0}" -f $profile)
    $ok = $false
  }
  if ($env:CONTROL_PLANE_API_KEY) {
    Write-Ok2 "CONTROL_PLANE_API_KEY is set"
  } else {
    Write-Warn2 "CONTROL_PLANE_API_KEY not set; tunnel may fail to connect"
  }
  if (-not (Test-Path (Join-Path $AppDir 'node_modules'))) {
    Write-Step2 "First run: npm install ..."
    Push-Location $AppDir
    try { npm install --no-audit --no-fund 2>&1 | Out-Host } finally { Pop-Location }
  } else {
    Write-Ok2 ("node_modules ready -> {0}" -f (Join-Path $AppDir 'node_modules'))
  }
  # personal_knowledge must be importable for rag-api to start.
  $pkImport = & python -NoProfile -c "import personal_knowledge,sys; sys.stdout.write(personal_knowledge.__file__)" 2>$null
  if (-not $pkImport) {
    Write-Step2 "personal_knowledge not installed; running pip install -e ."
    Push-Location $ProjectRoot
    try { python -m pip install -e . --disable-pip-version-check 2>&1 | Out-Host } finally { Pop-Location }
  } else {
    Write-Ok2 ("personal_knowledge importable -> {0}" -f $pkImport)
  }
  # tunnel-client reads ~/.config/tunnel-client/<profile>.yaml (XDG-style on Windows).
  # The authoritative profile may live under %APPDATA%\tunnel-client; sync it.
  $XdgDir   = Join-Path $env:USERPROFILE '.config\tunnel-client'
  $SrcProf  = Join-Path $env:APPDATA "tunnel-client\$TunnelProfile.yaml"
  $DstProf  = Join-Path $XdgDir "$TunnelProfile.yaml"
  if (Test-Path $SrcProf) {
    $null = New-Item -ItemType Directory -Force -Path $XdgDir
    if (-not (Test-Path $DstProf) -or ((Get-FileHash $SrcProf).Hash -ne (Get-FileHash $DstProf).Hash)) {
      Copy-Item -LiteralPath $SrcProf -Destination $DstProf -Force
      Write-Step2 ("synced tunnel profile -> {0}" -f $DstProf)
    } else {
      Write-Ok2 ("tunnel profile in XDG location -> {0}" -f $DstProf)
    }
  }
  # Resolve executables AFTER npm install (PATH/local bins may have changed).
  foreach ($key in $Services.Keys) {
    $svc = $Services[$key]
    $svc.FilePath = Resolve-FilePath -Hint $svc.FileHint
    if (-not $svc.FilePath -or -not (Test-Path $svc.FilePath)) {
      Write-Err2 ("Missing executable for {0}: {1}" -f $svc.Name, $svc.FileHint)
      $ok = $false
    } else {
      Write-Ok2 ("{0,-14} -> {1}" -f $svc.Name, $svc.FilePath)
    }
  }
  return $ok
}

# ---------- main ----------

if (-not (Invoke-Preflight)) {
  Write-Err2 "Preflight failed. Fix the issues above first."
  exit 2
}
if ($CheckOnly) {
  Write-Ok2 "Preflight OK (-CheckOnly; not starting services)."
  exit 0
}

# Ctrl-C handling: rely on PowerShell breaking the loop and entering finally.
# Keep sleeps short (1s) so shutdown latency stays low.
$Shutdown = $false

Write-Host "`n=== Network diagnostics ==="
Write-NetworkDiag

Write-Host "`n=== Startup (order: REST -> MCP -> Tunnel) ==="
foreach ($key in $Services.Keys) {
  $svc = $Services[$key]
  Write-Step2 ("Starting {0} on :{1}" -f $svc.Name, $svc.Port)
  Start-ServiceProc -Key $key
  if (Wait-ServiceReady -Key $key) {
    Write-Ok2 ("{0} ready -> {1}" -f $svc.Name, $svc.HealthUrl)
  } else {
    Write-Warn2 ("{0} not ready within {1}s; continuing (watch loop will retry)" -f $svc.Name, $StartTimeoutSeconds)
    $State[$key].Restarts++
  }
}

Write-Host "`n=== Watch loop (interval ${HealthIntervalSeconds}s) ==="
$iteration = 0
try {
  while (-not $Shutdown) {
    $iteration++
    foreach ($key in $Services.Keys) {
      $svc   = $Services[$key]
      $entry = $State[$key]

      $procExited = ($entry.Proc -and $entry.Proc.HasExited)
      $unhealthy  = -not (Test-Health -Url $svc.HealthUrl)

      if ($procExited -or $unhealthy) {
        # Bump fail streak; only restart after 2 consecutive failures (avoids
        # restarting on a single transient health-check blip).
        $entry.FailCount++
        $entry.LastStatus = "failing(#$($entry.FailCount))"
        if ($entry.Restarts -ge $MaxRestarts) {
          if ($entry.LastStatus -ne 'capped') {
            Write-Err2 ("{0} hit max restarts ({1}); stopping. Log: {2}" `
              -f $svc.Name, $MaxRestarts, $svc.LogFile)
            $entry.LastStatus = 'capped'
          }
          continue
        }
        if ($entry.FailCount -lt 2) {
          Write-Warn2 ("{0} unhealthy (exited={1}); waiting 1 more tick before restart" `
            -f $svc.Name, $procExited)
          continue
        }
        Write-Warn2 ("{0} unhealthy (exited={1}); restarting ({2}/{3})..." `
          -f $svc.Name, $procExited, ($entry.Restarts + 1), $MaxRestarts)
        Start-ServiceProc -Key $key
        $entry.Restarts++
        $entry.FailCount = 0
        # On tunnel restart, re-check the control-plane path is reachable.
        if ($key -eq 'tunnel') { Write-NetworkDiag }
        if (Wait-ServiceReady -Key $key) {
          Write-Ok2 ("{0} recovered" -f $svc.Name)
        } else {
          Write-Warn2 ("{0} still not ready after restart" -f $svc.Name)
        }
      } else {
        if ($entry.FailCount -gt 0) {
          Write-Ok2 ("{0} recovered after {1} blip(s)" -f $svc.Name, $entry.FailCount)
        }
        $entry.FailCount  = 0
        $entry.Healthy    = $true
        $entry.LastStatus = 'healthy'
      }
    }

    Show-Panel -Title ("Tick #" + $iteration + " @ " + (Get-Date -Format 'HH:mm:ss'))

    for ($i = 0; $i -lt $HealthIntervalSeconds; $i++) {
      Start-Sleep -Seconds 1
    }
  }
}
finally {
  Write-Host "`n=== Cleanup ==="
  foreach ($key in $Services.Keys) {
    Stop-ServiceProc -Entry $State[$key]
    Write-Host ("  stopped {0}" -f $Services[$key].Name)
  }
  foreach ($key in $Services.Keys) {
    Unregister-Event -SourceIdentifier "out_$key" -ErrorAction SilentlyContinue
    Unregister-Event -SourceIdentifier "err_$key" -ErrorAction SilentlyContinue
  }
  Write-Ok2 "Exited."
}
