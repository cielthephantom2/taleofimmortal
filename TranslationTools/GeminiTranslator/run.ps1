param(
    [ValidateSet('plan', 'run', 'status', 'apply', 'audit')]
    [string]$Command = 'plan',
    [int]$Limit = 0
)
$ErrorActionPreference = 'Stop'
$pythonPath = 'C:\Users\cielt\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { $pythonPath = 'python' }
if ($Command -eq 'audit') {
    & $pythonPath -X utf8 (Join-Path $PSScriptRoot 'audit_localtext.py')
    exit $LASTEXITCODE
}
$arguments = @('-X', 'utf8', (Join-Path $PSScriptRoot 'translate.py'), $Command, '--config', (Join-Path $PSScriptRoot 'config.json'))
if ($Limit -gt 0) { $arguments += @('--limit', $Limit) }
& $pythonPath @arguments
exit $LASTEXITCODE
