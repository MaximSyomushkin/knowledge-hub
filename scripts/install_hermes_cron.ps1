# Copies the digest and reminder wrappers into Hermes' scripts folder and creates the no-agent cron jobs.
# Safe to re-run: a job whose name already exists is left alone (edit it with `hermes cron edit`).
# Example: scripts/install_hermes_cron.ps1 -Deliver discord:<#daily id> -WeeklyDeliver discord:<#weekly id>
param(
    # Where the daily digest and the reminders are posted.
    [Parameter(Mandatory = $true)][string]$Deliver,
    # Where the weekend list and the Sunday recap are posted.
    [Parameter(Mandatory = $true)][string]$WeeklyDeliver
)

$hermesHome = Join-Path $env:LOCALAPPDATA "hermes"
$scripts = Join-Path $hermesHome "scripts"
$hermes = Join-Path $hermesHome "bin\hermes.exe"

New-Item -ItemType Directory -Force $scripts | Out-Null
Copy-Item (Join-Path $PSScriptRoot "..\hermes_plugin\cron\*.py") $scripts -Force
Write-Host "Copied digest wrappers to $scripts"

$existing = (& $hermes cron list 2>$null) -join "`n"
$jobs = @(
    @{ Name = "knowledge-hub-daily";  Schedule = "0 8 * * *";  Script = "khub_digest.py"; Deliver = $Deliver },
    @{ Name = "knowledge-hub-weekly"; Schedule = "0 18 * * 0"; Script = "khub_weekly.py"; Deliver = $WeeklyDeliver },
    # Weekend work list: Friday 18:00 and Saturday 10:00, with the recap. Names must not contain one another
    # (the exists-check below matches by substring).
    @{ Name = "knowledge-hub-weekend-fri"; Schedule = "0 18 * * 5"; Script = "khub_weekend.py"; Deliver = $WeeklyDeliver },
    @{ Name = "knowledge-hub-weekend-sat"; Schedule = "0 10 * * 6"; Script = "khub_weekend.py"; Deliver = $WeeklyDeliver },
    # Every 15 minutes: "⏰ 14:00, in 45 min: ..." for timed items; silent otherwise. Posted with the daily digest.
    @{ Name = "knowledge-hub-remind"; Schedule = "*/15 * * * *"; Script = "khub_remind.py"; Deliver = $Deliver }
)
foreach ($job in $jobs) {
    if ($existing -match [regex]::Escape($job.Name)) {
        Write-Host "exists:  $($job.Name)"
        continue
    }
    & $hermes cron create $job.Schedule --no-agent --script $job.Script --deliver $job.Deliver --name $job.Name 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Error "could not create $($job.Name) (hermes exit $LASTEXITCODE)"
        exit 1
    }
    Write-Host "created: $($job.Name) ($($job.Schedule)) -> $($job.Deliver)"
}
