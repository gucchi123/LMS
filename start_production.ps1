# LMS Production Startup Script
# This script starts the LMS application with production settings

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  LMS Production Mode Startup Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Set environment variables for production
$env:SECRET_KEY = "039b630f49f62a8a14c78966cc34018a68068974b424aa5877d4c57625a8688a"
$env:FLASK_ENV = "production"
$env:PORT = "5000"

Write-Host "[OK] Environment variables set" -ForegroundColor Green
Write-Host "  - FLASK_ENV: production" -ForegroundColor Gray
Write-Host "  - PORT: 5000" -ForegroundColor Gray
Write-Host ""

# Check if database exists
if (-not (Test-Path "lms.db")) {
    Write-Host "[WARNING] Database not found. Initializing..." -ForegroundColor Yellow
    python init_db.py
    Write-Host ""
}

# Check if videos folder exists
if (-not (Test-Path "videos")) {
    Write-Host "[INFO] Creating videos folder..." -ForegroundColor Blue
    New-Item -ItemType Directory -Path "videos" | Out-Null
}

Write-Host "[INFO] Starting LMS application..." -ForegroundColor Blue
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  LMS is running at:" -ForegroundColor White
Write-Host "  Local:    http://127.0.0.1:5000" -ForegroundColor Green
Write-Host "  Network:  http://0.0.0.0:5000" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Gray
Write-Host ""

# Start the application
python app.py
