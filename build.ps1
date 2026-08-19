$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { throw 'Python não encontrado. Instale Python 3.11+ e marque Add to PATH.' }
Set-Location $project
& $python -m venv .venv
& "$project\.venv\Scripts\python.exe" -m pip install --upgrade pip
& "$project\.venv\Scripts\python.exe" -m pip install -r requirements.txt
& "$project\.venv\Scripts\pyinstaller.exe" --noconfirm --clean --windowed --name JWNoticiasFeed main.py
Write-Host "Executável criado em $project\dist\JWNoticiasFeed\JWNoticiasFeed.exe"
