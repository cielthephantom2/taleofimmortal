@echo off
setlocal
set "VYYY_GAME_ROOT=%~dp0"
set "VYYY_UPDATER_FILE=%~f0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command "$s=[IO.File]::ReadAllText($env:VYYY_UPDATER_FILE); $m='#'+' POWERSHELL_PAYLOAD'; & ([ScriptBlock]::Create($s.Substring($s.IndexOf($m)+$m.Length)))"
if errorlevel 1 pause
exit /b
# POWERSHELL_PAYLOAD
$ErrorActionPreference='Stop'
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
$root=[IO.Path]::GetFullPath($env:VYYY_GAME_ROOT)
$exe=Join-Path $root 'guigubahuang.exe'
$mods=Join-Path $root 'Mods'
$dll=Join-Path $mods 'ImmortalModSuite.dll'
$temp=$null
$installed=$false
$backup=$null
try {
 if(-not (Test-Path -LiteralPath $exe -PathType Leaf)){throw 'Put ChoiGame.bat next to guigubahuang.exe.'}
 foreach($p in @(Get-Process -Name guigubahuang -ErrorAction SilentlyContinue)){
  if(-not $p.Path -or [String]::Equals($p.Path,$exe,[StringComparison]::OrdinalIgnoreCase)){throw 'The game is running. Close it before updating.'}
 }
 if(Test-Path -LiteralPath $mods){if((Get-Item -LiteralPath $mods).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Mods must be a regular directory.'}}
 else {New-Item -ItemType Directory -Path $mods | Out-Null}
 if((Test-Path -LiteralPath $dll) -and ((Get-Item -LiteralPath $dll).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'The mod DLL must be a regular file.'}
 try {
  Write-Host 'Checking the latest mod on GitHub...'
  $headers=@{'User-Agent'='Vyyy-Mod-Updater';Accept='application/vnd.github+json'}
  $commit=Invoke-RestMethod -Uri 'https://api.github.com/repos/cielthephantom2/taleofimmortal/commits/main' -Headers $headers -TimeoutSec 20
  if($commit.sha -notmatch '^[a-fA-F0-9]{40}$'){throw 'Invalid GitHub commit.'}
  $base='https://raw.githubusercontent.com/cielthephantom2/taleofimmortal/'+$commit.sha
  $manifest=Invoke-RestMethod -Uri ($base+'/mod-manifest.json') -Headers $headers -TimeoutSec 20
  if($manifest.schema -ne 1 -or $manifest.path -cne 'Mods/ImmortalModSuite.dll' -or $manifest.sha256 -notmatch '^[a-fA-F0-9]{64}$' -or [long]$manifest.bytes -le 0 -or [long]$manifest.bytes -gt 268435456){throw 'Invalid mod manifest.'}
  $current=if(Test-Path -LiteralPath $dll){(Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash}else{''}
  if($current -eq $manifest.sha256){Write-Host ('Already up to date: '+$manifest.version)}
  else {
   Write-Host ('Downloading mod '+$manifest.version+'...')
   $temp=Join-Path $mods ('.ImmortalModSuite.'+[Guid]::NewGuid().ToString('N')+'.download')
   Invoke-WebRequest -Uri ($base+'/Mods/ImmortalModSuite.dll') -Headers $headers -UseBasicParsing -TimeoutSec 120 -OutFile $temp
   if((Get-Item -LiteralPath $temp).Length -ne [long]$manifest.bytes -or (Get-FileHash -LiteralPath $temp -Algorithm SHA256).Hash -ne $manifest.sha256){throw 'Downloaded DLL failed SHA-256 verification.'}
   foreach($p in @(Get-Process -Name guigubahuang -ErrorAction SilentlyContinue)){
    if(-not $p.Path -or [String]::Equals($p.Path,$exe,[StringComparison]::OrdinalIgnoreCase)){throw 'The game started during download. Update cancelled.'}
   }
   if(Test-Path -LiteralPath $dll){
    $backupDir=Join-Path $root 'ModBackups'
    if((Test-Path -LiteralPath $backupDir) -and ((Get-Item -LiteralPath $backupDir).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'ModBackups must be a regular directory.'}
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    $backup=Join-Path $backupDir ('ImmortalModSuite-'+[Guid]::NewGuid().ToString('N')+'.dll.bak')
    [IO.File]::Replace($temp,$dll,$backup)
   } else {[IO.File]::Move($temp,$dll)}
   $temp=$null;$installed=$true
   if((Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash -ne $manifest.sha256){throw 'Installed DLL verification failed.'}
   Write-Host 'Update completed. Your settings and saves were preserved.'
  }
 } catch {
  if($installed){
   if($backup -and (Test-Path -LiteralPath $backup)){[IO.File]::Replace($backup,$dll,$null)}
   else {throw 'Installed DLL verification failed; game launch stopped.'}
  }
  if(-not (Test-Path -LiteralPath $dll)){throw ('No installed mod available. '+$_.Exception.Message)}
  Write-Warning ('Update unavailable; keeping the installed mod. '+$_.Exception.Message)
 }
 foreach($p in @(Get-Process -Name guigubahuang -ErrorAction SilentlyContinue)){
  if(-not $p.Path -or [String]::Equals($p.Path,$exe,[StringComparison]::OrdinalIgnoreCase)){throw 'The game is already running; no second instance will be started.'}
 }
 Write-Host 'Starting Tale of Immortal...'
 Start-Process -FilePath $exe -WorkingDirectory $root
} catch {Write-Host ('ERROR: '+$_.Exception.Message) -ForegroundColor Red;exit 1}
finally {if($temp -and (Test-Path -LiteralPath $temp)){Remove-Item -LiteralPath $temp -Force}}
