#!/usr/bin/env pwsh
<#
.SYNOPSIS
Build the isolated KNeoPiX V1.5 ESP32-S3 IP input prototype. Never uploads.
.PARAMETER SkipFirmware
Generate only the matching application/header and unsigned XKNX product.
.PARAMETER SizeChecks
Also build the interlocked C6 Mini, UP1-GW-UART and 4 MB QuinLED capacity checks.
For measured normal-vs-input comparisons, run python3 scripts/check_input_sizes.py.
#>
param([switch]$SkipFirmware, [switch]$SizeChecks)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $python = (Get-Command python3 -ErrorAction Stop).Source
    $pio = Get-Command pio -ErrorAction SilentlyContinue
    if ($pio) { $pio = $pio.Source }
    elseif ($IsWindows) { $pio = Join-Path $HOME '.platformio/penv/Scripts/pio.exe' }
    else { $pio = Join-Path $HOME '.platformio/penv/bin/pio' }
    $producer = (Get-Command OpenKNXproducer -ErrorAction Stop).Source
    & $python scripts/inputtest.py prepare
    if ($LASTEXITCODE -ne 0) { throw 'Prototype composition failed' }
    & scripts/Build-EffectParameters.ps1 -SkipOpenKNXproducer
    if (!$?) { throw 'Effect generation failed' }
    & lib/OGM-HardwareConfig/generator/Build-HardwareProfile.ps1 -Manifest HardwareManifest.inputtest.generated.xml
    if ($LASTEXITCODE -ne 0) { throw 'Prototype hardware generation failed' }
    & $python scripts/inputtest.py bind
    if ($LASTEXITCODE -ne 0) { throw 'Input conflict binding failed' }
    New-Item -ItemType Directory -Force release/inputtest | Out-Null
    & $producer create --Debug --HeaderFileName=include/knxprod.h --Output=release/inputtest/NeoPixel-InputTest.knxprod src/NeoPixel-InputTest.xml
    if ($LASTEXITCODE -ne 0) { throw 'Prototype application generation failed' }
    & $python scripts/inputtest.py package
    if ($LASTEXITCODE -ne 0) { throw 'Prototype product packaging failed' }
    if (!$SkipFirmware) {
        $environments = @('inputtest_OKNXHW_OPENKNXIAO_KNEOPIX_ESP32S3_V15_IP')
        if ($SizeChecks) {
            $environments += @('inputsize_OKNXHW_OPENKNXIAO_ESP32C6_MINI_V1', 'inputsize_OKNXHW_UP1_GW_UART', 'inputsize_QUINLED_DIG_QUAD_V3_WIFI')
        }
        $buildArgs = @('run')
        foreach ($environment in $environments) { $buildArgs += @('-e', $environment) }
        & $pio @buildArgs
        if ($LASTEXITCODE -ne 0) { throw 'Prototype firmware build failed' }
        $build = '.pio/build/inputtest_OKNXHW_OPENKNXIAO_KNEOPIX_ESP32S3_V15_IP'
        Copy-Item "$build/firmware.bin", "$build/firmware.factory.bin" release/inputtest -Force
        foreach ($environment in $environments) {
            $dest = "release/inputtest/$environment"
            New-Item -ItemType Directory -Force $dest | Out-Null
            Copy-Item ".pio/build/$environment/firmware.bin" $dest -Force
        }
        Write-Host 'Prototype ready in release/inputtest. Firmware has NOT been uploaded.'
    }
}
finally { Pop-Location }
