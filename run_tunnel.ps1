# Cloudflare Tunnel Runner Script
# This script runs the cloudflared tunnel to expose LMS to the internet

param(
    [Parameter(Mandatory=$false)]
    [string]$Token = ""
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Cloudflare Tunnel Runner" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if cloudflared is installed
$cloudflaredPath = "$env:USERPROFILE\.cloudflared\cloudflared.exe"
if (-not (Test-Path $cloudflaredPath)) {
    # Try system PATH
    $cloudflaredPath = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
    if (-not $cloudflaredPath) {
        Write-Host "[ERROR] cloudflared is not installed!" -ForegroundColor Red
        Write-Host "Run install_cloudflared.ps1 first, or install Docker Desktop." -ForegroundColor Yellow
        exit 1
    }
}

Write-Host "[OK] Found cloudflared at: $cloudflaredPath" -ForegroundColor Green
Write-Host ""

# If no token provided, prompt for it
if ([string]::IsNullOrEmpty($Token)) {
    Write-Host "[INFO] To get your tunnel token:" -ForegroundColor Blue
    Write-Host "  1. Go to https://one.dash.cloudflare.com/" -ForegroundColor Gray
    Write-Host "  2. Networks > Tunnels > Create a tunnel" -ForegroundColor Gray
    Write-Host "  3. Select 'Cloudflared' and copy the token" -ForegroundColor Gray
    Write-Host ""
    $Token = Read-Host "Enter your Cloudflare Tunnel token"
}

if ([string]::IsNullOrEmpty($Token)) {
    Write-Host "[ERROR] Token is required!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[INFO] Starting Cloudflare Tunnel..." -ForegroundColor Blue
Write-Host "[INFO] Press Ctrl+C to stop the tunnel" -ForegroundColor Gray
Write-Host ""

# Run the tunnel
& $cloudflaredPath tunnel --no-autoupdate run --token $Token
