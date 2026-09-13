# Registers the Task Scheduler job "skidki-crawl": a crawl every 2 hours (at :17)
# while the user is logged on. A missed run (PC asleep) starts as soon as possible;
# a second instance never starts while one is still running.
# Remove:  Unregister-ScheduledTask -TaskName skidki-crawl -Confirm:$false
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$vbs = Join-Path $PSScriptRoot "run_hidden.vbs"

$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$vbs`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(17) `
    -RepetitionInterval (New-TimeSpan -Hours 2) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 90) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName "skidki-crawl" -Action $action -Trigger $trigger -Settings $settings `
    -Description "skidki: mechta.kz + evrika.com discount monitor ($root)" -Force | Out-Null

Get-ScheduledTask -TaskName "skidki-crawl" | Get-ScheduledTaskInfo |
    Select-Object TaskName, LastRunTime, NextRunTime | Format-List
