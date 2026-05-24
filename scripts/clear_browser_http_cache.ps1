param(
    [ValidateSet("edge", "chrome", "firefox", "brave", "opera")]
    [string]$Browser = "edge",

    [string]$Profile = "Default",

    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Get-CachePaths {
    param(
        [string]$BrowserName,
        [string]$ProfileName
    )

    $local = $env:LOCALAPPDATA

    switch ($BrowserName) {
        "edge" {
            return @(
                (Join-Path $local "Microsoft\Edge\User Data\$ProfileName\Cache\Cache_Data"),
                (Join-Path $local "Microsoft\Edge\User Data\$ProfileName\Code Cache"),
                (Join-Path $local "Microsoft\Edge\User Data\$ProfileName\GPUCache")
            )
        }
        "chrome" {
            return @(
                (Join-Path $local "Google\Chrome\User Data\$ProfileName\Cache\Cache_Data"),
                (Join-Path $local "Google\Chrome\User Data\$ProfileName\Code Cache"),
                (Join-Path $local "Google\Chrome\User Data\$ProfileName\GPUCache")
            )
        }
        "brave" {
            return @(
                (Join-Path $local "BraveSoftware\Brave-Browser\User Data\$ProfileName\Cache\Cache_Data"),
                (Join-Path $local "BraveSoftware\Brave-Browser\User Data\$ProfileName\Code Cache"),
                (Join-Path $local "BraveSoftware\Brave-Browser\User Data\$ProfileName\GPUCache")
            )
        }
        "opera" {
            $operaBase = if ($ProfileName -eq "Default") {
                Join-Path $local "Opera Software\Opera Stable"
            }
            else {
                Join-Path $local "Opera Software\$ProfileName"
            }

            return @(
                (Join-Path $operaBase "Cache\Cache_Data"),
                (Join-Path $operaBase "Code Cache"),
                (Join-Path $operaBase "GPUCache")
            )
        }
        "firefox" {
            $ffRoot = Join-Path $local "Mozilla\Firefox\Profiles"
            if (-not (Test-Path $ffRoot)) {
                return @()
            }

            if ($ProfileName -eq "Default") {
                $profiles = Get-ChildItem $ffRoot -Directory | Where-Object { $_.Name -match "\.default" }
                $targets = @()
                foreach ($p in $profiles) {
                    $targets += (Join-Path $p.FullName "cache2")
                }
                return $targets
            }

            return @((Join-Path $ffRoot "$ProfileName\cache2"))
        }
    }
}

function Test-BrowserRunning {
    param([string]$BrowserName)

    $procNames = switch ($BrowserName) {
        "edge" { @("msedge") }
        "chrome" { @("chrome") }
        "brave" { @("brave") }
        "opera" { @("opera") }
        "firefox" { @("firefox") }
    }

    foreach ($name in $procNames) {
        if (Get-Process -Name $name -ErrorAction SilentlyContinue) {
            return $true
        }
    }

    return $false
}

Write-Host "Target browser: $Browser"
Write-Host "Profile: $Profile"
Write-Host ""
Write-Host "Note: Browser HTTP cache cannot be safely deleted per single origin/file without browser internals."
Write-Host "This script clears cache directories for one browser profile only."
Write-Host ""

if (Test-BrowserRunning -BrowserName $Browser) {
    throw "Please close $Browser before clearing cache files."
}

$paths = Get-CachePaths -BrowserName $Browser -ProfileName $Profile
if (-not $paths -or $paths.Count -eq 0) {
    throw "No cache directories found for browser '$Browser' and profile '$Profile'."
}

Write-Host "Cache directories to clear:"
$paths | ForEach-Object { Write-Host "- $_" }
Write-Host ""

if (-not $Force) {
    $confirmation = Read-Host "Type YES to continue"
    if ($confirmation -ne "YES") {
        Write-Host "Cancelled."
        exit 1
    }
}

foreach ($path in $paths) {
    if (Test-Path $path) {
        Get-ChildItem -Path $path -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "Cleared: $path"
    }
    else {
        Write-Host "Not found: $path"
    }
}

Write-Host "Done."