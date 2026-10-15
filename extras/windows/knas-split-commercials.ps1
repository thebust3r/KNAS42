# KNAS Commercial Splitter
# Cuts long commercial compilations (like a 3-hour "90s commercials" tape) into one file per
# commercial, by finding the quick fades to black between them. Your original video is never changed.
#
# Easiest: drag your videos onto "Split Commercials.bat". Each video gets a folder next to it
# called "<video name> - clips" with the commercials inside, ready for ErsatzTV.
[CmdletBinding(PositionalBinding = $false)]
param(
  [Parameter(Position = 0, ValueFromRemainingArguments = $true)][string[]]$Files,
  [double]$MinSeconds = 4,      # pieces shorter than this are dropped (flashes, glitches)
  [double]$MaxSeconds = 180,    # pieces longer than this go in a "check these" folder (probably the show)
  [double]$BlackSeconds = 0.08, # how long the black has to last to count as a break
  [switch]$Fast                 # copy instead of re-encode: much faster, cuts can be off by a second
)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$IsWin = ($env:OS -eq "Windows_NT")
$exe = "ffmpeg"; if ($IsWin) { $exe = "ffmpeg.exe" }

function Say($m, $c = "Gray") { Write-Host $m -ForegroundColor $c }

# ---------- find ffmpeg (ErsatzTV for Windows comes with one) ----------
function Find-FFmpeg {
  $c = Get-Command $exe -ErrorAction SilentlyContinue
  if ($c) { return $c.Source }
  $spots = @((Join-Path $here $exe), (Join-Path $here "ffmpeg\bin\$exe"))
  $roots = @($env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:LOCALAPPDATA, $env:USERPROFILE) | Where-Object { $_ }
  foreach ($d in (Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue)) { $roots += $d.Root }
  foreach ($r in $roots) {
    foreach ($sub in @("ErsatzTV", "ErsatzTV\ffmpeg", "ErsatzTV\bin", "ffmpeg\bin", "ffmpeg")) { $spots += (Join-Path $r (Join-Path $sub $exe)) }
  }
  foreach ($s in $spots) { if ($s -and (Test-Path $s)) { return $s } }
  # one level deeper on each drive, for folders like D:\Apps\ErsatzTV-v26.8.1-win-x64
  foreach ($d in (Get-PSDrive -PSProvider FileSystem -ErrorAction SilentlyContinue)) {
    $hit = Get-ChildItem -Path $d.Root -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "*ersatz*" -or $_.Name -like "*ffmpeg*" } |
      ForEach-Object { Get-ChildItem -Path $_.FullName -Filter $exe -Recurse -Depth 2 -ErrorAction SilentlyContinue | Select-Object -First 1 } | Select-Object -First 1
    if ($hit) { return $hit.FullName }
  }
  return $null
}

function Get-FFmpeg {
  $f = Find-FFmpeg
  if ($f) { return $f }
  if (-not $IsWin) { throw "ffmpeg isn't installed. Install it (for example: sudo apt install ffmpeg) and try again." }
  Say "This needs a free video tool called ffmpeg, and it isn't on this PC yet." Yellow
  $ans = Read-Host "Download it now? About 100 MB, saved next to this tool. (Y/N)"
  if ($ans -notmatch '^[Yy]') { throw "Can't split without ffmpeg." }
  $zip = Join-Path $here "knas-ffmpeg-download.zip"   # next to this tool, not on C:
  $dest = Join-Path $here "ffmpeg"
  $ProgressPreference = "SilentlyContinue"
  Say "Downloading ffmpeg..." Cyan
  Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip" -OutFile $zip
  Expand-Archive -Path $zip -DestinationPath $dest -Force; Remove-Item $zip -Force
  $hit = Get-ChildItem -Path $dest -Filter "ffmpeg.exe" -Recurse | Select-Object -First 1
  if (-not $hit) { throw "The ffmpeg download didn't have ffmpeg.exe in it." }
  return $hit.FullName
}

