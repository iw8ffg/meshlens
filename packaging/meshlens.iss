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
; niente AppMutex: in modalita' silenziosa farebbe rinunciare subito all'installazione se
; MeshLens non si e' ancora chiuso. Si aspetta invece in InitializeSetup (vedi [Code]).
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
; Firma facoltativa (certificato mai nel repository). Uso, dalla radice del repository:
;   iscc /DAppVersion=X /DSignedBuild "/Smeshlens=signtool.exe sign /sha1 <THUMBPRINT> /fd sha256 /tr <URL> /td sha256 $f" packaging\meshlens.iss
; Senza /DSignedBuild l'installer si compila come sempre, senza firma.
#ifdef SignedBuild
SignTool=meshlens
SignedUninstaller=yes
#endif

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

[InstallDelete]
; build precedente: via i file orfani (DLL e asset con hash nel nome) prima della copia.
; I dati dell'utente stanno in %LOCALAPPDATA%\MeshLens, non in {app}.
Type: filesandordirs; Name: "{app}\_internal"

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
const
  AppMutexName = 'MeshLensAppMutex';

// Aspetta (fino a TimeoutSec) che MeshLens si chiuda. Vero se e' chiuso.
function WaitAppClosed(TimeoutSec: Integer): Boolean;
var
  I: Integer;
begin
  for I := 1 to TimeoutSec * 2 do
  begin
    if not CheckForMutexes(AppMutexName) then
    begin
      Result := True;
      Exit;
    end;
    Sleep(500);
  end;
  Result := not CheckForMutexes(AppMutexName);
end;

function InitializeSetup(): Boolean;
begin
  // aggiornamento dall'app: MeshLens si chiude da solo pochi secondi dopo aver avviato l'installer
  Result := WaitAppClosed(30);
  if not Result then
  begin
    if WizardSilent then Exit;  // silenzioso: meglio non installare che sovrascrivere file in uso
    Result := MsgBox('MeshLens e'' ancora aperto: chiudilo dall''icona vicino all''orologio (Esci) e premi OK.' + #13#10 +
                     'MeshLens is still running: close it from the tray icon (Exit) and press OK.',
                     mbInformation, MB_OKCANCEL) = IDOK;
    if Result then Result := WaitAppClosed(15);
  end;
end;

function InitializeUninstall(): Boolean;
begin
  Result := WaitAppClosed(1);
  if not Result then
  begin
    if UninstallSilent then Exit;
    Result := MsgBox('Chiudi MeshLens dall''icona vicino all''orologio (Esci) e premi OK.' + #13#10 +
                     'Close MeshLens from the tray icon (Exit) and press OK.',
                     mbInformation, MB_OKCANCEL) = IDOK;
    if Result then Result := WaitAppClosed(15);
  end;
end;

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
