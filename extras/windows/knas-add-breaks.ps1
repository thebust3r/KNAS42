# KNAS Commercial Breaks
# Adds chapter markers to your episodes at the spots where the commercial breaks used to be, so
# ErsatzTV's "Mid-Roll" filler can play commercials in the middle of the show like real TV.
#
# How it works: from the episode's length it knows roughly where breaks belong (a half-hour show
# had 2 or 3), then looks around each of those spots for the fade to black and silence the show
# left for the original commercial break, and puts the marker exactly there. The picture and sound
# aren't re-encoded or changed; only the chapter list inside the file is added.
#
# Easiest: drag a show's folder (or some episodes) onto "Add Commercial Breaks.bat".
[CmdletBinding(PositionalBinding = $false)]
param(
  [Parameter(Position = 0, ValueFromRemainingArguments = $true)][string[]]$Files,
  [int]$Breaks = 0,          # force this many breaks per episode (0 = pick by the episode's length)
  [double]$Search = 90,      # how far (seconds) around each spot to look for the fade to black
  [switch]$Redo,             # also redo files that already have chapters
  [switch]$Backup,           # keep the original files in a hidden ".knas-originals" folder (needs extra disk space)
  [switch]$NoAsk             # don't ask about backups
)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$IsWin = ($env:OS -eq "Windows_NT")
$exe = "ffmpeg"; if ($IsWin) { $exe = "ffmpeg.exe" }
$inv = [Globalization.CultureInfo]::InvariantCulture
$VIDEO = '^\.(mkv|mp4|m4v|mov|avi|mpg|mpeg|ts|m2ts|wmv|webm|flv)$'
$KEEP_EXT = '^\.(mkv|mp4|m4v|mov)$'   # these can hold chapters; anything else is re-wrapped as .mkv (no re-encode)

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
  if ($ans -notmatch '^[Yy]') { throw "Can't do this without ffmpeg." }
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

$LOG = Join-Path $here "knas-commercial-breaks-log.txt"
function Log([string]$m) { try { Add-Content -Path $LOG -Value ("[" + (Get-Date -Format "yyyy-MM-dd HH:mm:ss") + "] " + $m) } catch {} }

# where the breaks go for a show this long, as fractions of the running time
function Break-Spots([double]$dur) {
  $m = $dur / 60
  $n = $Breaks
  if ($n -le 0) {
    if ($m -lt 5) { $n = 0 }            # a short: no breaks
    elseif ($m -lt 15) { $n = 1 }       # an 11-minute cartoon
    elseif ($m -lt 32) { $n = 2 }       # a half-hour show (22 min)
    elseif ($m -lt 55) { $n = 4 }       # an hour show (42 min)
    elseif ($m -lt 75) { $n = 5 }
    else { $n = [int][math]::Floor($m / 16) }   # movies: about every 16 minutes
  }
  $spots = @()
  if ($n -le 0) { return $spots }
  if ($n -eq 2 -and -not $Breaks) { return @((0.36 * $dur), (0.70 * $dur)) }   # cold open + act 1, act 2, tag
  for ($i = 1; $i -le $n; $i++) { $spots += $dur * $i / ($n + 1) }
  return $spots
}

function Info([string]$ff, [string]$video) {
  $r = Run-FF $ff @("-hide_banner", "-i", $video)
  $dur = 0
  $m = [regex]::Match($r.text, 'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)')
  if ($m.Success) { $dur = [int]$m.Groups[1].Value * 3600 + [int]$m.Groups[2].Value * 60 + [double]::Parse($m.Groups[3].Value, $inv) }
  $ok = $r.text -match 'Stream #\d+:\d+.*Video:'
  $titles = @([regex]::Matches($r.text, 'Chapter #[^\n]*\n\s*Metadata:\s*\n\s*title\s*:\s*([^\r\n]*)') | ForEach-Object { $_.Groups[1].Value.Trim() })
  $ours = ($titles.Count -gt 0) -and (@($titles | Where-Object { $_ -notmatch '^(KNAS )?Part \d+$' }).Count -eq 0)
  return @{ dur = $dur; chapters = ([regex]::Matches($r.text, 'Chapter #')).Count; video = $ok; ours = $ours }
}

