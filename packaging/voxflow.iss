; Inno Setup script for VoxFlow; built by packaging\build.py, which passes AppVersion and IconFile.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6D3A1F52-8B7E-4C0B-9E55-0B6F1E7C2A41}
AppName=VoxFlow
AppVersion={#AppVersion}
AppVerName=VoxFlow {#AppVersion}
AppPublisher=ThermalEX
AppPublisherURL=https://github.com/ThermalEX/VoxFlow
DefaultDirName={autopf}\VoxFlow
DefaultGroupName=VoxFlow
DisableProgramGroupPage=yes
; Per-user install: no admin prompt, and the install folder stays writable for the model server log.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=VoxFlow-Setup-{#AppVersion}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\VoxFlow.exe
UninstallDisplayName=VoxFlow
Compression=lzma2/normal
SolidCompression=no
LZMANumBlockThreads=4
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "chinesesimp"; MessagesFile: "ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
chinesesimp.StartWithWindows=开机时自动启动 VoxFlow
english.StartWithWindows=Start VoxFlow when Windows starts
chinesesimp.LaunchNow=立即启动 VoxFlow
english.LaunchNow=Launch VoxFlow now

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "startup"; Description: "{cm:StartWithWindows}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Models are already compressed; storing them as-is keeps the build fast.
Source: "..\dist\VoxFlow\*"; DestDir: "{app}"; Excludes: "*.gguf,*.onnx"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\dist\VoxFlow\models\*.onnx"; DestDir: "{app}\models"; Flags: ignoreversion recursesubdirs nocompression
Source: "..\dist\VoxFlow\runtime\models\*.gguf"; DestDir: "{app}\runtime\models"; Flags: ignoreversion nocompression

[Icons]
Name: "{autoprograms}\VoxFlow"; Filename: "{app}\VoxFlow.exe"
Name: "{autodesktop}\VoxFlow"; Filename: "{app}\VoxFlow.exe"; Tasks: desktopicon
Name: "{userstartup}\VoxFlow"; Filename: "{app}\VoxFlow.exe"; Tasks: startup

[Run]
Filename: "{app}\VoxFlow.exe"; Description: "{cm:LaunchNow}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\runtime\llama-server.log"

[Code]
// End a running VoxFlow before files are replaced or removed; its job object ends the speech worker and
// llama-server with it. Then wait briefly so Windows releases their DLLs.
procedure StopVoxFlow();
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /T /IM VoxFlow.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(1500);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopVoxFlow();
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    StopVoxFlow();
end;
