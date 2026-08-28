# omarchy-thunderbird-theme

Syncs Thunderbird's window chrome (toolbars, tabs, folder pane, popups) to
your current [Omarchy](https://omarchy.org/) theme, live, with no restart --
including when you switch themes while Thunderbird is already open.

## How it works

Omarchy always exposes the active theme's colors at a stable path:
`~/.local/state/omarchy/current/theme/colors.toml`. This project ships:

- **`extension/`** -- a small WebExtension (`Omarchy Theme Sync`) that holds
  a persistent connection to a native messaging host and calls
  [`browser.theme.update()`](https://webextension-api.thunderbird.net/en/latest/theme.html)
  whenever it receives new colors.
- **`native-host/omarchy_thunderbird_bridge.py`** -- a native messaging host
  Thunderbird spawns on startup. It reads `colors.toml`, maps Omarchy's
  color roles onto Thunderbird's theme color keys, sends them to the
  extension, then watches `~/.local/state/omarchy/current/` with
  `inotifywait` and re-sends on every change -- i.e. on every
  `omarchy theme set`, regardless of what triggered it (CLI, a bar widget,
  a hook, whatever swaps the theme symlink).

No polling, no Thunderbird restart, no dependency on Omarchy's hook system
-- it reacts directly to the same state Omarchy itself uses.

## Requirements

- Thunderbird >= 115 (Linux)
- `inotify-tools` (`inotifywait`) -- ships on most Arch/Omarchy systems
- Python >= 3.11 (stdlib `tomllib`)

## Install

```bash
git clone https://github.com/<you>/omarchy-thunderbird-theme.git
cd omarchy-thunderbird-theme
./install.sh ~/.thunderbird/<your-profile>.default-release
```

Find your profile directory with `thunderbird --ProfileManager`, or look for
the one whose `compatibility.ini` has `LastPlatformDir=/usr/lib/thunderbird`.

The installer:

1. Registers the native messaging host in `~/.mozilla/native-messaging-hosts/`.
2. Sideloads the extension (unpacked) into the profile's `extensions/` dir.
3. Sets `xpinstall.signatures.required = false` in the profile's `user.js`,
   since Thunderbird refuses to load unsigned extensions otherwise.

**One manual step is unavoidable:** Gecko-based apps disable freshly
sideloaded extensions by default as an anti-abuse measure. After the first
restart, open *Settings -> Add-ons Manager -> Extensions* and click *Enable*
next to "Omarchy Theme Sync" if it isn't already active. After that it stays
enabled across restarts and updates permanently.

## Uninstall

```bash
./uninstall.sh ~/.thunderbird/<your-profile>.default-release
```

## Customizing the color mapping

Edit `build_theme_colors()` in `native-host/omarchy_thunderbird_bridge.py` --
it reads the same keys any `colors.toml` provides (`background`, `foreground`,
`accent`, `selection`, the `dark_`/`darker_`/`lighter_` variants, etc.) and
maps them onto [Thunderbird's theme color keys](https://webextension-api.thunderbird.net/en/latest/theme.html).
No rebuild step -- just re-run `omarchy theme set` (or restart Thunderbird)
to see the change.

## License

MIT
