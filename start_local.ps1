param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectId,

    [string]$ProxyUrl = "http://127.0.0.1:7890",
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$env:GCP_PROJECT_ID = $ProjectId
$env:HTTP_PROXY = $ProxyUrl
$env:HTTPS_PROXY = $ProxyUrl

Write-Host "[ENV] GCP_PROJECT_ID=$($env:GCP_PROJECT_ID)"
Write-Host "[ENV] HTTP_PROXY=$($env:HTTP_PROXY)"
Write-Host "[ENV] HTTPS_PROXY=$($env:HTTPS_PROXY)"

$workspaceRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonCmd = "python"

$condaPython = "D:\Conda_Data\envs\terroir_hunter\python.exe"
if (Test-Path $condaPython) {
    $pythonCmd = $condaPython
}

$preflightFile = Join-Path $workspaceRoot "_gee_preflight.py"
$preflightCode = @"
import os
import ee

project_id = os.getenv("GCP_PROJECT_ID")
if not project_id:
    raise RuntimeError("GCP_PROJECT_ID is not set")

ee.Initialize(project=project_id)
roots = ee.data.getAssetRoots()
print("[GEE] EE_INIT_OK")
print(f"[GEE] ASSET_ROOTS_OK count={len(roots)}")
"@

Set-Content -Path $preflightFile -Value $preflightCode -Encoding UTF8

try {
    Write-Host "[CHECK] Validating GEE availability..."
    & $pythonCmd $preflightFile
    if ($LASTEXITCODE -ne 0) {
        throw "GEE preflight failed. Check project ID / proxy / authorization."
    }
}
finally {
    Remove-Item $preflightFile -ErrorAction SilentlyContinue
}

Write-Host "[START] GEE preflight passed. Starting backend at http://$BindHost`:$Port"
& $pythonCmd (Join-Path $workspaceRoot "server\main.py")
