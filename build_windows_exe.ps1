Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "Building frontend bundle (ui/dist)..."
Push-Location "ui"
try {
    npm install
    npm run build
}
finally {
    Pop-Location
}

Write-Host "Installing PyInstaller..."
pip install pyinstaller

Write-Host "Creating Windows executable..."
pyinstaller --noconfirm --clean pfin_dash.spec

Write-Host "Build complete. Output folder: dist\\PFIN-Dash"
