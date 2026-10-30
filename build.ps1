$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { throw 'Python não encontrado. Instale Python 3.11+ e marque Add to PATH.' }
Set-Location $project
& $python -m venv .venv
$venvPython = "$project\.venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements.txt
$version = (& $venvPython -c "from version import __version__; print(__version__)").Trim()

# O accessible_output2 carrega DLLs (NVDA, JAWS...) e usa COM; sem estes
# --collect-all elas não entram no .exe e a versão compilada falha.
& "$project\.venv\Scripts\pyinstaller.exe" --noconfirm --clean --windowed --name JWNoticiasFeed `
    --icon assets\icon.ico --add-data "assets\icon.ico;assets" `
    --collect-all accessible_output2 --collect-all libloader --collect-all platform_utils `
    --hidden-import win32com.client --hidden-import pythoncom --hidden-import pywintypes `
    main.py
Write-Host "Executável criado em $project\dist\JWNoticiasFeed\JWNoticiasFeed.exe"

# Gera o instalador se o Inno Setup 6 estiver instalado.
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if ($iscc) {
    & $iscc "/DMyAppVersion=$version" installer.iss
    Write-Host "Instalador criado em $project\installer-output"
} else {
    Write-Host 'Inno Setup 6 não encontrado; pulei o instalador (veja o README).'
}
