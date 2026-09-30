; AutoSend installer (Inno Setup). Build with:  build.ps1
#define AppName "AutoSend"
#ifndef AppVersion
  #define AppVersion "1.0.0"      ; the build passes the real one: ISCC /DAppVersion=...
#endif
#define AppPublisher "AutoSend"
#define AppExe "AutoSend.exe"

[Setup]
AppId={{6B0C2E7A-3D8F-4B62-9C41-A17E5D0F2B93}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}
; AutoSend is a PERSONAL app. It installs for the person running the setup and nobody else:
;  - no "all users" choice and no administrator prompt (PrivilegesRequired=lowest, with no override)
;  - one fixed folder inside that person's own profile (no folder page, so it can't be pointed at a shared place)
;  - shortcuts on that person's own Desktop / Start menu only
;  - its data (messages, history, WhatsApp link) lives in that person's own AppData
;  - the uninstall entry is registered for that person only
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#AppName}
DisableDirPage=yes
UsePreviousAppDir=no
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableReadyPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Windows 10 version 1809 or newer: needed for installing fonts per user, and it has the built-in ICU library Qt uses
MinVersion=10.0.17763
OutputDir=output
OutputBaseFilename=AutoSend-Setup-{#AppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
WizardImageFile=wizard_big.bmp
WizardSmallImageFile=wizard_small.bmp
Compression=lzma2/ultra64
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
CloseApplicationsFilter=*.exe
ShowLanguageDialog=no
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Put an AutoSend shortcut on my Desktop"; GroupDescription: "Shortcuts:"; Flags: checkedonce

[Files]
; the program (PyInstaller folder)
Source: "..\dist\AutoSend\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; a starter student list for people who don't have one yet; never overwritten, never removed
Source: "Students.xlsx"; DestDir: "{userdocs}\{#AppName}"; Flags: onlyifdoesntexist uninsneveruninstall
; Sinhala font (Noto Sans Sinhala, free SIL Open Font License). The app loads its own copy every time it starts, so this is
; only so other programs can use it too. Installed for THIS user only, and only if the PC doesn't already have it.
; Removed again on uninstall.
Source: "..\assets\fonts\NotoSansSinhala-Regular.ttf"; DestDir: "{autofonts}"; FontInstall: "Noto Sans Sinhala"; Flags: onlyifdoesntexist; Check: NeedSinhalaFont
Source: "..\assets\fonts\NotoSansSinhala-Bold.ttf"; DestDir: "{autofonts}"; FontInstall: "Noto Sans Sinhala Bold"; Flags: onlyifdoesntexist; Check: NeedSinhalaFont

[Icons]
Name: "{userprograms}\{#AppName}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{userprograms}\{#AppName}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Open AutoSend now"; Flags: nowait postinstall skipifsilent

[Code]
var
  SinhalaFontMissing: Boolean;

// Is a font whose registry name starts with Prefix already installed (for this user or for everyone)?
function FontRegistered(const Prefix: String): Boolean;
var
  Names: TArrayOfString;
  I: Integer;
begin
  Result := False;
  if RegGetValueNames(HKCU, 'Software\Microsoft\Windows NT\CurrentVersion\Fonts', Names) then
    for I := 0 to GetArrayLength(Names) - 1 do
      if Pos(Prefix, Names[I]) = 1 then begin Result := True; Exit; end;
  if RegGetValueNames(HKLM, 'Software\Microsoft\Windows NT\CurrentVersion\Fonts', Names) then
    for I := 0 to GetArrayLength(Names) - 1 do
      if Pos(Prefix, Names[I]) = 1 then begin Result := True; Exit; end;
end;

// Decided once, before anything is copied (otherwise installing the Regular file would make the Bold one look "already there").
function InitializeSetup(): Boolean;
begin
  SinhalaFontMissing := not FontRegistered('Noto Sans Sinhala');
  Result := True;
end;

function NeedSinhalaFont: Boolean;
begin
  Result := SinhalaFontMissing;
end;

// On uninstall, offer to remove saved data (templates, history, WhatsApp link). Default: keep it.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\{#AppName}');
    if DirExists(DataDir) and (not UninstallSilent) then
    begin
      if MsgBox('Also delete your saved AutoSend data (messages, send history and the WhatsApp link)?' + #13#10 + #13#10 +
                'Your Excel files are never touched. Choose No if you plan to reinstall.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
    end;
  end;
end;
