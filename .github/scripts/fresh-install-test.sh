#!/bin/sh
# Fresh-install test: does a brand-new KNAS start up and work, the way a first-time user sees it?
# Used by the GitHub check (.github/workflows/fresh-install.yml). You can also run it yourself
# against a fresh copy:   sh .github/scripts/fresh-install-test.sh http://localhost:8642
BASE="${1:-http://localhost:8642}"
FAIL=0
pass() { echo "  PASS  $*"; }
fail() { echo "  FAIL  $*"; FAIL=1; }
warn() { echo "  WARN  $*"; }
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }

echo "1. KNAS starts"
i=0; until curl -fsS "$BASE/api/version" >/dev/null 2>&1; do
  i=$((i + 1)); [ $i -gt 90 ] && { fail "KNAS didn't answer at $BASE within 3 minutes"; exit 1; }; sleep 2
done
pass "KNAS is running: $(curl -fsS "$BASE/api/version")"

echo "2. With nothing set up, the screens already open (KNAS guesses the town)"
if curl -fsS "$BASE/api/setup" | grep -q '"auto_location": {'; then
  pass "KNAS guessed a town from the internet connection"
  for p in / /tv /sports /break; do
    [ "$(code "$BASE$p")" = 200 ] && pass "$p opens with no setup" || fail "$p didn't open on a fresh install"
  done
else
  warn "KNAS couldn't guess a town (no internet on this runner?), so the screens send you to the setup page"
  for p in / /tv; do
    where="$(curl -s -o /dev/null -w '%{http_code} %{redirect_url}' "$BASE$p")"
    case "$where" in "302 "*"/setup") pass "$p -> setup page";; *) fail "$p gave '$where'";; esac
  done
fi
[ "$(code "$BASE/setup")" = 200 ] && pass "setup page loads" || fail "setup page didn't load"

echo "3. Fonts and pages load (no internet needed for these)"
[ "$(code "$BASE/fonts/classic-700.woff")" = 200 ] && pass "fonts are served" || fail "fonts missing"
[ "$(code "$BASE/knas-common.js")" = 200 ] && pass "page scripts are served" || fail "knas-common.js missing"

echo "4. Saving the setup page"
R="$(curl -fsS -X POST -H 'Content-Type: application/json' \
  -d '{"settings":{"CITY_NAME":"Springfield, MO","LATITUDE":"37.2090","LONGITUDE":"-93.2923","TZ":"America/Chicago","BREAK_CLIPS":"30s x1","BREAK_CLIPS_HOURS":"6"},"teams":[]}' \
  "$BASE/api/setup")"
case "$R" in *'"ok": true'*) pass "settings saved";; *) fail "saving settings failed: $R";; esac
sleep 6
i=0; until curl -fsS "$BASE/api/version" >/dev/null 2>&1; do i=$((i + 1)); [ $i -gt 30 ] && break; sleep 2; done
[ "$(code "$BASE/")" = 200 ] && pass "after setup, the weather channel opens (no more redirect)" || fail "weather channel still redirects after setup"
[ "$(code "$BASE/tv")" = 200 ] && pass "cable box opens" || fail "cable box didn't open"

echo "5. Weather data (needs internet)"
if curl -fsS "$BASE/api/all" | grep -q '"temperature_2m"'; then pass "weather loaded"; else warn "no weather yet (internet or the weather service may be down)"; fi

echo "6. Break clips get recorded (this is the slow one: up to 6 minutes)"
i=0; while :; do
  J="$(curl -fsS "$BASE/api/clips" 2>/dev/null)"
  if printf '%s' "$J" | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if any(f.get("name")=="KNAS Break 30sec A.ts" and f.get("size",0)>100000 for f in d.get("files",[])) else 1)' 2>/dev/null; then
    pass "a break clip was recorded"; break
  fi
  i=$((i + 1))
  if [ $i -gt 72 ]; then fail "no break clip after 6 minutes. Clip status: $(printf '%s' "$J" | head -c 400)"; break; fi
  sleep 5
done

echo
if [ $FAIL = 0 ]; then echo "ALL GOOD: a fresh install works."; else echo "SOMETHING FAILED (see FAIL lines above)."; fi
exit $FAIL
