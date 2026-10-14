#!/bin/sh
# KNAS Break clips -> this Mac or Linux computer
# Copies the break clips KNAS records into a "break-clips" folder next to this file, so ErsatzTV
# on this computer can play them. Only new or changed clips are downloaded, and clips KNAS no
# longer makes are removed. Run it once by hand, then every 5 minutes with cron:
#
#   crontab -e      and add this line (with the real path to this file):
#   */5 * * * * /bin/sh "/path/to/knas-clip-sync.sh" >/dev/null 2>&1
#
# >>> Change YOUR_NAS_IP to the IP address of the computer running KNAS <<<
NAS="${KNAS_URL:-http://YOUR_NAS_IP:8642}"

case "$NAS" in *YOUR_NAS_IP*)
  echo "Open knas-clip-sync.sh in a text editor and put your server's IP address where it says YOUR_NAS_IP."
  exit 1;;
esac

DIR="$(cd "$(dirname "$0")" && pwd)"
DEST="$DIR/break-clips"
STATE="$DEST/.knas-clips"          # remembers which version of each clip we have
mkdir -p "$DEST"
touch "$STATE"

LIST="$(curl -fsS --max-time 20 "$NAS/api/clips.txt")" || { echo "Can't reach KNAS at $NAS. Is the NAS on?"; exit 1; }

NEWSTATE="$STATE.new"
: > "$NEWSTATE"
COUNT=0
CHANGED=0
OLDIFS="$IFS"
IFS='
'
for line in $LIST; do
  case "$line" in "#"*) continue;; esac          # the keep list, handled below
  IFS='	' read -r name size mtime <<EOF
$line
EOF
  [ -n "$name" ] || continue
  COUNT=$((COUNT + 1))
  have="$(grep -F "$name	" "$STATE" | head -n 1 | cut -f2)"
  if [ -f "$DEST/$name" ] && [ "$have" = "$size:$mtime" ]; then
    printf '%s\t%s\n' "$name" "$size:$mtime" >> "$NEWSTATE"
    continue
  fi
  url="$NAS/break-clips/$(printf '%s' "$name" | sed 's/ /%20/g')"
  if curl -fsS --max-time 900 -o "$DEST/.$name.part" "$url"; then
    mv -f "$DEST/.$name.part" "$DEST/$name"
    printf '%s\t%s\n' "$name" "$size:$mtime" >> "$NEWSTATE"
    echo "Got $name"
    CHANGED=1
  else
    rm -f "$DEST/.$name.part"
    echo "Couldn't download $name - will try again next time"
  fi
done
IFS="$OLDIFS"
mv -f "$NEWSTATE" "$STATE"

# Remove clips KNAS doesn't make anymore. Only clips that aren't on KNAS's clip list are
# removed, so clips it's still recording for the first time are kept. With break clips turned
# off in KNAS, nothing is removed.
if [ "$COUNT" -gt 0 ] && ! printf '%s\n' "$LIST" | grep -qx '#nodelete'; then
  KEEP="$(printf '%s\n' "$LIST" | sed -n 's/^#keep	//p'; printf '%s\n' "$LIST" | grep -v '^#' | cut -f1)"
  for f in "$DEST"/KNAS\ Break\ *.ts; do
    [ -e "$f" ] || continue
    b="$(basename "$f")"
    printf '%s\n' "$KEEP" | grep -qxF "$b" || { rm -f "$f"; CHANGED=1; }
  done
fi
# Newer ErsatzTV versions (26.8+) need their API key before KNAS can ask them to rescan the clips.
# If ErsatzTV runs on this computer, pass the key from its api-secrets.json to KNAS.
for d in "${ETV_CONFIG_FOLDER:-}" "$HOME/.local/share/ersatztv" "$HOME/Library/Application Support/ersatztv"; do
  [ -n "$d" ] && [ -f "$d/api-secrets.json" ] || continue
  KEY="$(grep -io '"[^"]*key[^"]*"[[:space:]]*:[[:space:]]*"[A-Za-z0-9+/=_.-]\{16,\}"' "$d/api-secrets.json" | head -n 1 | sed 's/.*:[[:space:]]*"//; s/"$//')"
  [ -n "$KEY" ] || KEY="$(grep -o '"[A-Za-z0-9+/=_.-]\{16,\}"' "$d/api-secrets.json" | head -n 1 | tr -d '"')"
  if [ -n "$KEY" ]; then
    R="$(curl -fsS --max-time 10 -X POST -H 'Content-Type: application/json' -d "{\"key\":\"$KEY\"}" "$NAS/api/clips/etv-key" 2>/dev/null)"
    case "$R" in *'"changed": true'*)
      echo "Gave KNAS the ErsatzTV API key"; sleep 4          # KNAS restarts to use it: wait until it's back
      w=0; until curl -fsS --max-time 3 "$NAS/api/version" >/dev/null 2>&1 || [ $w -ge 15 ]; do w=$((w + 1)); sleep 2; done;;
    esac
  fi
  break
done
# Tell KNAS the clips changed, so it can ask ErsatzTV to rescan them right away
[ "$CHANGED" = 1 ] && curl -fsS --max-time 10 -X POST "$NAS/api/clips/copied" >/dev/null 2>&1
echo "$COUNT clips on the NAS. Folder: $DEST"
