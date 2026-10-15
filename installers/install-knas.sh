#!/bin/sh
# Installs (or updates) KNAS 42 in Docker with the right settings, then shows the setup page address.
# Mac or Linux: open Terminal and run:  sh install-knas.sh
# Run it again any time to update KNAS. Your settings stay.
IMAGE="ghcr.io/thebust3r/knas42:latest"
KNASDIR="$HOME/KNAS42"

echo
echo "  KNAS 42 installer"
echo

if ! docker info >/dev/null 2>&1; then
  echo "  Docker isn't running. Start Docker (Docker Desktop on a Mac), then run this again."
  exit 1
fi

echo "  Downloading the newest KNAS 42..."
docker pull "$IMAGE" || { echo "  The download didn't work. Check your internet connection and try again."; exit 1; }

mkdir -p "$KNASDIR"
docker rm -f knas42 >/dev/null 2>&1
if [ "$(uname)" = "Linux" ]; then NET="--network host"; else NET="-p 8642:8642 -p 8645:8645"; fi
# shellcheck disable=SC2086
docker run -d --name knas42 --restart unless-stopped $NET -v "$KNASDIR:/knas" "$IMAGE" >/dev/null \
  || { echo "  KNAS didn't start. Another program may be using port 8642."; docker logs --tail 20 knas42; exit 1; }

echo "  Waiting for KNAS to come on the air..."
i=0
until curl -s -o /dev/null http://localhost:8642/setup; do
  i=$((i+1)); [ $i -ge 60 ] && { echo "  Taking longer than usual. Try http://localhost:8642/setup in a minute."; exit 0; }
  sleep 2
done

echo
echo "  KNAS 42 is on the air! Your files are in $KNASDIR"
echo "  Setup page:  http://localhost:8642/setup"
echo "  On a TV or phone, use this computer's address instead of localhost, with :8642/tv at the end."
echo
(command -v open >/dev/null && open http://localhost:8642/setup) || (command -v xdg-open >/dev/null && xdg-open http://localhost:8642/setup) >/dev/null 2>&1 || true
