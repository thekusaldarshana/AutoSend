# One command to build everything:  powershell -ExecutionPolicy Bypass -File build.ps1
# Result:  dist\AutoSend\AutoSend.exe   (the app)
#          installer\output\AutoSend-Setup-<version>.exe   (the installer)
# Temporary build files are removed afterwards, so the repo stays clean.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = ".\.venv\Scripts\python.exe"

# A running copy of the app would lock its own files and break the build.
$running = Get-Process AutoSend -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$PSScriptRoot\dist\*" }
if ($running) { throw "AutoSend is running from dist\. Close it and run the build again." }

$ver = (& $py -c "from autosend import __version__; print(__version__)").Trim()
Write-Host "Building AutoSend $ver" -ForegroundColor Cyan

Write-Host "1/5  Running tests..." -ForegroundColor Green
& $py -m pytest tests -q
if ($LASTEXITCODE -ne 0) { throw "Tests failed" }

Write-Host "2/5  Making icon and installer pictures..." -ForegroundColor Green
& $py tools\make_icon.py
& $py tools\make_installer_assets.py
& $py tools\make_version_info.py

Write-Host "3/5  Packaging the app (PyInstaller)..." -ForegroundColor Green
& $py -m PyInstaller autosend.spec --noconfirm --distpath dist --workpath build\pyinstaller
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

Write-Host "4/5  Quick start-up check of the packaged app..." -ForegroundColor Green
$env:AUTOSEND_DATA = Join-Path $env:TEMP "autosend_buildcheck"
$env:AUTOSEND_SMOKE = "6"
if (Test-Path $env:AUTOSEND_DATA) { Remove-Item -LiteralPath $env:AUTOSEND_DATA -Recurse -Force }
$p = Start-Process -FilePath ".\dist\AutoSend\AutoSend.exe" -PassThru -Wait
Remove-Item Env:AUTOSEND_SMOKE, Env:AUTOSEND_DATA
if ($p.ExitCode -ne 0) { throw "Packaged app did not start cleanly" }

Write-Host "5/5  Building the installer (Inno Setup)..." -ForegroundColor Green
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 7\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
          "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") |
        Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup not found" }
& $iscc "/DAppVersion=$ver" installer\AutoSend.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }

# tidy up temporary files
if (Test-Path build) { Remove-Item -LiteralPath build -Recurse -Force }
Get-ChildItem -Path . -Filter "build.log" -ErrorAction SilentlyContinue | Remove-Item -Force

Write-Host "`nDone." -ForegroundColor Green
Get-ChildItem installer\output\*.exe | Format-Table Name, @{n="MB";e={[math]::Round($_.Length/1MB,1)}}
