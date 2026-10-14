FROM python:3.12-alpine
WORKDIR /knas
# ffmpeg: used by the Tools page to find act breaks and add commercial-break markers to your episodes
# nodejs: the jukebox's video downloader needs it for YouTube (KNAS adds it by itself on older images)
RUN apk add --no-cache ffmpeg nodejs
# Video player library for the cable box (kept outside your folder so updates never touch it)
ADD https://cdn.jsdelivr.net/npm/hls.js@1.5.17/dist/hls.min.js /opt/knas/vendor/hls.min.js
RUN chmod 644 /opt/knas/vendor/hls.min.js
# A starter copy of the code. Your knas-42 folder is mounted over /knas and is what actually runs,
# so updates are just files dropped into that folder - no rebuild needed.
COPY server.py settings.txt facts.txt teams.txt trivia.txt ./
COPY app ./app
COPY web ./web
EXPOSE 8642 8645
CMD ["python", "-u", "/knas/server.py"]
