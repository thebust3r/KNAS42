FROM python:3.12-alpine
# ffmpeg: used by the Tools page to find act breaks and add commercial-break markers to your episodes
# nodejs: the jukebox's video downloader needs it for YouTube (KNAS adds it by itself on older images)
RUN apk add --no-cache ffmpeg nodejs
# Video player library for the cable box (kept outside your folder so updates never touch it)
ADD https://cdn.jsdelivr.net/npm/hls.js@1.5.17/dist/hls.min.js /opt/knas/vendor/hls.min.js
RUN chmod 644 /opt/knas/vendor/hls.min.js
# A full copy of KNAS. On start, /opt/knas/start.py puts it into your KNAS folder (mapped to /knas) if the
# folder is empty, or updates the code there if this image is newer. Your settings are never touched.
# The folder is what actually runs, so updates can also be zips dropped into its updates folder.
COPY . /opt/knas/seed
RUN cp /opt/knas/seed/docker-start.py /opt/knas/start.py
WORKDIR /knas
VOLUME ["/knas"]
EXPOSE 8642 8645
LABEL org.opencontainers.image.title="KNAS 42" \
      org.opencontainers.image.description="A 90s cable box for any screen: TV guide, weather channel, live sports. Map a folder to /knas and open port 8642." \
      org.opencontainers.image.source="https://github.com/thebust3r/knas42"
CMD ["python", "-u", "/opt/knas/start.py"]
