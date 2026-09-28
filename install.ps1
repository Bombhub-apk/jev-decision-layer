# Jev Decision Layer Installer for Windows
Write-Host "Installing Jev Decision Layer..." -ForegroundColor Cyan

# Install Python requirements
py -3.13 -m pip install -r "$PSScriptRoot\requirements.txt" --quiet

# Add to user PATH if not present
$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($currentPath -notlike "*$PSScriptRoot*") {
    [Environment]::SetEnvironmentVariable("Path", "$currentPath;$PSScriptRoot", "User")
    Write-Host "Added $PSScriptRoot to User PATH." -ForegroundColor Green
}

# Create initial jev_keys.json from template if not present
$keysFile = Join-Path $PSScriptRoot "jev_keys.json"
if (-not (Test-Path $keysFile)) {
    Copy-Item (Join-Path $PSScriptRoot "jev_keys.example.json") $keysFile
    Write-Host "Initialized jev_keys.json from template." -ForegroundColor Yellow
}

Write-Host "Installation complete! Try running: jev --help" -ForegroundColor Green
