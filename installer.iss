; Requer Inno Setup 6: https://jrsoftware.org/isinfo.php

#define MyAppName "JW Notícias Feed"
#define MyAppVersion "0.1.0"
#define MyAppExeName "JWNoticiasFeed.exe"

[Setup]
AppId={{B4A7A9D4-8C8B-4B0B-9C4D-6A1D2C3E4F50}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\JWNoticiasFeed
DefaultGroupName={#MyAppName}
OutputDir=installer-output
OutputBaseFilename=JWNoticiasFeed-Setup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "startup"; Description: "Iniciar automaticamente com o Windows (minimizado)"; GroupDescription: "Opções adicionais:"
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Opções adicionais:"

[Files]
Source: "dist\JWNoticiasFeed\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\JW Notícias Feed"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\JW Notícias Feed"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "JWNoticiasFeed"; ValueData: """{app}\{#MyAppExeName}"" --background"; Flags: uninsdeletevalue; Tasks: startup

    