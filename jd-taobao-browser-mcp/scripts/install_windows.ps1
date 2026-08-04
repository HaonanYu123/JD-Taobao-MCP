$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

$tempDir = Join-Path (Get-Location) ".tmp"
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
$resolvedTempDir = (Resolve-Path -LiteralPath $tempDir).Path
$env:TEMP = $resolvedTempDir
$env:TMP = $resolvedTempDir

$browserDir = Join-Path (Get-Location) ".ms-playwright"
New-Item -ItemType Directory -Force -Path $browserDir | Out-Null
$env:PLAYWRIGHT_BROWSERS_PATH = (Resolve-Path -LiteralPath $browserDir).Path

$pythonExe = Get-Command python -ErrorAction SilentlyContinue
if ($pythonExe) {
    $python = @("python")
} else {
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if (-not $pyLauncher) {
        throw "Python was not found. Install Python 3.11+ or add python to PATH."
    }
    $python = @("py", "-3")
}

$pythonArgs = if ($python.Length -gt 1) { $python[1..($python.Length - 1)] } else { @() }
Invoke-Checked $python[0] ($pythonArgs + @("-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"))
Invoke-Checked $python[0] ($pythonArgs + @("-m", "venv", ".venv"))
Invoke-Checked .\.venv\Scripts\python.exe @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Checked .\.venv\Scripts\python.exe @("-m", "pip", "install", "-e", ".[dev]")
Invoke-Checked .\.venv\Scripts\python.exe @("-m", "playwright", "install", "chromium")

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
}

if (-not (Select-String -Path .env -Pattern "^PLAYWRIGHT_BROWSERS_PATH=" -Quiet)) {
    Add-Content -Path .env -Value "PLAYWRIGHT_BROWSERS_PATH=.ms-playwright"
}

Write-Host "Install complete. Run tests with: .\.venv\Scripts\python.exe -m pytest"
Write-Host "Local MCP debug command: .\.venv\Scripts\python.exe server.py"
