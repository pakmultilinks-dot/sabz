param(
    [string]$ArduinoCli,
    [string]$CliConfig
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $ArduinoCli) { $ArduinoCli = Join-Path $projectRoot 'data/firmware-tools/arduino-cli.exe' }
if (-not $CliConfig) { $CliConfig = Join-Path $projectRoot 'data/firmware-tools/arduino-cli.yaml' }
$ArduinoCli = (Resolve-Path -LiteralPath $ArduinoCli).Path
$CliConfig = (Resolve-Path -LiteralPath $CliConfig).Path
$coreListing = (& $ArduinoCli --config-file $CliConfig core list --json | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect compiler platform.' }
$platform = $coreListing.platforms | Where-Object id -eq 'esp32:esp32'
if ($platform.installed_version -ne '3.3.0') { throw 'This bench build requires the reviewed reproducibility baseline esp32:esp32@3.3.0.' }
$outputPath = Join-Path $projectRoot 'data/firmware-release/esp32s3_bench'
$buildPath = Join-Path $projectRoot 'data/firmware-build'
$sketchPath = Join-Path $projectRoot 'firmware/esp32s3_bench'
& $ArduinoCli --config-file $CliConfig compile --fqbn esp32:esp32:esp32s3 --warnings all --build-path $buildPath --output-dir $outputPath $sketchPath
if ($LASTEXITCODE -ne 0) { throw 'ESP32 target build failed; do not flash.' }
$artifactHashes = @{}
Get-ChildItem -LiteralPath $outputPath -File | Where-Object Extension -In @('.bin','.elf','.map') | ForEach-Object {
    $artifactHashes[$_.Name] = @{ bytes=$_.Length; sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant() }
}
$sourceHashes = @{}
Get-ChildItem -LiteralPath $sketchPath -File | ForEach-Object {
    $sourceHashes[$_.Name] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
}
$manifest = @{
    target_build_passed=$true; flashed=$false; electrical_verification=$false; road_ready=$false
    fqbn='esp32:esp32:esp32s3'; arduino_core='esp32:esp32@3.3.0'
    build_utc=[DateTime]::UtcNow.ToString('o'); artifacts=$artifactHashes; sources=$sourceHashes
}
$manifestJson = $manifest | ConvertTo-Json -Depth 6
Set-Content -LiteralPath (Join-Path $outputPath 'build-manifest.json') -Value $manifestJson -Encoding utf8
Set-Content -LiteralPath (Join-Path $projectRoot 'validation/esp32-rebuild-manifest.json') -Value $manifestJson -Encoding utf8
Write-Output 'Target build and hash manifest completed. No device was opened or flashed.'
