#!/usr/bin/env bash
# Build and install over the top, keeping the ledger. No uninstall.
#
# Every build so far shipped with "uninstall first", which also wiped the
# records — so nobody could carry a chain across two builds, and testing meant
# starting from zero every time. Two things made the wipe necessary and both are
# fixed in the app: a signing key an older build left behind is now regenerated
# on use, and a record this build cannot parse is reported instead of throwing.
#
#   ./install.sh            build, then install over whatever is on the device
#   ./install.sh --run      the same, then stream logs (ctrl-C to stop)
#   ./install.sh --wipe     the old way, when you actually want a clean slate
set -euo pipefail
cd "$(dirname "$0")"

PKG=in.gov.ncb.sih26231.field_companion

command -v adb >/dev/null || {
  echo "adb not found. It ships with Android Studio, or: brew install android-platform-tools"
  exit 1
}

DEVICES=$(adb devices | awk 'NR>1 && $2=="device" {print $1}')
if [ -z "$DEVICES" ]; then
  echo "No device. Plug the phone in and allow USB debugging, or pair over"
  echo "wireless debugging:  adb pair <host:port>  then  adb connect <host:port>"
  exit 1
fi

./build-apk.sh
APK=dist/sih26231-latest.apk

for D in $DEVICES; do
  echo
  echo "--- $D ---"
  if [ "${1:-}" = "--wipe" ]; then
    echo "  removing the app AND its records"
    adb -s "$D" uninstall "$PKG" >/dev/null 2>&1 || true
  fi
  # -r reinstalls keeping data. -d allows the same or an older versionCode,
  # which matters because these builds are named by commit, not by version.
  if adb -s "$D" install -r -d "$APK"; then
    echo "  installed, records kept"
  else
    echo
    echo "  Install refused. That is almost always a signing mismatch — an APK"
    echo "  built on another machine has a different debug key. Once:"
    echo "      adb -s $D uninstall $PKG"
    echo "  then run this again. (That does delete the records on the device.)"
    exit 1
  fi
done

if [ "${1:-}" = "--run" ]; then
  adb logcat -c
  adb shell monkey -p "$PKG" -c android.intent.category.LAUNCHER 1 >/dev/null
  echo
  echo "streaming app logs — ctrl-C to stop"
  adb logcat --pid="$(adb shell pidof -s $PKG)" 2>/dev/null || adb logcat "*:E"
fi
