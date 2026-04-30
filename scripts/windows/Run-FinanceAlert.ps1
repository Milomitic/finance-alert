# Run-FinanceAlert.ps1 - invoked by Task Scheduler at user logon.
# Boots the prod-local mode (FastAPI serving the built frontend) on port 8000
# and writes stdout/stderr to a rotated log file.

$ErrorActionPreference = "Stop"

# Resolve the project root: this script lives at <root>/scripts/windows/
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)

# Ensure the log directory exists.
$LogDir = Join-Path $ProjectRoot "backend\data\logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}
$LogFile = Join-Path $LogDir "windows-task.log"

# Simple size-based rotation: rename if >10 MB, keep one .1 backup.
if (Test-Path $LogFile) {
    $size = (Get-Item $LogFile).Length
    if ($size -gt 10MB) {
        $rotated = "$LogFile.1"
        if (Test-Path $rotated) { Remove-Item $rotated -Force }
        Rename-Item $LogFile $rotated
    }
}

# Run uvicorn from backend/ so settings paths and alembic.ini resolve correctly.
Set-Location (Join-Path $ProjectRoot "backend")

# Append both stdout and stderr to the log file.
& uv run uvicorn app.main:app --port 8000 *>> $LogFile
