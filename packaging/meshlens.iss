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

[Tasks]
Name: "autostart"; Description: "Avvia MeshLens all'accesso a Windows"; GroupDescription: "Opzioni:"; Flags: unchecked

[Files]
Source: "..\dist\MeshLens\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\MeshLens"; Filename: "{app}\MeshLens.exe"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "MeshLens"; ValueData: """{app}\MeshLens.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
; interattivo: casella "Avvia MeshLens" a fine installazione
Filename: "{app}\MeshLens.exe"; Description: "Avvia MeshLens"; Flags: nowait postinstall skipifsilent runasoriginaluser
; silenzioso (aggiornamento dall'app): riavvia sempre MeshLens
Filename: "{app}\MeshLens.exe"; Flags: nowait skipifnotsilent runasoriginaluser

; Nessuna sezione [UninstallDelete] per %LOCALAPPDATA%\MeshLens\data: i dati restano,
; salvo scelta esplicita nella domanda di disinstallazione (vedi [Code]).

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
