# Registers the Task Scheduler job "skidki-crawl": a crawl every 2 hours (at :17)
# while the user is logged on. The task wakes the PC from sleep (owner's request,
# 2026-09-14; needs "Allow wake timers" enabled in the power plan). A missed run
# (PC off) starts as soon as possible; a second instance never starts while one runs.
# Usage:  install_task.ps1 [-Shops "mechta"]  — Shops: comma-separated list
#         (passed to run_crawl.cmd); without it all shops are crawled.
# Remove:  Unregister-ScheduledTask -TaskName skidki-crawl -Confirm:$false
param([string]$Shops = "")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$vbs = Join-Path $PSScriptRoot "run_hidden.vbs"

$argument = "`"$vbs`""
if ($Shops) { $argument = "`"$vbs`" run_crawl.cmd $Shops" }
$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument $argument -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(17) `
    -RepetitionInterval (New-TimeSpan -Hours 2) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 90) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName "skidki-crawl" -Action $action -Trigger $trigger -Settings $settings `
    -Description "skidki: discount monitor, shops: $(if ($Shops) { $Shops } else { 'all' }) ($root)" -Force | Out-Null

Get-ScheduledTask -TaskName "skidki-crawl" | Get-ScheduledTaskInfo |
    Select-Object TaskName, LastRunTime, NextRunTime | Format-List
