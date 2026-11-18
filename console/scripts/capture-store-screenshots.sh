#!/usr/bin/env bash
#
# Capture one display's App Store screenshots from a booted simulator.
#
#   capture-store-screenshots.sh <udid> <app> <outdir> <sizes> <api-base>
#
#     sizes   comma-separated pixel sizes Apple accepts for this slot,
#             e.g. 1320x2868 or 2064x2752,2048x2732
#
# The app is opened on a start route rather than through a deep link: simctl
# openurl raises iOS's "Open in AthenIQ?" confirmation and a macOS runner has
# nothing that can tap it, so the frames were the alert instead of the screen.
# lib/start-route.ts reads the route file at boot and navigates itself, which
# needs no tap and no prompt.
#
# The set is checked here rather than in Apple's upload errors: four distinct
# frames, all at a pixel size the display slot accepts.
set -euo pipefail

UDID="$1"
APP="$2"
OUT="$3"
SIZES="$4"
API_BASE="$5"
BUNDLE="institute.atheniq.app"

test -n "$UDID" -a -n "$APP" -a -n "$OUT" -a -n "$SIZES"

xcrun simctl install "$UDID" "$APP"
xcrun simctl launch "$UDID" "$BUNDLE" >/dev/null
mkdir -p "$OUT"

# A store screenshot showing 3% battery and no signal reads as broken.
xcrun simctl status_bar "$UDID" override \
  --time "9:41" --dataNetwork wifi --wifiMode active --wifiBars 3 \
  --cellularMode active --cellularBars 4 --batteryState charged --batteryLevel 100

data=$(xcrun simctl get_app_container "$UDID" "$BUNDLE" data)
mkdir -p "$data/Documents"

# A frame taken while the app is still launching is a black rectangle that
# still passes every size and distinctness check, and that is what shipped in
# one run. Two things stop it: the app writes `start-route.txt.done` once it has
# navigated, and the frame is only kept when two shots a moment apart are
# identical — a screen that is still painting never is.
capture_settled() {
  local name="$1"
  local attempt
  for attempt in 1 2 3 4; do
    xcrun simctl io "$UDID" screenshot --type=png "$OUT/$name"
    sleep 2
    xcrun simctl io "$UDID" screenshot --type=png "$OUT/.check.png"
    if [ "$(md5 -q "$OUT/$name")" = "$(md5 -q "$OUT/.check.png")" ]; then
      rm -f "$OUT/.check.png"
      return 0
    fi
    echo "$name was still painting (attempt $attempt); waiting"
  done
  rm -f "$OUT/.check.png"
  echo "::error::$name never settled; the frame would be a half-drawn screen."
  return 1
}

shot() {
  name="$1"; route="$2"; settle="${3:-4}"
  rm -f "$data/Documents/start-route.txt.done"
  printf '%s\n' "$route" > "$data/Documents/start-route.txt"
  # A cold simulator can take half a minute to load the bundle, and a launch
  # that lands while the previous instance is still shutting down never gets as
  # far as the route: one run lost /sign-up that way and the whole set with it.
  # Wait longer, and give the launch itself a second chance before failing.
  applied=0
  for launch in 1 2; do
    xcrun simctl terminate "$UDID" "$BUNDLE" >/dev/null 2>&1 || true
    sleep 2
    xcrun simctl launch "$UDID" "$BUNDLE" >/dev/null
    # Wait for the app to say it navigated, not for a fixed number of seconds.
    for _ in $(seq 1 90); do
      [ -f "$data/Documents/start-route.txt.done" ] && break
      sleep 1
    done
    if [ -f "$data/Documents/start-route.txt.done" ]; then applied=1; break; fi
    echo "$name: $route was not applied within 90s (launch $launch); relaunching"
  done
  if [ "$applied" -ne 1 ]; then
    echo "::error::$name: the app never applied $route. Check lib/start-route.ts."
    return 1
  fi
  sleep "$settle"
  capture_settled "$name"
  echo "captured $name ($route, $(wc -c < "$OUT/$name" | tr -d ' ') bytes)"
}

# The app opens on the catalog, so wait for the network before the first frame
# rather than photographing a spinner.
rm -f "$data/Documents/start-route.txt" "$data/Documents/start-route.txt.done"
sleep 8
capture_settled "01-courses.png"

# A real course page: the catalog is public, so take the first id.
course=$(curl -fsS "$API_BASE/api/mobile/v1/catalog" | node -e '
  let body = "";
  process.stdin.on("data", (chunk) => (body += chunk)).on("end", () => {
    const json = JSON.parse(body);
    const catalog = json.data?.courses || json.courses || [];
    process.stdout.write(String(catalog[0]?.id || ""));
  });
' || true)
if [ -n "$course" ]; then
  shot 02-course.png "/course/$course" 8
else
  echo "::warning::The catalog returned no course; the course page is missing from the set."
fi
shot 03-my-learning.png "/learning" 6
# Not Account: a fresh simulator has no session, so that screen would read
# "Not signed in" in the listing. Where someone starts is worth showing.
shot 04-sign-up.png "/sign-up" 6

# Identical files mean the start route did not take and the set is the same
# screen four times; that is worth failing on, not shipping.
unique=$(md5 -q "$OUT"/*.png | sort -u | wc -l | tr -d ' ')
total=$(ls "$OUT"/*.png | wc -l | tr -d ' ')
if [ "$unique" -ne "$total" ]; then
  echo "::error::Only $unique of $total screenshots differ — the start route did not navigate. Check lib/start-route.ts and the routes (course, learning, sign-up)."
  exit 1
fi

first=$(sips -g pixelWidth "$OUT/01-courses.png" | awk '/pixelWidth/ {print $2}')
second=$(sips -g pixelHeight "$OUT/01-courses.png" | awk '/pixelHeight/ {print $2}')
actual="${first}x${second}"
for file in "$OUT"/*.png; do
  echo "$(basename "$file") $actual"
done

case ",$SIZES," in
  *",$actual,"*) echo "$OUT: $total frames, $actual, all distinct" ;;
  *)
    echo "::error::Captured $actual on $UDID; this display slot accepts $SIZES."
    exit 1
    ;;
esac
