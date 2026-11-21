; Inno Setup 6 - installer per utente di MeshLens.
; Uso: iscc /DAppVersion=1.0.0 packaging\meshlens.iss   (dalla radice del repository)
#ifndef AppVersion
  #error Passare la versione con /DAppVersion=X.Y.Z
#endif

[Setup]
AppId={{5E3B7C1A-9D24-4F86-B0A7-3C61E8D2F4A9}
AppName=MeshLens
AppVersion={#AppVersion}
AppPublisher=iw8ffg
AppPublisherURL=https://github.com/iw8ffg/meshlens
DefaultDirName={localappdata}\Programs\MeshLens
DefaultGroupName=MeshLens
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
CloseApplications=yes
AppMutex=MeshLensAppMutex
RestartApplications=no
SetupIconFile=..\server\meshlens\assets\meshlens.ico
UninstallDisplayIcon={app}\MeshLens.exe
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=MeshLens-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
italian.AutostartTask=Avvia MeshLens all'accesso a Windows
italian.OptionsGroup=Opzioni:
english.AutostartTask=Start MeshLens when I sign in to Windows
english.OptionsGroup=Options:

[Tasks]
Name: "autostart"; Description: "{cm:AutostartTask}"; GroupDescription: "{cm:OptionsGroup}"; Flags: unchecked

[Files]
; dist\MeshLens contiene anche licenses\ (testi completi delle licenze, generati dalla build)
Source: "..\dist\MeshLens\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENZA.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\MeshLens"; Filename: "{app}\MeshLens.exe"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "MeshLens"; ValueData: """{app}\MeshLens.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
; interattivo: casella "Avvia MeshLens" a fine installazione
Filename: "{app}\MeshLens.exe"; Description: "Avvia MeshLens"; Flags: nowait postinstall skipifsilent runasoriginaluser
; silenzioso (aggiornamento dall'app): riavvia sempre MeshLens
Filename: "{app}\MeshLens.exe"; Flags: nowait skipifnotsilent runasoriginaluser

[UninstallDelete]
; solo gli installer scaricati: i dati restano in %LOCALAPPDATA%\MeshLens\data,
; salvo scelta esplicita nella domanda di disinstallazione (vedi [Code]).
Type: filesandordirs; Name: "{localappdata}\MeshLens\updates"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    if UninstallSilent then Exit;
    DataDir := ExpandConstant('{localappdata}\MeshLens\data');
    if DirExists(DataDir) then
      if MsgBox('Vuoi eliminare anche i dati di MeshLens (database, mappe, impostazioni)?' + #13#10 +
                DataDir + #13#10#13#10 +
                'Do you also want to delete MeshLens data (database, maps, settings)?',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