# how long the video really runs: reads the whole file quickly (no decoding) and takes the last timestamp.
# Some files don't record their length, or record a wrong one, so this is what we trust.
function Real-Length([string]$ff, [string]$video) {
  $r = Run-FF $ff @("-hide_banner", "-i", $video, "-map", "0:v:0", "-c", "copy", "-f", "null", "-")
  $ms = [regex]::Matches($r.text, 'time=\s*(\d+):(\d+):(\d+(?:\.\d+)?)')
  if (-not $ms.Count) { return 0 }
  $m = $ms[$ms.Count - 1]
  return [int]$m.Groups[1].Value * 3600 + [int]$m.Groups[2].Value * 60 + [double]::Parse($m.Groups[3].Value, $inv)
}

# looks around one spot for a real act break. In order of trust:
#   fade to black + silence  >  fade to black  >  a hard cut during a silence  >  a long silence.
# A plain pause in the middle of a scene doesn't count. If nothing good is near, there's no break here
# (better one break too few than one in the middle of a scene).
function Find-Break([string]$ff, [string]$video, [double]$spot, [double]$dur) {
  $from = [math]::Max(30, $spot - $Search); $to = [math]::Min($dur - 30, $spot + $Search)
  if ($to -le $from) { return $null }
  $r = Run-FF $ff @("-hide_banner", "-nostats", "-ss", $from.ToString($inv), "-t", ($to - $from).ToString($inv), "-i", $video,
    "-map", "0:v:0", "-map", "0:a:0?",
    "-vf", "scale=160:-2,blackdetect=d=0.08:pix_th=0.08:pic_th=0.97,select=gt(scene\,0.30),showinfo",
    "-af", "silencedetect=n=-40dB:d=0.3", "-f", "null", "-")
  $blacks = @(); $quiet = @(); $cuts = @()
  foreach ($b in [regex]::Matches($r.text, 'black_start:\s*([\d.]+)\s+black_end:\s*([\d.]+)')) {
    $s0 = [double]::Parse($b.Groups[1].Value, $inv) + $from; $e0 = [double]::Parse($b.Groups[2].Value, $inv) + $from
    if ($e0 - $s0 -le 6) { $blacks += , @($s0, $e0) }
  }
  $qs = $null
  foreach ($q in [regex]::Matches($r.text, 'silence_(start|end):\s*(-?[\d.]+)')) {
    $v = [double]::Parse($q.Groups[2].Value, $inv) + $from
    if ($q.Groups[1].Value -eq "start") { $qs = $v } elseif ($qs -ne $null) { if ($v - $qs -le 8) { $quiet += , @($qs, $v) }; $qs = $null }
  }
  foreach ($c in [regex]::Matches($r.text, 'Parsed_showinfo[^\n]*pts_time:\s*([\d.]+)')) { $cuts += ([double]::Parse($c.Groups[1].Value, $inv) + $from) }
  $cands = @()
  foreach ($b in $blacks) {
    $both = $false; foreach ($q in $quiet) { if ($q[0] -le $b[1] + 0.4 -and $q[1] -ge $b[0] - 0.4) { $both = $true } }
    if ($both) { $cands += , @((($b[0] + $b[1]) / 2), 6, "fade to black + silence") } else { $cands += , @((($b[0] + $b[1]) / 2), 5, "fade to black") }
  }
  foreach ($q in $quiet) {
    $len = $q[1] - $q[0]
    $cut = $null; foreach ($c in $cuts) { if ($c -ge $q[0] - 0.6 -and $c -le $q[1] + 0.6) { $cut = $c } }
    if ($cut -ne $null -and $len -ge 0.45) { $cands += , @($cut, 4, "scene change during silence") }
    elseif ($len -ge 3.0) { $cands += , @((($q[0] + $q[1]) / 2), 2, "long silence") }
  }
  $best = $null; $bestScore = -1
  foreach ($c in $cands) {
    $score = $c[1] - [math]::Abs($c[0] - $spot) / ($Search * 2)
    if ($score -gt $bestScore) { $bestScore = $score; $best = @{ t = $c[0]; how = $c[2] } }
  }
  return $best
}

