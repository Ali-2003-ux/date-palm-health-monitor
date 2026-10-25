# Palm Monitor keep-alive watchdog.
# Ensures the Docker container (public app) and the Cloudflare tunnel stay
# running; repairs or restarts them if they die, and records the current
# public URL to data\public_url.txt.
# Registered via: schtasks /Create /SC MINUTE /MO 5 /TN PalmMonitorKeepAlive

$ErrorActionPreference = "SilentlyContinue"
$Project = "C:\Users\Lenovo\.zcode\workspace\default\date-palm-monitor"
$Docker = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
$Cloudflared = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$LogFile = Join-Path $Project "logs\keep_alive.log"

function Log($message) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $message" | Out-File -Append -Encoding utf8 $LogFile
}

# --- 1. Docker engine up? ---
$engineUp = & $Docker ps 2>$null
if (-not $engineUp) {
    Log "docker engine down - starting Docker Desktop"
    Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    $deadline = (Get-Date).AddSeconds(120)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 5
        if (& $Docker ps 2>$null) { break }
    }
    if (-not (& $Docker ps 2>$null)) { Log "engine did not come up; aborting run"; exit 1 }
    Log "engine recovered"
}

# --- 2. palm-live container running? ---
$running = & $Docker inspect -f "{{.State.Running}}" palm-live 2>$null
if ($running -ne "true") {
    Log "palm-live not running (state=$running) - restarting via redeploy script"
    & "C:\Program Files\Git\bin\bash.exe" -lc "cd '$($Project -replace '\\','/')' && export PATH='/c/Program Files/Docker/Docker/resources/bin:`$PATH' && bash scripts/redeploy_live.sh" 2>>$LogFile
    Log "redeploy attempt finished"
}

# --- 3. cloudflared tunnel alive? (check it can still reach the app) ---
$tunnelProc = Get-Process cloudflared -ErrorAction SilentlyContinue
$healthy = $false
if ($tunnelProc) {
    $tunnelLog = Get-Content (Join-Path $Project "logs\tunnel.log") -Tail 5 -ErrorAction SilentlyContinue
    $url = $null
    if ($tunnelLog) { $url = ($tunnelLog | Select-String -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -First 1).Matches.Value }
    if ($url) {
        try {
            $resp = Invoke-WebRequest -Uri "$url/health" -TimeoutSec 20 -UseBasicParsing
            if ($resp.StatusCode -eq 200) { $healthy = $true }
        } catch { }
    }
}
if (-not $healthy) {
    Log "tunnel unhealthy/dead - restarting cloudflared"
    Stop-Process -Name cloudflared -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Start-Process -FilePath $Cloudflared -ArgumentList "tunnel", "--url", "http://localhost:7860" `
        -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Project "logs\tunnel.log") `
        -RedirectStandardError (Join-Path $Project "logs\tunnel.err.log")
    Start-Sleep -Seconds 10
    # record the (possibly new) public URL
    $tunnelLog = Get-Content (Join-Path $Project "logs\tunnel.log") -ErrorAction SilentlyContinue
    $url = ($tunnelLog | Select-String -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -First 1).Matches.Value
    if ($url) { $url | Out-File -Encoding ascii (Join-Path $Project "data\public_url.txt"); Log "new tunnel URL: $url" }
} else {
    $url = (Get-Content (Join-Path $Project "data\public_url.txt") -ErrorAction SilentlyContinue)
    if (-not $url) {
        $tunnelLog = Get-Content (Join-Path $Project "logs\tunnel.log") -ErrorAction SilentlyContinue
        $url = ($tunnelLog | Select-String -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -First 1).Matches.Value
        if ($url) { $url | Out-File -Encoding ascii (Join-Path $Project "data\public_url.txt") }
    }
}
