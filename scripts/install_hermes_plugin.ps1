# Copies the knowledge-hub Hermes plugin into the Hermes plugins folder (no config changes).
$ErrorActionPreference = "Stop"
$src = Join-Path $PSScriptRoot "..\hermes_plugin\knowledge_hub"
$dest = Join-Path $env:LOCALAPPDATA "hermes\plugins\knowledge-hub"
New-Item -ItemType Directory -Force $dest | Out-Null
# Files dropped from the plugin must not linger in the installed copy.
$keep = (Get-ChildItem $src -File).Name
Get-ChildItem $dest -File | Where-Object { $_.Name -notin $keep } | Remove-Item
Get-ChildItem $src -File | Where-Object { $_.Extension -in ".py", ".yaml" } | Copy-Item -Destination $dest -Force
Write-Host "Copied plugin to $dest"
Get-ChildItem $dest | Select-Object Name
