; Story Lab - Windows installer (Inno Setup 7).  Build: python build_installer.py
;
; Copies Story Lab (only what the game uses), builds its own Python in the
; chosen folder with uv, adds the icons, then opens Story Lab Setup - where
; the player chooses the pictures, agrees to each model's licence and the
; big downloads happen (resumable, hash-checked). Per user: no admin rights.

#define AppName "Story Lab"
#define AppVersion "12.4"
#define AppPublisher "Vsevolod Kiriouchine"
#define Payload "build\payload"

[Setup]
AppId={{8C3E5D21-6B4F-4E7A-9A51-5F1D2C7B3E90}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppCopyright=Copyright 2026 {#AppPublisher}
AppPublisherURL=https://github.com/Kiriouchine/StoryLab
AppSupportURL=https://github.com/Kiriouchine/StoryLab/issues
AppUpdatesURL=https://github.com/Kiriouchine/StoryLab
VersionInfoVersion=12.4.0.0
DefaultDirName={localappdata}\Programs\StoryLab
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
DirExistsWarning=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=dist
OutputBaseFilename=StoryLabSetup-{#AppVersion}
SetupIconFile=assets\storylab.ico
UninstallDisplayIcon={app}\assets\storylab.ico
UninstallDisplayName={#AppName}
WizardStyle=modern dynamic
WizardImageFile=assets\wizard_202x386.png,assets\wizard_269x515.png,assets\wizard_336x643.png,assets\wizard_430x824.png,assets\wizard_534x1022.png
WizardSmallImageFile=assets\wizard_small_58.png,assets\wizard_small_97.png,assets\wizard_small_124.png,assets\wizard_small_159.png
LicenseFile=payload_docs\LICENSE
; Python + packages, built after the copy (the models are Story Lab Setup's job)
ExtraDiskSpaceRequired=1600000000
Compression=lzma2/max
SolidCompression=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel1=Welcome to Story Lab
WelcomeLabel2=Two characters, a world you describe, and a story that answers you - told aloud and, if you like, painted.%n%nThis installs Story Lab and builds its own Python in the folder you choose (about 1.5 GB, a few minutes, needs the internet). Then Story Lab Setup opens: there you choose the picture styles and agree to each model's licence before anything large is downloaded.
SelectDirDesc=Where should Story Lab live?
SelectDirLabel3=Story Lab, its Python, your stories and saved games go here. If Story Lab Setup installs the picture engine (ComfyUI) for you, it and the picture models go here too - up to about 20 GB, so pick a drive with room.
FinishedHeadingLabel=Story Lab is installed
FinishedLabel=One more step: Story Lab Setup chooses the pictures and downloads the models. You can run it again any time from the Start menu.

[Tasks]
Name: "desktopicon"; Description: "Put a Story Lab icon on the desktop"; GroupDescription: "Icons:"

[Files]
Source: "{#Payload}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Dirs]
Name: "{app}\stories"
Name: "{app}\saves"

[Icons]
Name: "{group}\Story Lab"; Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\story_lab_gui12.py"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\storylab.ico"; Comment: "Play Story Lab"
Name: "{group}\Story Lab Setup (pictures, models, repair)"; Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\setup\storylab_setup.py"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\storylab.ico"
Name: "{group}\Read me"; Filename: "{app}\README.txt"
Name: "{group}\Uninstall Story Lab"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Story Lab"; Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\story_lab_gui12.py"""; WorkingDir: "{app}"; IconFilename: "{app}\assets\storylab.ico"; Comment: "Play Story Lab"; Tasks: desktopicon

[Run]
Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\setup\storylab_setup.py"""; WorkingDir: "{app}"; Description: "Open Story Lab Setup now (choose pictures, download the models)"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\.cache"
Type: filesandordirs; Name: "{app}\downloads"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: filesandordirs; Name: "{app}\setup\__pycache__"
Type: files; Name: "{app}\storylab_paths.json"
Type: files; Name: "{app}\setup\make_env.log"
Type: files; Name: "{app}\image_prompt_settings.json"

[Code]
var
  EnvFailed: Boolean;

function RunPhase(const Phase, Status: String): Boolean;
var
  Code: Integer;
begin
  WizardForm.StatusLabel.Caption := Status;
  WizardForm.FilenameLabel.Caption := '';
  Result := Exec(ExpandConstant('{app}\setup\make_env.cmd'), Phase, ExpandConstant('{app}'),
                 SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0);
  if not Result then
    Log(Format('make_env %s failed with code %d', [Phase, Code]));
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    WizardForm.ProgressGauge.Style := npbstMarquee;
    EnvFailed := not (RunPhase('venv', 'Getting Python 3.11 for Story Lab...')
                      and RunPhase('torch', 'Installing PyTorch for the voices (about 200 MB)...')
                      and RunPhase('packages', 'Installing Story Lab''s Python packages...'));
    WizardForm.ProgressGauge.Style := npbstNormal;
    if EnvFailed then
      SuppressibleMsgBox('Story Lab''s Python could not be finished (no internet, or a download was blocked).' + #13#10 + #13#10 +
             'Run this installer again to retry - nothing is lost. Details: ' +
             ExpandConstant('{app}\setup\make_env.log'), mbError, MB_OK, IDOK);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  App: String;
begin
  App := ExpandConstant('{app}');
  if CurUninstallStep = usUninstall then
  begin
    if DirExists(App + '\ComfyUI_windows_portable') then
      if SuppressibleMsgBox('Also delete the ComfyUI and the picture models that Story Lab Setup downloaded into' + #13#10 +
                App + '\ComfyUI_windows_portable ?' + #13#10 + #13#10 +
                'Choose No to keep them (for example to use ComfyUI on its own).',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
        DelTree(App + '\ComfyUI_windows_portable', True, True, True);
    if DirExists(App + '\runSaves') or DirExists(App + '\stories') or DirExists(App + '\saves') then
      if SuppressibleMsgBox('Also delete your saved games and stories?' + #13#10 + #13#10 +
                'Choose No to keep them in ' + App + '.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
      begin
        DelTree(App + '\runSaves', True, True, True);
        DelTree(App + '\stories', True, True, True);
        DelTree(App + '\saves', True, True, True);
      end;
  end;
  if CurUninstallStep = usPostUninstall then
    SuppressibleMsgBox('Story Lab is removed.' + #13#10 + #13#10 +
           'Ollama and the story model stay installed - they are their own program. Remove them ' +
           'in Windows Settings > Apps if you no longer need them. Picture models put into an ' +
           'existing ComfyUI also stay there.', mbInformation, MB_OK, IDOK);
end;
