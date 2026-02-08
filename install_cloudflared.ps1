# Cloudflared Installation Script for Windows
# This script downloads and installs cloudflared without Docker

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Cloudflared Installation Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Define installation paths
$installDir = "$env:USERPROFILE\.cloudflared"
$cloudflaredExe = "$installDir\cloudflared.exe"
$downloadUrl = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"

# Create installation directory
if (-not (Test-Path $installDir)) {
    Write-Host "[INFO] Creating installation directory: $installDir" -ForegroundColor Blue
    New-Item -ItemType Directory -Path $installDir -Force | Out-Null
}

# Download cloudflared
Write-Host "[INFO] Downloading cloudflared..." -ForegroundColor Blue
try {
    Invoke-WebRequest -Uri $downloadUrl -OutFile $cloudflaredExe -UseBasicParsing
    Write-Host "[OK] Downloaded cloudflared successfully" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Failed to download cloudflared: $_" -ForegroundColor Red
    exit 1
}

# Add to PATH if not already there
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$installDir*") {
    Write-Host "[INFO] Adding cloudflared to PATH..." -ForegroundColor Blue
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$installDir", "User")
    $env:Path = "$env:Path;$installDir"
    Write-Host "[OK] Added to PATH (restart PowerShell to take effect)" -ForegroundColor Green
}

# Verify installation
Write-Host ""
Write-Host "[INFO] Verifying installation..." -ForegroundColor Blue
& $cloudflaredExe --version

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Installation Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Run: cloudflared tunnel login" -ForegroundColor White
Write-Host "  2. Create tunnel in Cloudflare dashboard" -ForegroundColor White
Write-Host "  3. Run the tunnel using run_tunnel.ps1" -ForegroundColor White
Write-Host ""
