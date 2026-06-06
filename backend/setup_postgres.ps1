# PostgreSQL Setup Script for HHB/FKD Project
# Run this after installing PostgreSQL

$ErrorActionPreference = "Stop"

Write-Host "=== PostgreSQL Setup for HHB/FKD ===" -ForegroundColor Green

# PostgreSQL credentials (default superuser)
$PG_USER = Read-Host "PostgreSQL superuser name (default: postgres)"
if (-not $PG_USER) { $PG_USER = "postgres" }

$PG_PASS = Read-Host "PostgreSQL superuser password" -AsSecureString
$BSTR = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($PG_PASS)
$PG_PASSPlain = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($BSTR)

$PG_HOST = Read-Host "PostgreSQL host (default: localhost)"
if (-not $PG_HOST) { $PG_HOST = "localhost" }

$PG_PORT = Read-Host "PostgreSQL port (default: 5432)"
if (-not $PG_PORT) { $PG_PORT = "5432" }

# Set environment variable for the app
$env:DATABASE_URL = "postgresql://${PG_USER}:${PG_PASSPlain}@${PG_HOST}:${PG_PORT}/hhb_b2b"
Write-Host "`nDATABASE_URL set for current session: postgresql://${PG_USER}:****@${PG_HOST}:${PG_PORT}/hhb_b2b" -ForegroundColor Cyan

# Add to user environment permanently
[Environment]::SetEnvironmentVariable("DATABASE_URL", $env:DATABASE_URL, "User")
Write-Host "DATABASE_URL saved to user environment variables." -ForegroundColor Green

# Test connection
Write-Host "`nTesting connection..." -ForegroundColor Yellow
try {
    $result = & psql -U $PG_USER -h $PG_HOST -p $PG_PORT -d postgres -c "SELECT version();" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Connection successful!" -ForegroundColor Green
    } else {
        Write-Host "Connection failed. Make sure PostgreSQL is running." -ForegroundColor Red
        Write-Host $result
        exit 1
    }
} catch {
    Write-Host "Error connecting: $_" -ForegroundColor Red
    exit 1
}

# Create database
Write-Host "`nCreating database 'hhb_b2b'..." -ForegroundColor Yellow
& psql -U $PG_USER -h $PG_HOST -p $PG_PORT -d postgres -c "CREATE DATABASE hhb_b2b;" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Database may already exist or error occurred. Continuing..." -ForegroundColor Yellow
}

# Create app user (optional, more secure than using superuser)
Write-Host "`nCreating app user 'hhb_app'..." -ForegroundColor Yellow
$HHB_PASS = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 16 | ForEach-Object { [char]$_ })
& psql -U $PG_USER -h $PG_HOST -p $PG_PORT -d postgres -c "CREATE USER hhb_app WITH PASSWORD '${HHB_PASS}';" 2>$null
& psql -U $PG_USER -h $PG_HOST -p $PG_PORT -d hhb_b2b -c "GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO hhb_app;" 2>$null

Write-Host "`n=== Setup Complete ===" -ForegroundColor Green
Write-Host "You can now run the server. It will auto-create tables on first start."
Write-Host "App user password: ${HHB_PASS}" -ForegroundColor Cyan
Write-Host "`nTo use the app user instead of superuser, set:"
Write-Host "DATABASE_URL=postgresql://hhb_app:${HHB_PASS}@${PG_HOST}:${PG_PORT}/hhb_b2b" -ForegroundColor Yellow
