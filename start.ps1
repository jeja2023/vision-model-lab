param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8080,
    [switch]$SkipInstall,
    [switch]$SkipFrontendBuild,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$startArgs = @("start.py", "--host", $HostName, "--port", $Port)
if ($SkipInstall) {
    $startArgs += "--skip-install"
}
if ($SkipFrontendBuild) {
    $startArgs += "--skip-frontend-build"
}
if ($RemainingArgs) {
    $startArgs += $RemainingArgs
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    & $python.Source @startArgs
}
else {
    & py -3 @startArgs
}
exit $LASTEXITCODE
