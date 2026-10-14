#!/usr/bin/env python3
"""Writes a never-ending, real-time 48 kHz stereo PCM stream to stdout.
Shuffles through the music folder; plays silence if there is no music
or between tracks, so the audio never stalls or drifts from the video."""
import os, random, subprocess, sys, threading, time, queue

MUSIC = os.environ.get("MUSIC_DIR", "/music")
EXT = (".mp3", ".ogg", ".m4a", ".aac", ".wav", ".opus", ".flac")
VOLUME = os.environ.get("MUSIC_VOLUME", "0.8")
RATE, BPS = 48000, 4            # 16-bit stereo
CHUNK = RATE * BPS // 50        # 20 ms
buf = queue.Queue(maxsize=200)  # ~4 s of decoded audio


def songs():
    try:
        return [os.path.join(MUSIC, f) for f in os.listdir(MUSIC) if f.lower().endswith(EXT)]
    except OSError:
        return []


def decoder():
    while True:
        lst = songs()
        if not lst:
            time.sleep(30)
            continue
        random.shuffle(lst)
        for path in lst:
            p = subprocess.Popen(
                ["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-vn", "-af", f"volume={VOLUME}",
                 "-f", "s16le", "-ar", str(RATE), "-ac", "2", "-"],
                stdout=subprocess.PIPE)
            while True:
                data = p.stdout.read(CHUNK)
                if not data:
                    break
                buf.put(data.ljust(CHUNK, b"\0"))
            p.wait()
            for _ in range(50):          # 1 s pause between songs
                buf.put(b"\0" * CHUNK)


threading.Thread(target=decoder, daemon=True).start()
out, silence = sys.stdout.buffer, b"\0" * CHUNK
start, sent = time.monotonic(), 0
while True:
    due = int((time.monotonic() - start) * 50)   # chunks that should exist by now
    while sent < due:
        try:
            out.write(buf.get_nowait())
        except queue.Empty:
            out.write(silence)
        sent += 1
    out.flush()
    time.sleep(0.01)
