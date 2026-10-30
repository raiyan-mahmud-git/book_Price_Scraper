# ============================================================
# start-dashboard.ps1
# Starts the Book Price Tracker dashboard and opens a public
# Cloudflare Quick Tunnel so anyone can access it via a link.
#
# Usage:  .\start-dashboard.ps1
#         .\start-dashboard.ps1 -Port 9000   (optional)
# ============================================================

param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$venv = Join-Path $root ".venv\Scripts"
$bookScraper = Join-Path $venv "book-scraper.exe"
$db = Join-Path $root "book_data.db"

# ── 1. Verify venv ──────────────────────────────────────────
if (-not (Test-Path $bookScraper)) {
    Write-Error "Venv not found at $venv. Run: pip install -e '.[web]' first."
    exit 1
}

# ── 2. Start dashboard in background ────────────────────────
Write-Host "▶ Starting dashboard on port $Port …" -ForegroundColor Cyan
$server = Start-Process -FilePath $bookScraper `
    -ArgumentList "--db `"$db`" serve --host 0.0.0.0 --port $Port" `
    -PassThru -WindowStyle Hidden

Start-Sleep -Seconds 2
if ($server.HasExited) {
    Write-Error "Dashboard failed to start. Check book_data.db permissions."
    exit 1
}
Write-Host "  ✓ Dashboard PID $($server.Id) running at http://localhost:$Port" -ForegroundColor Green

# ── 3. Find cloudflared ──────────────────────────────────────
$cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cloudflared) {
    # Try WinGet install path
    $candidate = Get-ChildItem "$env:ProgramFiles\cloudflared" -Filter "cloudflared.exe" -Recurse -ErrorAction SilentlyContinue |
                 Select-Object -First 1
    if ($candidate) {
        $cloudflared = $candidate.FullName
    } else {
        Write-Warning "cloudflared not found. Install with: winget install Cloudflare.cloudflared"
        Write-Host "Dashboard is running locally at: http://localhost:$Port" -ForegroundColor Yellow
        Write-Host "Press Ctrl+C to stop."
        Wait-Process -Id $server.Id
        exit 0
    }
} else {
    $cloudflared = $cloudflared.Source
}

# ── 4. Open Cloudflare Quick Tunnel ─────────────────────────
Write-Host "`n▶ Opening Cloudflare Quick Tunnel …" -ForegroundColor Cyan
Write-Host "  (no account needed – link is valid while this window is open)`n" -ForegroundColor DarkGray

$tunnelLog = Join-Path $env:TEMP "cloudflared-tunnel.log"
$tunnel = Start-Process -FilePath $cloudflared `
    -ArgumentList "tunnel --url http://localhost:$Port --no-autoupdate" `
    -PassThru -RedirectStandardError $tunnelLog -WindowStyle Hidden

# Wait for the tunnel URL to appear in the log
$url = $null
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 500
    if (Test-Path $tunnelLog) {
        $content = Get-Content $tunnelLog -Raw -ErrorAction SilentlyContinue
        if ($content -match 'https://[a-z0-9\-]+\.trycloudflare\.com') {
            $url = $Matches[0]
            break
        }
    }
}

if ($url) {
    Write-Host "  ✅  PUBLIC URL: $url" -ForegroundColor Green
    Write-Host "      Share this link with anyone – it's live NOW.`n" -ForegroundColor Green
    # Open in default browser
    Start-Process $url
} else {
    Write-Host "  ⚠  Could not parse tunnel URL. Check: $tunnelLog" -ForegroundColor Yellow
    Write-Host "  Dashboard still running at http://localhost:$Port" -ForegroundColor Cyan
}

Write-Host "Press Ctrl+C to stop both the dashboard and the tunnel." -ForegroundColor DarkGray

# ── 5. Keep script alive until user presses Ctrl+C ──────────
try {
    while ($true) {
        Start-Sleep -Seconds 5
        if ($server.HasExited) {
            Write-Warning "Dashboard exited unexpectedly. Stopping tunnel."
            break
        }
    }
} finally {
    Write-Host "`nShutting down…" -ForegroundColor Yellow
    Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue
    Write-Host "Done." -ForegroundColor Green
}
