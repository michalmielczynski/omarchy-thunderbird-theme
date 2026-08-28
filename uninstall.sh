#!/bin/bash
set -euo pipefail

EXTENSION_ID="omarchy-thunderbird-theme@fifue.cloud"
NATIVE_HOST_NAME="cloud.fifue.omarchy_thunderbird_bridge"

usage() {
  echo "Usage: $0 <path-to-thunderbird-profile-dir>"
  exit 1
}

[[ $# -eq 1 ]] || usage
PROFILE_DIR="$(cd -- "$1" &>/dev/null && pwd)" || { echo "No such directory: $1"; exit 1; }

rm -rf "$PROFILE_DIR/extensions/$EXTENSION_ID"
rm -f "$HOME/.mozilla/native-messaging-hosts/$NATIVE_HOST_NAME.json"
sed -i '/xpinstall\.signatures\.required/d' "$PROFILE_DIR/user.js" 2>/dev/null || true

echo "Removed. Restart Thunderbird to complete the uninstall."
