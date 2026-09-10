#!/usr/bin/env bash
# Build the APK with its identity stamped in, and name the file after the commit.
#
# Every APK sent out was called v10. Several were built from different commits.
# When a tester reported a screen missing there was no way to tell whether the
# app was wrong or the APK was old — it was the APK, and the screen had been
# there for weeks. This script exists so that question is never asked again.
set -euo pipefail
cd "$(dirname "$0")"

COMMIT=$(git rev-parse --short HEAD)
DATE=$(date -u +%Y-%m-%dT%H:%MZ)
DIRTY=""
git diff --quiet || DIRTY="-dirty"

if [ -n "$DIRTY" ]; then
  echo "WARNING: uncommitted changes. The stamp will say ${COMMIT}${DIRTY},"
  echo "         which nobody else can check out. Commit first if this is"
  echo "         going to anyone but you."
fi

echo "building ${COMMIT}${DIRTY} at ${DATE}"
( cd app && flutter build apk --release \
    --dart-define=BUILD_COMMIT="${COMMIT}${DIRTY}" \
    --dart-define=BUILD_DATE="${DATE}" )

mkdir -p dist
OUT="dist/sih26231-${COMMIT}${DIRTY}.apk"
cp app/build/app/outputs/flutter-apk/app-release.apk "$OUT"

# A stable name for "the latest", alongside the one that identifies itself.
cp "$OUT" dist/sih26231-latest.apk

echo
echo "  $OUT"
echo "  dist/sih26231-latest.apk  (same file)"
echo
echo "The build shows ${COMMIT}${DIRTY} on its standby screen under 'Build'."
echo "Ask anyone reporting a problem to read that line out first."
