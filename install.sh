#!/bin/bash
# Installs the Omarchy Theme Sync extension + native messaging bridge into a
# Thunderbird profile. Re-running is safe (idempotent).
set -euo pipefail

EXTENSION_ID="omarchy-thunderbird-theme@fifue.cloud"
NATIVE_HOST_NAME="cloud.fifue.omarchy_thunderbird_bridge"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"

usage() {
  echo "Usage: $0 <path-to-thunderbird-profile-dir>"
  echo
  echo "Example:"
  echo "  $0 ~/.thunderbird/rdlj8tgf.default-release"
  echo
  echo "Find your profile dir with: thunderbird --ProfileManager"
  exit 1
}

[[ $# -eq 1 ]] || usage
PROFILE_DIR="$(cd -- "$1" &>/dev/null && pwd)" || { echo "No such directory: $1"; exit 1; }
[[ -f "$PROFILE_DIR/prefs.js" || -f "$PROFILE_DIR/user.js" ]] || {
  echo "Warning: $PROFILE_DIR doesn't look like a Thunderbird profile (no prefs.js/user.js)."
}

if ! command -v inotifywait &>/dev/null; then
  echo "inotifywait not found. Install inotify-tools first, e.g.:"
  echo "  sudo pacman -S inotify-tools"
  exit 1
fi

chmod +x "$SCRIPT_DIR/native-host/omarchy_thunderbird_bridge.py"

# 1. Register the native messaging host (per-user, shared .mozilla dir --
#    Thunderbird reads native messaging manifests from the same location as Firefox).
NMH_DIR="$HOME/.mozilla/native-messaging-hosts"
mkdir -p "$NMH_DIR"
cat > "$NMH_DIR/$NATIVE_HOST_NAME.json" <<EOF
{
  "name": "$NATIVE_HOST_NAME",
  "description": "Bridges the active Omarchy theme into Thunderbird",
  "path": "$SCRIPT_DIR/native-host/omarchy_thunderbird_bridge.py",
  "type": "stdio",
  "allowed_extensions": ["$EXTENSION_ID"]
}
EOF
echo "Registered native messaging host at $NMH_DIR/$NATIVE_HOST_NAME.json"

# 2. Sideload the extension (unpacked) into the profile's extensions dir.
EXT_DEST="$PROFILE_DIR/extensions/$EXTENSION_ID"
rm -rf "$EXT_DEST"
mkdir -p "$EXT_DEST"
cp "$SCRIPT_DIR/extension/manifest.json" "$SCRIPT_DIR/extension/background.js" "$EXT_DEST/"
echo "Installed extension into $EXT_DEST"

# 3. Allow unsigned extensions to load (Thunderbird enforces AMO signing by default).
USER_JS="$PROFILE_DIR/user.js"
touch "$USER_JS"
if grep -q 'xpinstall.signatures.required' "$USER_JS" 2>/dev/null; then
  sed -i 's/.*xpinstall\.signatures\.required.*/user_pref("xpinstall.signatures.required", false);/' "$USER_JS"
else
  echo 'user_pref("xpinstall.signatures.required", false);' >> "$USER_JS"
fi
echo "Disabled signature enforcement in $USER_JS"

cat <<EOF

Done. One-time manual step left:

  1. Fully quit Thunderbird (not just close the window).
  2. Start it again.
  3. Open Settings -> Add-ons Manager -> Extensions.
     If "Omarchy Theme Sync" shows up disabled, click Enable.

After that it stays active across restarts and re-syncs automatically
every time you run "omarchy theme set" or "omarchy theme bg next" --
no further steps needed.
EOF
