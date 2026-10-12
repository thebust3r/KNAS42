# KNAS Break clips - one-time setup for a Windows PC running ErsatzTV.
# "Get KNAS Break Clips.bat" downloads and runs this. It:
#   1. picks a folder for the clips (your existing one if you've set this up before)
#   2. gets the clip copier from KNAS and copies the clips the first time
#   3. sets the copier to check by itself every 5 minutes, silently (no windows popping up)
#   4. shows you the clips folder to add in ErsatzTV (and copies it to the clipboard)
param([string]$NAS = "http://YOUR_NAS_IP:8642", [string]$Here = "")

$ProgressPreference = "SilentlyContinue"
$TaskName = "KNAS Break Clips"
function Line { Write-Host ("-" * 64) -ForegroundColor DarkGray }

Write-Host ""
Write-Host "  KNAS Break Clips setup" -ForegroundColor Yellow
Line

# ---- 1. Where the clips go ----
$dir = $null
try {   # set up before? keep using the same folder, so ErsatzTV's library still points at it
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    $a = ($t.Actions | Select-Object -First 1)
    $m = [regex]::Match(("" + $a.Execute + " " + $a.Arguments), '"([^"]+\\)knas-clip-(sync\.ps1|run\.vbs)"')
    if ($m.Success -and (Test-Path -LiteralPath $m.Groups[1].Value)) { $dir = $m.Groups[1].Value }
} catch { }
if (-not $dir -and $Here) {
    $h = [System.IO.Path]::GetFullPath($Here).TrimEnd('\') + '\'
    if ((Test-Path -LiteralPath (Join-Path $h "knas-clip-sync.ps1")) -or (Test-Path -LiteralPath (Join-Path $h "break-clips"))) { $dir = $h }
}
if (-not $dir) { $dir = Join-Path $env:USERPROFILE "KNAS Break Clips" }
$dir = $dir.TrimEnd('\')
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$sync = Join-Path $dir "knas-clip-sync.ps1"
$vbs = Join-Path $dir "knas-clip-run.vbs"
$clips = Join-Path $dir "break-clips"
Write-Host "  Folder: $dir"

# ---- 2. Get the copier and copy the clips ----
Write-Host "  Getting the clip copier from KNAS..."
try {
    Invoke-WebRequest -UseBasicParsing -Uri "$NAS/api/setup/download/clip-sync.ps1" -OutFile $sync -TimeoutSec 30
} catch {
    Write-Host ""
    Write-Host "  Can't reach KNAS at $NAS." -ForegroundColor Red
    Write-Host "  Make sure the NAS is on and this PC is on the same network, then run this again."
    exit 1
}
Write-Host "  Copying the break clips (the first time can take a few minutes)..."
& (Get-Process -Id $PID).Path -NoProfile -ExecutionPolicy Bypass -File $sync -NAS $NAS -NoUpdate

# ---- 3. Check every 5 minutes, hidden ----
# A tiny VBScript starts PowerShell with no window, so nothing flashes on screen. Each check is one
# quick question to KNAS; it only downloads when a clip changed or went missing.
$q = '""'
Set-Content -LiteralPath $vbs -Encoding ASCII -Value ('CreateObject("WScript.Shell").Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ' + $q + $sync + $q + '", 0, False')
$taskOk = $false
try {
    $p = Start-Process -FilePath "schtasks.exe" -WindowStyle Hidden -Wait -PassThru -ArgumentList ('/Create /TN "' + $TaskName + '" /SC MINUTE /MO 5 /F /TR "wscript.exe \"' + $vbs + '\""')
    $taskOk = ($p.ExitCode -eq 0)
} catch { }

# ---- 4. Is ErsatzTV here? ----
$etv = $false
foreach ($base in @($env:LOCALAPPDATA, $env:ProgramData)) {
    if ($base -and (Test-Path -LiteralPath (Join-Path $base "ersatztv"))) { $etv = $true }
}

# ---- 5. Done: tell the person what's next ----
try { Set-Clipboard -Value $clips } catch { }
Line
if ($taskOk) {
    Write-Host "  All set! " -ForegroundColor Green -NoNewline
    Write-Host "The clips stay fresh by themselves (checked every 5 minutes, in the background)."
} else {
    Write-Host "  The clips were copied, but the automatic refresh couldn't be set up." -ForegroundColor Yellow
    Write-Host "  Right-click Get KNAS Break Clips.bat and choose 'Run as administrator' to fix that."
}
Write-Host ""
Write-Host "  Your clips folder (already copied to the clipboard):" -ForegroundColor Yellow
Write-Host "    $clips" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Last step, in ErsatzTV:"
Write-Host "    1. Media Sources > Local > add a library, kind 'Other Videos'"
Write-Host "    2. Add the folder above (paste it), save, and scan the library"
Write-Host "    3. Back in the KNAS setup page (Breaks & clips), enter that library's number"
Write-Host "       so KNAS can tell ErsatzTV when clips change"
if (-not $etv) {
    Write-Host ""
    Write-Host "  (ErsatzTV doesn't seem to be installed on this PC. Run this on the PC that runs ErsatzTV.)" -ForegroundColor DarkYellow
}
Line
try { Start-Process explorer.exe -ArgumentList ('"' + $clips + '"') } catch { }
