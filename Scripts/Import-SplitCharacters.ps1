param(
    [string]$EngineRoot = 'C:\Program Files\Epic Games\UE_5.7',
    [string]$SourceRoot = 'E:\Work\CharacterSet\Export'
)

$ErrorActionPreference = 'Stop'
$projectPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\CharacterMakePlugin.uproject')).Path
$scriptPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'import_split_characters.py')).Path
$editor = Join-Path $EngineRoot 'Engine\Binaries\Win64\UnrealEditor.exe'
$reportPath = Join-Path $PSScriptRoot '..\Saved\SplitCharacterImportReport.json'

if (-not (Test-Path -LiteralPath $editor)) {
    throw "UnrealEditor.exe was not found: $editor"
}
if (-not (Test-Path -LiteralPath $SourceRoot)) {
    throw "Split FBX source directory was not found: $SourceRoot"
}

$env:CHARACTERSET_SOURCE_ROOT = (Resolve-Path -LiteralPath $SourceRoot).Path
$startedAt = Get-Date
$argumentLine = '"{0}" "-ExecutePythonScript={1}" -unattended -nop4 -nosplash -nosound -NullRHI -DDC-ForceMemoryCache -DisablePlugins=ModelingToolsEditorMode' -f $projectPath, $scriptPath
$process = Start-Process -FilePath $editor -ArgumentList $argumentLine -WindowStyle Hidden -Wait -PassThru

if (-not (Test-Path -LiteralPath $reportPath)) {
    throw "Unreal did not create the expected import report: $reportPath"
}
if ((Get-Item -LiteralPath $reportPath).LastWriteTime -lt $startedAt) {
    throw "Unreal did not refresh the import report: $reportPath"
}
$report = Get-Content -Raw -LiteralPath $reportPath | ConvertFrom-Json
if ($report.errors.Count -gt 0) {
    throw "Unreal import completed with $($report.errors.Count) errors. See $reportPath"
}
if ($process.ExitCode -ne 0) {
    Write-Warning "Unreal returned exit code $($process.ExitCode), but the import report completed without errors."
}
