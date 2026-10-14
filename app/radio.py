"""Radio relay: the NAS keeps one connection to each station and shares the live audio.

Internet stations often play an ad every time a new connection starts. By holding one
connection open (and tuning in early, while the cable box is in use), flipping back to the
sports channel joins the live broadcast instead of hearing that ad again.
"""
import os, time, queue, hashlib, threading, collections, urllib.request, shutil, subprocess

KEEP_SECONDS = int(os.environ.get("RADIO_KEEP_MINUTES", "30") or 30) * 60
BUFFER_BYTES = 64 * 1024          # a few seconds of audio so playback starts instantly
RELAYS, _lock = {}, threading.Lock()


class Relay:
    def __init__(self, url):
        self.url, self.listeners, self.buf, self.size = url, set(), collections.deque(), 0
        self.ctype, self.thread, self.last_use, self.lock = "audio/mpeg", None, time.time(), threading.Lock()
        self.connects = 0
        self.hls = ".m3u8" in url.lower()       # a playlist of short chunks, not one long stream

    def _feed(self, chunk):
        with self.lock:
            self.buf.append(chunk)
            self.size += len(chunk)
            while self.size > BUFFER_BYTES and len(self.buf) > 1:
                self.size -= len(self.buf.popleft())
            for q in list(self.listeners):
                try:
                    q.put_nowait(chunk)
                except queue.Full:
                    pass

    def _run_hls(self):
        """HLS stations (.m3u8): ffmpeg follows the playlist and turns it into one plain MP3 stream,
        which every browser and TV box can play."""
        ff = shutil.which("ffmpeg")
        if not ff:
            print("[radio] this station needs ffmpeg, which isn't installed", flush=True)
            return
        self.ctype = "audio/mpeg"
        while not self._idle():
            p = None
            try:
                p = subprocess.Popen([ff, "-nostdin", "-hide_banner", "-loglevel", "error", "-user_agent", "Mozilla/5.0 (KNAS42 radio)",
                                      "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "10",
                                      "-i", self.url, "-vn", "-map", "0:a:0", "-c:a", "libmp3lame", "-b:a", "128k", "-ar", "44100",
                                      "-f", "mp3", "pipe:1"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.connects += 1
                while True:
                    chunk = p.stdout.read(4096)
                    if not chunk:
                        break
                    self._feed(chunk)
                    if self._idle():
                        return
                err = p.stderr.read().decode(errors="replace").strip().splitlines()
                print("[radio] station stream ended, reconnecting:", (err[-1] if err else "no more audio"), flush=True)
            except Exception as e:
                print("[radio] reconnecting:", e, flush=True)
            finally:
                if p and p.poll() is None:
                    p.kill()
            time.sleep(3)
        with self.lock:
            self.buf.clear()
            self.size = 0

    def touch(self):
        self.last_use = time.time()
        if not (self.thread and self.thread.is_alive()):
            self.thread = threading.Thread(target=self._run, daemon=True, name="radio-relay")
            self.thread.start()

    def _idle(self):
        return not self.listeners and time.time() - self.last_use > KEEP_SECONDS

    def _run(self):
        if self.hls:
            return self._run_hls()
        while not self._idle():
            try:
                req = urllib.request.Request(self.url, headers={"User-Agent": "Mozilla/5.0 (KNAS42 radio)"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    self.connects += 1
                    self.ctype = r.headers.get("Content-Type", "audio/mpeg").split(";")[0] or "audio/mpeg"
                    while True:
                        chunk = r.read(4096)
                        if not chunk:
                            break
                        with self.lock:
                            self.buf.append(chunk)
                            self.size += len(chunk)
                            while self.size > BUFFER_BYTES and len(self.buf) > 1:
                                self.size -= len(self.buf.popleft())
                            for q in list(self.listeners):
                                try:
                                    q.put_nowait(chunk)
                                except queue.Full:
                                    pass
                        if self._idle():
                            return
            except Exception as e:
                print("[radio] reconnecting:", e, flush=True)
                time.sleep(3)
        with self.lock:
            self.buf.clear()
            self.size = 0

    def subscribe(self):
        q = queue.Queue(maxsize=512)
        with self.lock:
            self.listeners.add(q)
            pre = list(self.buf)
        self.touch()
        return q, pre

    def unsubscribe(self, q):
        with self.lock:
            self.listeners.discard(q)
        self.last_use = time.time()


def _rid(url):
    return hashlib.sha1(url.encode()).hexdigest()[:10]


def relay_url(url):
    """Address the browser should use for a station: our relay for regular streams."""
    if not url or not url.lower().startswith(("http://", "https://")):
        return url
    i = _rid(url)
    with _lock:
        RELAYS.setdefault(i, Relay(url))
    return f"/radio/{i}.mp3"


def warm(urls):
    """Tune in early so any connection ad plays before anyone is listening."""
    for u in urls:
        p = relay_url(u)
        if p and p.startswith("/radio/"):
            RELAYS[p[7:-4]].touch()


def serve(handler, rid):
    relay = RELAYS.get(rid)
    if not relay:
        return handler.send_error(404)
    q, pre = relay.subscribe()
    try:
        if not pre:  # just tuned in: give the stream a moment to arrive
            try:
                pre = [q.get(timeout=15)]
            except queue.Empty:
                return handler.send_error(504, "station not answering")
        handler.send_response(200)
        handler.send_header("Content-Type", relay.ctype)
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Connection", "close")
        handler.end_headers()
        for c in pre:
            handler.wfile.write(c)
        while True:
            try:
                handler.wfile.write(q.get(timeout=30))
            except queue.Empty:
                break
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass
    finally:
        relay.unsubscribe(q)
