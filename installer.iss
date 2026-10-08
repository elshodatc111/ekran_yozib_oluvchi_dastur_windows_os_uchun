; Inno Setup skripti: oddiy dasturlar kabi o'rnatiladi (Program Files, ish stoli yorlig'i,
; Start menyu, "Dasturlar va komponentlar" orqali o'chirish).
; Jim o'rnatish:  EkranYozuvchi_Setup.exe /VERYSILENT /SUPPRESSMSGBOXES

#define AppName "Ekran Yozuvchi"
#define AppVersion "0.1.0"
#define AppExe "EkranYozuvchi.exe"

[Setup]
AppId={{6E1F6B1C-5C0B-4E5B-9B53-3F5A2A7D9E11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Ekran Yozuvchi
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Standart: administrator (Program Files). Foydalanuvchi xohlasa, faqat o'zi uchun o'rnatishi mumkin.
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=installer_out
OutputBaseFilename=EkranYozuvchi_Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "dist\EkranYozuvchi\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
