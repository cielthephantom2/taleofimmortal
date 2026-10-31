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
$root=[IO.Path]::GetFullPath($env:VYYY_GAME_ROOT).TrimEnd('\')
$exe=Join-Path $root 'guigubahuang.exe'
$stage=$null
$applied=New-Object Collections.Generic.List[object]
function Assert-Idle {
 foreach($p in @(Get-Process -Name guigubahuang -ErrorAction SilentlyContinue)){
  if(-not $p.Path -or [String]::Equals($p.Path,$exe,[StringComparison]::OrdinalIgnoreCase)){throw 'Close the game before updating.'}
 }
}
function Safe-Path([string]$relative){
 if($relative -cnotmatch '^(Mods|ModExportData)/' -or $relative.Contains('\') -or $relative.Contains(':') -or $relative -match '[\x00-\x1f]'){throw 'Invalid update path.'}
 foreach($part in $relative.Split('/')){if(-not $part -or $part -in @('.','..') -or $part.EndsWith('.') -or $part.EndsWith(' ') -or $part -match '[<>"|?*]' -or $part -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)'){throw 'Invalid path segment.'}}
 $target=[IO.Path]::GetFullPath((Join-Path $root $relative))
 if(-not $target.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase)){throw 'Path escaped game directory.'}
 $walk=$target
 while($walk -and $walk.StartsWith($root,[StringComparison]::OrdinalIgnoreCase)){
  if(Test-Path -LiteralPath $walk){if((Get-Item -LiteralPath $walk -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Update path contains a junction or symlink.'}}
  if($walk -eq $root){break};$walk=Split-Path -Parent $walk
 }
 return $target
}
function Verify-File($path,$entry){
 if(-not (Test-Path -LiteralPath $path -PathType Leaf)){throw ('Missing file: '+$entry.path)}
 if((Get-Item -LiteralPath $path).Length -ne [long]$entry.bytes -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $entry.sha256){throw ('Hash/size mismatch: '+$entry.path)}
}
try {
 if(-not (Test-Path -LiteralPath $exe -PathType Leaf)){throw 'Put PlayGame.bat next to guigubahuang.exe.'}
 Assert-Idle
 $headers=@{'User-Agent'='Vyyy-Mod-Updater';Accept='application/vnd.github+json'}
 Write-Host 'Checking Mods and ModExportData on GitHub...'
 $commit=Invoke-RestMethod -Uri 'https://api.github.com/repos/cielthephantom2/taleofimmortal/commits/main' -Headers $headers -TimeoutSec 30
 if($commit.sha -notmatch '^[a-fA-F0-9]{40}$'){throw 'Invalid commit.'}
 $base='https://raw.githubusercontent.com/cielthephantom2/taleofimmortal/'+$commit.sha
 $manifest=Invoke-RestMethod -Uri ($base+'/mods-files.json') -Headers $headers -TimeoutSec 30
 if($manifest.schema -ne 2 -or @($manifest.files).Count -lt 1 -or @($manifest.files).Count -gt 20000){throw 'Invalid file manifest.'}
 $seen=New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
 $changed=New-Object Collections.Generic.List[object]
 $total=0L
 foreach($entry in $manifest.files){
  $dest=Safe-Path $entry.path
  if(-not $seen.Add($dest) -or $entry.sha256 -notmatch '^[a-fA-F0-9]{64}$' -or [long]$entry.bytes -lt 0 -or [long]$entry.bytes -gt 104857600){throw 'Invalid/duplicate manifest entry.'}
  $total += [long]$entry.bytes;if($total -gt 2147483648){throw 'Manifest is too large.'}
  if((Test-Path -LiteralPath $dest) -and -not (Test-Path -LiteralPath $dest -PathType Leaf)){throw 'File target is a directory.'}
  if(-not (Test-Path -LiteralPath $dest) -or (Get-Item -LiteralPath $dest).Length -ne [long]$entry.bytes -or (Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash -ne $entry.sha256){$changed.Add($entry)}
 }
 if(-not $seen.Contains((Join-Path $root 'Mods\ImmortalModSuite.dll'))){throw 'Main DLL is missing from manifest.'}
 if($changed.Count){
  $stage=Join-Path $root ('.VyyyUpdate-'+[Guid]::NewGuid().ToString('N'));New-Item -ItemType Directory -Path $stage | Out-Null
  Write-Host ('Downloading '+$changed.Count+' changed/missing files...')
  if($changed.Count -gt 8){
   # First install: one archive download instead of hundreds of HTTP requests.
   $zip=Join-Path $stage 'release.zip'
   Invoke-WebRequest -Uri ('https://codeload.github.com/cielthephantom2/taleofimmortal/zip/'+$commit.sha) -Headers $headers -UseBasicParsing -TimeoutSec 600 -OutFile $zip
   Add-Type -AssemblyName System.IO.Compression,System.IO.Compression.FileSystem
   $archive=[IO.Compression.ZipFile]::OpenRead($zip)
   try {
    foreach($entry in $changed){
     $name='taleofimmortal-'+$commit.sha+'/'+$entry.path
     $z=$archive.GetEntry($name)
     if($null -eq $z -or $z.Length -ne [long]$entry.bytes){throw ('Archive entry mismatch: '+$entry.path)}
     $file=Join-Path $stage $entry.path;New-Item -ItemType Directory -Path (Split-Path -Parent $file) -Force | Out-Null
     $inputStream=$z.Open();$outputStream=[IO.File]::Create($file)
     try{$inputStream.CopyTo($outputStream)}finally{$inputStream.Dispose();$outputStream.Dispose()}
     Verify-File $file $entry
    }
   } finally {$archive.Dispose()}
  } else {
   foreach($entry in $changed){
    $file=Join-Path $stage $entry.path;New-Item -ItemType Directory -Path (Split-Path -Parent $file) -Force | Out-Null
    $urlPath=($entry.path.Split('/')|ForEach-Object {[Uri]::EscapeDataString($_)}) -join '/'
    Invoke-WebRequest -Uri ($base+'/'+$urlPath) -Headers $headers -UseBasicParsing -TimeoutSec 120 -OutFile $file
    Verify-File $file $entry
   }
  }
  Assert-Idle
  $backupRoot=Join-Path $root 'ModBackups'
  if((Test-Path -LiteralPath $backupRoot) -and ((Get-Item -LiteralPath $backupRoot -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'Backup directory must not be a symlink.'}
  $backup=Join-Path $backupRoot ('FullUpdate-'+[Guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $backup -Force | Out-Null
  foreach($entry in $changed){
   Assert-Idle
   $dest=Safe-Path $entry.path;$file=Join-Path $stage $entry.path;$old=Join-Path $backup $entry.path
   New-Item -ItemType Directory -Path (Split-Path -Parent $dest) -Force | Out-Null
   $existed=Test-Path -LiteralPath $dest
   if($existed){
    New-Item -ItemType Directory -Path (Split-Path -Parent $old) -Force | Out-Null
    [IO.File]::Replace($file,$dest,$old)
   }else{[IO.File]::Move($file,$dest)}
   $applied.Add(@{path=$entry.path;old=$old;existed=$existed})
   Verify-File $dest $entry
  }
  # Verify the whole installed snapshot before launching, including skipped files.
  foreach($entry in $manifest.files){Verify-File (Safe-Path $entry.path) $entry}
  Write-Host ('Updated '+$changed.Count+' files. Backup: '+$backup)
 } else {Write-Host ('Already up to date: '+$manifest.version)}
 Assert-Idle
 Write-Host 'Starting Tale of Immortal...'
 Start-Process -FilePath $exe -WorkingDirectory $root
} catch {
 $failure=$_.Exception.Message;$rollbackFailed=$false
 for($i=$applied.Count-1;$i -ge 0;$i--){
  $record=$applied[$i]
  try{$dest=Safe-Path $record.path;if($record.existed){[IO.File]::Copy($record.old,$dest,$true)}elseif(Test-Path -LiteralPath $dest){Remove-Item -LiteralPath $dest -Force}}
  catch{$rollbackFailed=$true;Write-Warning ('Rollback failed: '+$record.path)}
 }
 if($rollbackFailed){throw ('Update failed; rollback incomplete. Restore from ModBackups. '+$failure)}
 throw ('Update failed; game was not started. Existing files preserved/restored. '+$failure)
} finally {
 if($stage -and (Test-Path -LiteralPath $stage)){
  $resolved=[IO.Path]::GetFullPath($stage)
  if($resolved.StartsWith($root+'\.VyyyUpdate-',[StringComparison]::OrdinalIgnoreCase) -and -not ((Get-Item -LiteralPath $stage -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){
   Remove-Item -LiteralPath $stage -Recurse -Force
  }
 }
}

