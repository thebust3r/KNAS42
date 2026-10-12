FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
      chromium xvfb ffmpeg python3 fonts-dejavu-core fonts-liberation ca-certificates procps \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY cast.py audio.py ./
EXPOSE 8643 8644
# Runs the recorder from your knas-42 folder when it's mounted (so updates apply without a rebuild),
# otherwise the copy built into the image.
CMD ["sh", "-c", "if [ -f /knas/cast/cast.py ]; then exec python3 -u /knas/cast/cast.py; else exec python3 -u /app/cast.py; fi"]