# runs ffmpeg and gives back everything it printed (ffmpeg talks on stderr)
function Run-FF([string]$ff, [string[]]$a) {
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = $ff; $psi.UseShellExecute = $false; $psi.RedirectStandardError = $true; $psi.RedirectStandardOutput = $true; $psi.CreateNoWindow = $true
  $psi.Arguments = ($a | ForEach-Object { if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ } }) -join " "
  $p = [System.Diagnostics.Process]::Start($psi)
  $errTask = $p.StandardError.ReadToEndAsync(); $null = $p.StandardOutput.ReadToEnd(); $p.WaitForExit()
  return @{ code = $p.ExitCode; text = $errTask.Result }
}

function Fmt([double]$s) { $t = [TimeSpan]::FromSeconds($s); return ("{0}:{1:00}:{2:00}" -f [int][math]::Floor($t.TotalHours), $t.Minutes, $t.Seconds) }

function Split-One([string]$ff, [string]$video) {
  $name = [IO.Path]::GetFileNameWithoutExtension($video)
  $outDir = Join-Path (Split-Path -Parent $video) "$name - clips"
  $checkDir = Join-Path $outDir "_long pieces (check these)"
  Say ""; Say "=== $name ===" White
  Say "Looking for the breaks between commercials (this reads the whole video, so a 3-hour tape takes a few minutes)..." Cyan
  $inv = [Globalization.CultureInfo]::InvariantCulture
  $probe = Run-FF $ff @("-hide_banner", "-i", $video)
  $dur = 0
  $m = [regex]::Match($probe.text, 'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)')
  if ($m.Success) { $dur = [int]$m.Groups[1].Value * 3600 + [int]$m.Groups[2].Value * 60 + [double]::Parse($m.Groups[3].Value, $inv) }
  if ($dur -le 0) { Say "  Couldn't read this video. Is it a normal video file?" Red; return }
  $hasAudio = $probe.text -match 'Stream #\d+:\d+[^\n]*: Audio:'
  # one pass finds three things: dark gaps (VHS "black" is often fuzzy gray, so this is forgiving),
  # picture changes (cuts), and short quiet moments in the sound
  $bt = $BlackSeconds.ToString($inv)
  $graph = "[0:v:0]scale=160:-2,blackdetect=d=$($bt):pix_th=0.14:pic_th=0.85,select='gt(scene,0.25)',metadata=print[v]"
  $maps = @("-map", "[v]")
  if ($hasAudio) { $graph += ";[0:a:0]silencedetect=n=-38dB:d=0.06[a]"; $maps += @("-map", "[a]") }
  $r = Run-FF $ff (@("-hide_banner", "-nostats", "-i", $video, "-filter_complex", $graph) + $maps + @("-f", "null", "-"))
  $blacks = @()
  foreach ($b in [regex]::Matches($r.text, 'black_start:\s*([\d.]+)\s+black_end:\s*([\d.]+)')) {
    $bs = [double]::Parse($b.Groups[1].Value, $inv); $be = [double]::Parse($b.Groups[2].Value, $inv)
    if ($be - $bs -le 4) { $blacks += , @($bs, $be) }   # longer than 4 seconds of black is a dark scene, not a break
  }
  $scenes = @()
  foreach ($c in [regex]::Matches($r.text, 'pts_time:([\d.]+)[^\n]*\n[^\n]*lavfi\.scene_score=([\d.]+)')) {
    $scenes += , @([double]::Parse($c.Groups[1].Value, $inv), [double]::Parse($c.Groups[2].Value, $inv))
  }
  $quiet = @(); $qs = $null
  foreach ($q in [regex]::Matches($r.text, 'silence_(start|end):\s*(-?[\d.]+)')) {
    $t = [double]::Parse($q.Groups[2].Value, $inv)
    if ($q.Groups[1].Value -eq "start") { $qs = $t } elseif ($qs -ne $null) { if ($t - $qs -le 3) { $quiet += , @($qs, $t) }; $qs = $null }
  }
  # cuts: [end of the piece before, start of the next one]
  $cuts = @(); $nBlack = 0; $nQuiet = 0; $nTiming = 0
  foreach ($b in $blacks) { $cuts += , @($b[0], $b[1]); $nBlack++ }
  # a picture cut right where the sound goes quiet is almost always a new commercial
  foreach ($q in $quiet) {
    $near = $scenes | Where-Object { $_[0] -ge $q[0] - 0.3 -and $_[0] -le $q[1] + 0.3 } | Sort-Object { - $_[1] } | Select-Object -First 1
    if (-not $near) { continue }
    $t = $near[0]
    if ($cuts | Where-Object { $t -ge $_[0] - 1 -and $t -le $_[1] + 1 }) { continue }
    $cuts += , @($t, $t); $nQuiet++
  }
  $cuts = @($cuts | Sort-Object { $_[0] })
  $pieces = @(); $start = 0.0
  foreach ($c in $cuts) { if ($c[0] -gt $start) { $pieces += , @($start, $c[0]) }; $start = [math]::Max($start, $c[1]) }
  $pieces += , @($start, $dur)
  # Last try for long stretches with no gap at all: commercials are almost always 10, 15, 20, 30, 45 or 60 seconds,
  # so look for a chain of picture cuts that lands on those lengths. Only used when it explains most of the stretch.
  $std = @{ 30 = 3.0; 15 = 2.0; 60 = 2.6; 45 = 1.5; 20 = 1.5; 10 = 1.0; 90 = 1.0; 120 = 1.0 }
  $final = @()
  foreach ($p in $pieces) {
    $len = $p[1] - $p[0]
    if ($len -le 65) { $final += , $p; continue }
    $nodes = @($p[0]) + @($scenes | Where-Object { $_[1] -ge 0.3 -and $_[0] -gt $p[0] + 8 -and $_[0] -lt $p[1] - 8 } | ForEach-Object { $_[0] }) + @($p[1])
    $n = $nodes.Count; $best = New-Object double[] $n; $from = New-Object int[] $n; $cover = New-Object double[] $n
    for ($i = 1; $i -lt $n; $i++) { $best[$i] = -1; $from[$i] = -1 }
    for ($j = 1; $j -lt $n; $j++) {
      for ($i = $j - 1; $i -ge 0; $i--) {
        $d = $nodes[$j] - $nodes[$i]
        if ($d -gt 125) { break }
        if ($best[$i] -lt 0) { continue }
        foreach ($k in $std.Keys) {
          if ([math]::Abs($d - $k) -le 0.45) {
            $v = $best[$i] + $std[$k]
            if ($v -gt $best[$j]) { $best[$j] = $v; $from[$j] = $i; $cover[$j] = $cover[$i] + $d }
          }
        }
      }
    }
    # the chain can stop early; whatever is left after it stays one piece
    $endAt = 0; $endVal = 0
    for ($j = 1; $j -lt $n; $j++) { if ($best[$j] -gt $endVal) { $endVal = $best[$j]; $endAt = $j } }
    if ($endAt -eq 0 -or $cover[$endAt] -lt 0.6 * $len) { $final += , $p; continue }
    $chain = @(); $j = $endAt
    while ($j -gt 0) { $chain = @($nodes[$j]) + $chain; $j = $from[$j] }
    $s0 = $p[0]
    foreach ($t in $chain) { $final += , @($s0, $t); $s0 = $t; if ($t -lt $p[1]) { $nTiming++ } }
    if ($p[1] - $s0 -gt 0.5) { $final += , @($s0, $p[1]) }
  }
  $pieces = $final
  Say ("  Found {0} breaks in {1} of video ({2} dark gaps, {3} quiet cuts, {4} by commercial length)." -f ($nBlack + $nQuiet + $nTiming), (Fmt $dur), $nBlack, $nQuiet, $nTiming)
  # in order: [start, end, folder]
  $all = @(); $keepN = 0; $longN = 0; $dropped = 0
  foreach ($p in $pieces) {
    $len = $p[1] - $p[0]
    if ($len -lt $MinSeconds) { $dropped++ }
    elseif ($len -gt $MaxSeconds) { $longN++; $all += , @($p[0], $p[1], $checkDir) }
    else { $keepN++; $all += , @($p[0], $p[1], $outDir) }
  }
  if (-not $all.Count) { Say "  Nothing to cut out. This video may not have black gaps between commercials." Yellow; return }
  New-Item -ItemType Directory -Force -Path $outDir | Out-Null
  if ($longN) { New-Item -ItemType Directory -Force -Path $checkDir | Out-Null }
  $n = 0; $total = $all.Count
  foreach ($p in $all) {
    $n++
    $out = Join-Path $p[2] ("{0} {1:000}.mp4" -f $name, $n)
    if (Test-Path $out) { Say ("  [{0}/{1}] already done" -f $n, $total) DarkGray; continue }
    $ss = ([math]::Round($p[0], 3)).ToString($inv); $len = ([math]::Round($p[1] - $p[0], 3)).ToString($inv)
    Say ("  [{0}/{1}] {2}  ({3:0} sec)" -f $n, $total, (Fmt $p[0]), ($p[1] - $p[0]))
    $tmp = "$out.part.mp4"
    if ($Fast) { $codec = @("-c", "copy", "-avoid_negative_ts", "make_zero") }
    else { $codec = @("-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-af", "loudnorm=I=-18:TP=-2:LRA=11") }
    $args2 = @("-hide_banner", "-nostats", "-y", "-ss", $ss, "-i", $video, "-t", $len, "-map", "0:v:0", "-map", "0:a:0?") + $codec + @("-movflags", "+faststart", $tmp)
    $res = Run-FF $ff $args2
    if ($res.code -eq 0 -and (Test-Path $tmp)) { Move-Item -Force $tmp $out } else { Say "     couldn't cut this one, skipped" Yellow; if (Test-Path $tmp) { Remove-Item -Force $tmp } }
  }
  Say ("  Done: {0} clips in ""{1}""" -f $keepN, $outDir) Green
  if ($longN) { Say ("  {0} long pieces (over {1:0} sec, probably part of a show) are in ""_long pieces (check these)""." -f $longN, $MaxSeconds) Yellow }
  if ($dropped) { Say ("  Skipped {0} tiny bits under {1:0} sec." -f $dropped, $MinSeconds) DarkGray }
}

