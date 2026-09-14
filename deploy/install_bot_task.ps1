# Registers the Task Scheduler job "skidki-bot": the Telegram listener behind the
# "Groups" buttons and the /groups, /status commands. Starts at logon, runs while
# the user is logged on, restarts every minute after a crash. Starts right away.
# Remove:  Unregister-ScheduledTask -TaskName skidki-bot -Confirm:$false
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$vbs = Join-Path $PSScriptRoot "run_hidden.vbs"

$action = New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$vbs`" run_bot.cmd" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName "skidki-bot" -Action $action -Trigger $trigger -Settings $settings `
    -Description "skidki: Telegram listener for notification groups ($root)" -Force | Out-Null
Start-ScheduledTask -TaskName "skidki-bot"

Get-ScheduledTask -TaskName "skidki-bot" | Select-Object TaskName, State | Format-List