# a picture of 1.5 seconds before and after each break, so you can check them
function Preview([string]$ff, [string]$video, [double]$t, [int]$n) {
  $dir = Join-Path (Split-Path -Parent $video) "_break previews"; New-Item -ItemType Directory -Force -Path $dir | Out-Null
  $base = [IO.Path]::GetFileNameWithoutExtension($video)
  $out = Join-Path $dir ("{0} - break {1} at {2}.jpg" -f $base, $n, ((Fmt $t) -replace ':', '-'))
  $a = [math]::Max(0, $t - 1.5).ToString($inv); $b = ($t + 1.5).ToString($inv)
  $fc = "[0:v]scale=480:270:force_original_aspect_ratio=decrease,pad=480:270:(ow-iw)/2:(oh-ih)/2,setsar=1[a];[1:v]scale=480:270:force_original_aspect_ratio=decrease,pad=480:270:(ow-iw)/2:(oh-ih)/2,setsar=1[b];[a][b]hstack=inputs=2"
  $null = Run-FF $ff @("-hide_banner", "-nostats", "-y", "-ss", $a, "-i", $video, "-ss", $b, "-i", $video, "-filter_complex", $fc, "-frames:v", "1", "-q:v", "3", $out)
}

function Mark-One([string]$ff, [string]$video, [string]$bakRoot) {
  $name = Split-Path -Leaf $video
  $i = Info $ff $video
  if (-not $i.video) { Say "  $name - can't read this file (no video found in it), skipped" Yellow; return "skip" }
  if ($i.chapters -gt 0 -and -not $Redo -and -not ($i.ours -and $script:RedoOurs)) { Say "  $name - already has chapters, skipped" DarkGray; return "skip" }
  $real = Real-Length $ff $video
  if ($real -gt 0) { $i.dur = $real }
  if ($i.dur -le 0) { Say "  $name - can't tell how long this video is, skipped" Yellow; return "skip" }
  $spots = Break-Spots $i.dur
  if (-not $spots.Count) { Say ("  {0} - only {1}, too short for breaks" -f $name, (Fmt $i.dur)) DarkGray; return "skip" }
  $found = @(); $missed = 0
  foreach ($s in $spots) { $f = Find-Break $ff $video $s $i.dur; if ($f) { $found += , $f } else { $missed++ } }
  if (-not $found.Count) { Say ("  {0} [{1}] - no clean break found (no fade or scene change), left alone" -f $name, (Fmt $i.dur)) DarkYellow; return "skip" }
  $found = @($found | Sort-Object { $_.t })
  $times = @($found | ForEach-Object { $_.t })
  $k = 0; foreach ($f in $found) { $k++; Preview $ff $video $f.t $k }
  $list = ($found | ForEach-Object { "{0} ({1})" -f (Fmt $_.t), $_.how }) -join ",  "
  $note = ""; if ($missed) { $note = " - $missed spot(s) had no clean break, so no break there" }
  if ($script:PreviewOnly) { Say ("  {0} [{1}]: would break at {2}{3}" -f $name, (Fmt $i.dur), $list, $note) Cyan; return "ok" }
  # chapters: start..break1, break1..break2, ..., lastbreak..end
  $meta = ";FFMETADATA1`n"; $prev = 0; $k = 0
  foreach ($t in ($times + @($i.dur))) {
    $k++; $meta += "[CHAPTER]`nTIMEBASE=1/1000`nSTART={0}`nEND={1}`ntitle=KNAS Part {2}`n" -f [int64]($prev * 1000), [int64]($t * 1000), $k; $prev = $t
  }
  $ext = [IO.Path]::GetExtension($video)
  if ($ext -notmatch $KEEP_EXT) { $ext = ".mkv" }
  $dir = Split-Path -Parent $video; $base = [IO.Path]::GetFileNameWithoutExtension($video)
  # everything is written next to the episode (same drive), never to the C: temp folder
  $metaFile = Join-Path $dir ($base + ".knas-chapters.txt")
  try { [IO.File]::WriteAllText($metaFile, $meta) } catch {
    Say "  $name - can't save files in this folder ($($_.Exception.Message))" Yellow; Log "$video`r`n  $($_.Exception.Message)"; return "fail" }
  $final = Join-Path $dir ($base + $ext)
  $tmp = Join-Path $dir ($base + ".knas-tmp" + $ext)
  $ok = $false; $why = ""
  # can we even write in this folder? (NAS shares and some drives are read-only)
  try { [IO.File]::WriteAllText($tmp, "test"); Remove-Item -Force $tmp } catch {
    Remove-Item -Force $metaFile -ErrorAction SilentlyContinue
    Say "  $name - can't save files in this folder (no permission, or the drive is full). Run it on a folder you can edit." Yellow
    Log "$video`r`n  can't write in the folder: $($_.Exception.Message)"; return "fail" }
  $tries = @(
    @("-map", "0", "-ignore_unknown"),
    @("-map", "0:v", "-map", "0:a?", "-map", "0:s?", "-ignore_unknown"),
    @("-map", "0:v:0", "-map", "0:a?")
  )
  foreach ($maps in $tries) {
    $a = @("-hide_banner", "-nostats", "-y", "-fflags", "+genpts", "-i", $video, "-f", "ffmetadata", "-i", $metaFile) + $maps +
         @("-map_metadata", "0", "-map_chapters", "1", "-c", "copy", "-max_interleave_delta", "0")
    if ($ext -match '^\.(mp4|m4v|mov)$') { $a += @("-movflags", "+faststart") }
    $a += $tmp
    $r = Run-FF $ff $a
    if ($r.code -eq 0 -and (Test-Path $tmp)) {
      $chk = Info $ff $tmp; $newLen = Real-Length $ff $tmp
      if ($newLen -gt 0 -and [math]::Abs($newLen - $i.dur) -lt 3 -and $chk.chapters -ge $times.Count) { $ok = $true; break }
      $why = "the new file didn't check out (video runs {0}, original {1}, {2} chapters)" -f (Fmt $newLen), (Fmt $i.dur), $chk.chapters
    } else {
      $lines = @($r.text -split "`r?`n" | Where-Object { $_ -match '(?i)error|invalid|could not|cannot|permission|denied|not supported|unknown|failed' } | Select-Object -Last 3)
      if ($lines.Count) { $why = ($lines -join " / ").Trim() } else { $why = "ffmpeg stopped with code $($r.code)" }
      Log "$video`r`n  try: $($maps -join ' ')`r`n$($r.text)"
    }
    if (Test-Path $tmp) { Remove-Item -Force $tmp }
  }
  Remove-Item -Force $metaFile -ErrorAction SilentlyContinue
  if (-not $ok) {
    Say "  $name - couldn't add chapters, left it alone." Yellow
    if ($why) { Say "     why: $why" DarkYellow }
    return "fail" }
  if ($bakRoot) {
    # a hidden folder that Jellyfin, Plex, Emby and ErsatzTV are told to skip, so episodes don't show up twice
    $bdir = Join-Path $dir ".knas-originals"
    if (-not (Test-Path $bdir)) {
      New-Item -ItemType Directory -Force -Path $bdir | Out-Null
      foreach ($ig in @(".ignore", ".etvignore", ".nomedia")) { Set-Content -Path (Join-Path $bdir $ig) -Value "" -ErrorAction SilentlyContinue }
      Set-Content -Path (Join-Path $bdir ".plexignore") -Value "*" -ErrorAction SilentlyContinue
      try { (Get-Item $bdir -Force).Attributes += "Hidden" } catch {}
    }
    $keep = Join-Path $bdir $name
    if (Test-Path $keep) { Remove-Item -Force $video } else { Move-Item -Force $video $keep }
  } else { Remove-Item -Force $video }
  if ((Test-Path $final) -and ($final -ne $video)) { Remove-Item -Force $final }
  Move-Item -Force $tmp $final
  Say ("  {0} [{1}]: breaks at {2}{3}" -f $name, (Fmt $i.dur), $list, $note) Green
  if ($ext -ne [IO.Path]::GetExtension($video)) { Say "     (saved as $([IO.Path]::GetFileName($final)): that file type can't hold chapters, so it was re-wrapped as .mkv with nothing re-encoded)" DarkGray }
  return "ok"
}