try {
  $Files = @($Files | Where-Object { $_ -and $_.Trim() })
  if (-not $Files.Count -and $IsWin) {
    Add-Type -AssemblyName System.Windows.Forms
    $dlg = New-Object System.Windows.Forms.OpenFileDialog
    $dlg.Title = "Pick the long commercial videos to split"; $dlg.Multiselect = $true
    $dlg.Filter = "Videos|*.mp4;*.mkv;*.avi;*.mov;*.m4v;*.mpg;*.mpeg;*.ts;*.wmv;*.webm;*.flv|All files|*.*"
    if ($dlg.ShowDialog() -eq "OK") { $Files = $dlg.FileNames }
  }
  if (-not $Files.Count) { Say "No videos picked. Drag your videos onto ""Split Commercials.bat"" to split them." Yellow; exit 0 }
  $ff = Get-FFmpeg
  Say "Using ffmpeg: $ff" DarkGray
  if ($Fast) { Say "Fast mode: copying instead of re-encoding. Cuts may be off by up to a second." Yellow }
  foreach ($f in $Files) {
    $f = $f.Trim('"')
    if (Test-Path $f -PathType Container) {
      Get-ChildItem -Path $f -File | Where-Object { $_.Extension -match '^\.(mp4|mkv|avi|mov|m4v|mpg|mpeg|ts|wmv|webm|flv)$' } | ForEach-Object { Split-One $ff $_.FullName }
    } elseif (Test-Path $f) { Split-One $ff (Resolve-Path $f).Path } else { Say "Can't find $f" Red }
  }
  Say ""; Say "All done. Your original videos weren't changed." Green
  Say "Next: in ErsatzTV, add the clip folders as a library (type: Other Videos), scan, and make a collection for your commercial breaks." Gray
} catch {
  Say ""; Say ("Something went wrong: " + $_.Exception.Message) Red
}
