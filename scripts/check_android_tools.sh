#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."

missing=0

check_tool() {
  if command -v "$1" >/dev/null 2>&1; then
    echo "$1: $(command -v "$1")"
  else
    echo "$1: missing"
    missing=1
  fi
}

check_tool adb
check_tool gradle

if [ "$missing" -ne 0 ]; then
  echo
  echo "Install Android platform-tools and Gradle, or open android-client/ in Android Studio."
  echo "Then rerun this script and use adb devices to confirm the phone is visible."
  exit 1
fi

adb devices
