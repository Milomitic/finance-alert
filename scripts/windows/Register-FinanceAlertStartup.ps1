# Register-FinanceAlertStartup.ps1
# Registers a Windows Task Scheduler entry that launches Finance Alert at user logon.
# Does NOT require admin privileges (runs as the current user only).

$ErrorActionPreference = "Stop"

$ScriptToRun = Join-Path $PSScriptRoot "Run-FinanceAlert.ps1"
if (-not (Test-Path $ScriptToRun)) {
    throw "Run-FinanceAlert.ps1 not found at $ScriptToRun"
}

$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File `"$ScriptToRun`""

$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask `
    -TaskName "FinanceAlert" `
    -Description "Launches Finance Alert at user logon (no admin required)" `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Force | Out-Null

Write-Host "Task 'FinanceAlert' registered. It will launch on the next user logon."
Write-Host "To start it immediately: Start-ScheduledTask -TaskName FinanceAlert"
Write-Host "To verify: Get-ScheduledTask -TaskName FinanceAlert | Get-ScheduledTaskInfo"
