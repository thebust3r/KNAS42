# KNAS Break clips -> this PC
# Keeps a copy of the break clips KNAS records in a "break-clips" folder next to this file, so
# ErsatzTV on this PC can play them. A missing clip is put back on the next check. Runs by itself (set up by
# "Get KNAS Break Clips.bat"; it checks every 5 minutes). You don't need to edit or replace this file:
#   - it updates itself from KNAS whenever KNAS has a newer version
#   - only new or changed clips are downloaded, and each is swapped in all at once, so ErsatzTV
#     never finds a clip missing
#   - clips KNAS no longer makes are removed (never ones it's still recording)
#   - it passes ErsatzTV's API key to KNAS and tells KNAS when clips changed, so KNAS can ask
#     ErsatzTV to rescan the clips right away
param([string]$NAS = "http://YOUR_NAS_IP:8642", [switch]$NoUpdate)

if ($NAS -like "*YOUR_NAS_IP*") {
    Write-Host "This copy doesn't know your KNAS address. Download Get KNAS Break Clips.bat from the KNAS setup page and run that instead."
    exit 1
}
$ProgressPreference = "SilentlyContinue"   # much faster downloads in Windows PowerShell
$Here = $PSScriptRoot
$Dest = Join-Path $Here "break-clips"
$Work = Join-Path $Here "break-clips-download"
$Log = Join-Path $Here "knas-clip-sync-log.txt"
function Say($msg) {
    Write-Host $msg
    try {
        $old = @()
        if (Test-Path -LiteralPath $Log) { $old = @(Get-Content -LiteralPath $Log -Tail 300) }
        $old + ((Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "  " + $msg) | Set-Content -LiteralPath $Log
    } catch { }
}

# ---- 1. Update myself if KNAS has a newer copier ----
if (-not $NoUpdate -and $PSCommandPath) {
    try {
        $latest = [string](Invoke-WebRequest -UseBasicParsing -Uri "$NAS/api/setup/download/clip-sync.ps1" -TimeoutSec 20).Content
        $mine = [System.IO.File]::ReadAllText($PSCommandPath)
        if ($latest -match "KNAS Break clips" -and $latest.Trim() -ne $mine.Trim()) {
            [System.IO.File]::WriteAllText($PSCommandPath, $latest)
            Say "Updated the clip copier to the latest version"
            & (Get-Process -Id $PID).Path -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath -NAS $NAS -NoUpdate
            exit $LASTEXITCODE
        }
    } catch { }
}

# ---- 1b. Keep the background check set up the current way: every 5 minutes, with no window ----
# (Older setups ran every 15 minutes and flashed a window. This moves them over by itself.)
if ($env:OS -eq "Windows_NT" -and $PSCommandPath) {
    try {
        $t = Get-ScheduledTask -TaskName "KNAS Break Clips" -ErrorAction Stop
        $vbs = Join-Path $Here "knas-clip-run.vbs"
        $want = 'CreateObject("WScript.Shell").Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""' + $PSCommandPath + '""", 0, False'
        if (-not (Test-Path -LiteralPath $vbs) -or ([System.IO.File]::ReadAllText($vbs)).Trim() -ne $want) {
            Set-Content -LiteralPath $vbs -Encoding ASCII -Value $want
        }
        $a = $t.Actions | Select-Object -First 1
        $ok = ("" + $a.Execute) -match 'wscript' -and ("" + $a.Arguments).Contains($vbs) -and ("" + $t.Triggers[0].Repetition.Interval) -eq "PT5M"
        if (-not $ok) {
            Start-Process -FilePath "schtasks.exe" -WindowStyle Hidden -Wait -ArgumentList ('/Create /TN "KNAS Break Clips" /SC MINUTE /MO 5 /F /TR "wscript.exe \"' + $vbs + '\""')
            Say "Switched the background check to every 5 minutes, with no window"
        }
    } catch { }
}

New-Item -ItemType Directory -Force -Path $Dest, $Work | Out-Null

# ---- 2. Ask KNAS which clips it has ----
try {
    $info = Invoke-RestMethod -Uri "$NAS/api/clips" -TimeoutSec 20
} catch {
    Say "Can't reach KNAS at $NAS. Is the NAS on?"
    exit 1
}

# ---- 3. Copy new or changed clips ----
$names = @()
$changed = $false
foreach ($f in @($info.files)) {
    if (-not $f.name) { continue }
    $names += $f.name
    $local = Join-Path $Dest $f.name
    $remoteTime = [DateTimeOffset]::FromUnixTimeSeconds([int64]$f.mtime).LocalDateTime
    if (Test-Path -LiteralPath $local) {
        $item = Get-Item -LiteralPath $local
        if ($item.Length -eq [int64]$f.size -and $item.LastWriteTime -ge $remoteTime.AddSeconds(-2)) { continue }
    }
    $part = Join-Path $Work $f.name
    try {
        Invoke-WebRequest -Uri ("$NAS/break-clips/" + [uri]::EscapeDataString($f.name)) -OutFile $part -UseBasicParsing -TimeoutSec 900
    } catch {
        Say "Couldn't download $($f.name): $($_.Exception.Message)"
        Remove-Item -LiteralPath $part -ErrorAction SilentlyContinue
        continue
    }
    # Swap the new clip in, in one step, so there's never a moment the clip is missing.
    # The swap keeps a backup of the old clip until it's done: if Windows can't finish it (the old
    # clip is playing, or antivirus is still scanning the new file), both files stay exactly as they
    # were, and we try again in a few seconds, then next time.
    $backup = Join-Path $Work ($f.name + ".old")
    $done = $false
    for ($try = 1; $try -le 4 -and -not $done; $try++) {
        try {
            Remove-Item -LiteralPath $backup -ErrorAction SilentlyContinue
            if (Test-Path -LiteralPath $local) {
                [System.IO.File]::Replace($part, $local, $backup, $true)
            } else {
                [System.IO.File]::Move($part, $local)
            }
            $done = $true
        } catch {
            if (-not (Test-Path -LiteralPath $local) -and (Test-Path -LiteralPath $backup)) {
                try { [System.IO.File]::Move($backup, $local) } catch { }   # never leave the clip missing
            }
            Start-Sleep -Seconds 5
        }
    }
    Remove-Item -LiteralPath $backup -ErrorAction SilentlyContinue
    if ($done) {
        try { (Get-Item -LiteralPath $local).LastWriteTime = $remoteTime } catch { }
        Say "Got $($f.name)"
        $changed = $true
    } else {
        Say "$($f.name) is playing right now - kept the old one, will update it next time"
        Remove-Item -LiteralPath $part -ErrorAction SilentlyContinue
    }
}

# ---- 4. Remove clips KNAS doesn't make anymore ----
# Only clips that aren't on KNAS's clip list are removed, so clips it's still recording for the
# first time are kept. With break clips turned off in KNAS, nothing is removed.
$keep = @($info.plan) + $names
if ($names.Count -gt 0 -and $info.enabled -ne $false) {
    $old = @(Get-ChildItem -LiteralPath $Dest -Filter "KNAS Break *.ts" | Where-Object { $keep -notcontains $_.Name })
    foreach ($o in $old) {
        try { Remove-Item -LiteralPath $o.FullName -ErrorAction Stop; Say "Removed old clip $($o.Name)"; $changed = $true } catch { }
    }
}

# ---- 5. Give KNAS ErsatzTV's API key ----
# Newer ErsatzTV versions (26.8+) need their API key before KNAS can ask them to rescan the clips.
# ErsatzTV keeps it in api-secrets.json in its config folder on this PC.
function Get-StringValues($o) {
    if ($null -eq $o) { return }
    if ($o -is [string]) { [pscustomobject]@{ Name = ""; Value = $o }; return }
    if ($o -is [System.Collections.IEnumerable]) { foreach ($i in $o) { Get-StringValues $i }; return }
    foreach ($p in $o.PSObject.Properties) {
        if ($p.Value -is [string]) { [pscustomobject]@{ Name = $p.Name; Value = $p.Value } }
        else { Get-StringValues $p.Value }
    }
}
$etvDirs = @($env:ETV_CONFIG_FOLDER)
if ($env:LOCALAPPDATA) { $etvDirs += (Join-Path $env:LOCALAPPDATA "ersatztv") }
if ($env:ProgramData) { $etvDirs += (Join-Path $env:ProgramData "ersatztv") }
if ($env:SystemRoot) { $etvDirs += (Join-Path $env:SystemRoot "System32\config\systemprofile\AppData\Local\ersatztv") }
foreach ($d in ($etvDirs | Where-Object { $_ })) {
    $secrets = Join-Path $d "api-secrets.json"
    if (-not (Test-Path -LiteralPath $secrets)) { continue }
    try {
        $vals = @(Get-StringValues (Get-Content -LiteralPath $secrets -Raw | ConvertFrom-Json)) |
            Where-Object { $_.Value.Length -ge 16 -and $_.Value -match '^[A-Za-z0-9+/=_.\-]+$' }
        $best = @(@($vals | Where-Object { $_.Name -match 'key' }) + @($vals)) | Select-Object -First 1
        if ($best) {
            $body = @{ key = $best.Value } | ConvertTo-Json
            $r = Invoke-RestMethod -Method Post -Uri "$NAS/api/clips/etv-key" -Body $body -ContentType "application/json" -TimeoutSec 10
            if ($r.changed) {
                Say "Gave KNAS the ErsatzTV API key (from $secrets)"
                Start-Sleep -Seconds 4           # KNAS restarts to use it: wait until it's back
                for ($w = 0; $w -lt 15; $w++) {
                    try { Invoke-RestMethod -Uri "$NAS/api/version" -TimeoutSec 3 | Out-Null; break } catch { Start-Sleep -Seconds 2 }
                }
            }
        }
    } catch { }
    break
}

# ---- 6. Tell KNAS the clips changed, so it can ask ErsatzTV to rescan them right away ----
if ($changed) {
    try { Invoke-RestMethod -Method Post -Uri "$NAS/api/clips/copied" -TimeoutSec 10 | Out-Null } catch { }
}
Write-Host "$($names.Count) clips on the NAS. Folder: $Dest"
