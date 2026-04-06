#define MyAppName "XMDL"
#define MyAppExeName "XMLDownloader.exe"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "JFL"
#define MyAppURL ""
#define MyAppAssocName MyAppName + " App"
#define MyAppAssocExt ".xmdl"
#define MyAppAssocKey StringChange(MyAppAssocName, " ", "") + MyAppAssocExt

[Setup]
AppId={{C7D3903F-D1A1-4B77-A677-3D0C7A038A10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=build\inno
OutputBaseFilename=XMDL-Setup
SetupIconFile=build\XMDL.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
CloseApplications=no
DirExistsWarning=no
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=XMDL Installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos adicionais:"; Flags: unchecked

[Dirs]
Name: "{sd}\xmdl"; Permissions: users-modify
Name: "{sd}\xmdl\data"; Permissions: users-modify
Name: "{sd}\xmdl\data\db"; Permissions: users-modify
Name: "{sd}\xmdl\data\logs"; Permissions: users-modify
Name: "{sd}\xmdl\data\downloads"; Permissions: users-modify
Name: "{sd}\xmdl\data\cache"; Permissions: users-modify
Name: "{sd}\xmdl\data\certificados"; Permissions: users-modify

[Files]
Source: "build\main.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Executar {#MyAppName}"; Flags: nowait postinstall skipifsilent