try {
  $Files = @($Files | Where-Object { $_ -and $_.Trim() })
  if (-not $Files.Count -and $IsWin) {
    Add-Type -AssemblyName System.Windows.Forms
    $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
    $dlg.Description = "Pick a show's folder (seasons inside it are included)"
    if ($dlg.ShowDialog() -eq "OK") { $Files = @($dlg.SelectedPath) }
  }
  if (-not $Files.Count) { Say "Nothing picked. Drag a show's folder onto ""Add Commercial Breaks.bat""." Yellow; exit 0 }
  $ff = Get-FFmpeg
  Say "Using ffmpeg: $ff" DarkGray
  $list = @()
  foreach ($f in $Files) {
    $f = $f.Trim('"')
    if (Test-Path $f -PathType Container) {
      $list += @(Get-ChildItem -Path $f -File -Recurse | Where-Object { $_.Extension -match $VIDEO -and $_.FullName -notmatch '_originals \(delete when happy\)|\\\.knas-originals\\|_break previews' -and $_.Name -notmatch '\.knas-tmp\.' } | Sort-Object FullName | ForEach-Object { $_.FullName })
    } elseif (Test-Path $f) { $list += (Resolve-Path $f).Path } else { Say "Can't find $f" Red }
  }
  if (-not $list.Count) { Say "No videos found there." Yellow; exit 0 }
  Say ("Found {0} videos." -f $list.Count) White
  $script:PreviewOnly = $false; $script:RedoOurs = $false
  if (-not $NoAsk) {
    Say "Tip: you can check first. It makes a picture of right before and after each break (in ""_break previews"" folders) without changing anything." Gray
    $ans = Read-Host "Just check first, without changing any files? (Y/N)"
    if ($ans -match '^[Yy]') { $script:PreviewOnly = $true }
    $ans = Read-Host "Redo episodes this tool already marked (to use the newest break finder)? (Y/N)"
    if ($ans -match '^[Yy]') { $script:RedoOurs = $true }
  }
  if (-not $Backup -and -not $NoAsk -and -not $script:PreviewOnly) {
    Say "The picture and sound aren't changed, only a chapter list is added. Each file is checked before it replaces the original." Gray
    $ans = Read-Host "Keep a backup copy of each original anyway? Needs as much free space as the files take up. (Y/N)"
    if ($ans -match '^[Yy]') { $Backup = $true }
  }
  $bak = $null; if ($Backup) { $bak = "yes" }
  $ok = 0; $skip = 0; $fail = 0
  foreach ($v in $list) {
    try { $res = Mark-One $ff $v $bak } catch { Say ("  " + (Split-Path -Leaf $v) + " - " + $_.Exception.Message) Yellow; $res = "fail" }
    if ($res -eq "ok") { $ok++ } elseif ($res -eq "skip") { $skip++ } else { $fail++ }
  }
  if ($script:PreviewOnly) {
    Say ""; Say ("Checked {0} episodes. Nothing was changed. Look at the pictures in the ""_break previews"" folders:" -f $ok) Green
    Say "each one shows right before (left) and right after (right) a break. If they look like the end and start of scenes, run this again and answer N to checking first." Gray
    exit 0
  }
  Say ""; Say ("All done: {0} episodes got commercial breaks, {1} skipped, {2} couldn't be changed." -f $ok, $skip, $fail) Green
  if ($fail) { Say "Details for the ones that couldn't be changed are in: $LOG" Yellow }
  Say "Next: in ErsatzTV, rescan this library so it sees the new chapters. Then use a Mid-Roll filler preset in your schedule." Gray
  if ($Backup) { Say "Your originals are in hidden "".knas-originals"" folders next to the episodes (your media apps skip them). Delete them once you've checked a few episodes." Gray }
} catch {
  Say ""; Say ("Something went wrong: " + $_.Exception.Message) Red
}
