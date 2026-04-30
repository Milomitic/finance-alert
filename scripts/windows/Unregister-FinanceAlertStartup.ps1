# Unregister-FinanceAlertStartup.ps1
# Removes the Finance Alert scheduled task. Safe to run if not registered.

$ErrorActionPreference = "Stop"

$task = Get-ScheduledTask -TaskName "FinanceAlert" -ErrorAction SilentlyContinue
if ($null -eq $task) {
    Write-Host "Task 'FinanceAlert' is not registered. Nothing to do."
    exit 0
}

Stop-ScheduledTask -TaskName "FinanceAlert" -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "FinanceAlert" -Confirm:$false
Write-Host "Task 'FinanceAlert' removed."
