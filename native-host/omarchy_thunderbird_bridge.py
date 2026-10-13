#!/usr/bin/env python3
"""Native messaging host for the "Omarchy Theme Sync" Thunderbird extension.

Two outputs, both rebuilt on every theme change:

1. Pushes the active Omarchy palette into Thunderbird through
   browser.theme.update() (live, via native messaging).
2. Writes a small chrome overlay (chrome/omarchy-thunderbird.css, imported by
   userChrome.css) that reaches the tokens the WebExtension theme API cannot:
   the message-list layout ladder (--layout-*) and Thunderbird's stock accent
   palette (blue/green/yellow/amber), which otherwise leak off-theme colours
   into the thread pane. Chrome-only surfaces stay owned by the extension.

Spawned by Thunderbird when the extension calls connectNative(). Exits on
stdin EOF, per the native messaging protocol.
"""
import datetime
import json
import os
import selectors
import struct
import subprocess
import sys
import tomllib

STATE_DIR = os.path.expanduser("~/.local/state/omarchy/current")
COLORS_PATH = os.path.join(STATE_DIR, "theme", "colors.toml")
THEME_NAME_PATH = os.path.join(STATE_DIR, "theme.name")
CHROME_DIR = os.path.expanduser("~/.thunderbird/omarchy-profile/chrome")
CSS_PATH = os.path.join(CHROME_DIR, "omarchy-thunderbird.css")
USERCHROME_PATH = os.path.join(CHROME_DIR, "userChrome.css")
CSS_IMPORT = '@import url("omarchy-thunderbird.css");'


def read_message_stdin():
    raw_length = sys.stdin.buffer.read(4)
    if len(raw_length) == 0:
        return None
    length = struct.unpack("<I", raw_length)[0]
    sys.stdin.buffer.read(length)
    return True


def send_message(obj):
    data = json.dumps(obj).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(data)))
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def load_colors():
    try:
        with open(COLORS_PATH, "rb") as f:
            return tomllib.load(f)
    except (FileNotFoundError, tomllib.TOMLDecodeError, OSError):
        return None


def pick(raw, *keys):
    for key in keys:
        value = raw.get(key)
        if value:
            return value
    return None


def _clamp(v):
    return max(0, min(255, int(round(v))))


def _mix(color, other, t):
    """Blend '#rrggbb' color toward other by t in [0, 1]."""
    try:
        a = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
        b = [int(other[i:i + 2], 16) for i in (1, 3, 5)]
    except (TypeError, ValueError, IndexError):
        return color
    return "#%02x%02x%02x" % tuple(_clamp(x + (y - x) * t) for x, y in zip(a, b))


def _on(color):
    """Readable text colour for a given background (accent)."""
    try:
        r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    except (TypeError, ValueError, IndexError):
        return "#111111"
    lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    return "#111111" if lum > 0.5 else "#ffffff"


def _lum(color):
    try:
        r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    except (TypeError, ValueError, IndexError):
        return 0.0
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


def build_palette(raw):
    """Derive the full shade ladder. Omarchy palettes are often thin (no
    dark_background/lighter_background/selection, no 'mode'), so missing layers
    are synthesised instead of collapsing every surface to one flat colour."""
    bg = pick(raw, "background") or "#111111"
    dark_bg = pick(raw, "dark_background") or _mix(bg, "#000000", 0.12)
    darker_bg = pick(raw, "darker_background") or _mix(bg, "#000000", 0.28)
    lighter_bg = pick(raw, "lighter_background") or _mix(bg, "#ffffff", 0.10)
    fg = pick(raw, "foreground") or "#e6e6e6"
    bright_fg = pick(raw, "bright_foreground", "light_foreground") or fg
    accent = pick(raw, "accent") or "#faa968"
    selection = (pick(raw, "selection", "selection_background")
                 or _mix(bg, accent, 0.25))
    return {
        "bg": bg,
        "dark_bg": dark_bg,
        "darker_bg": darker_bg,
        "lighter_bg": lighter_bg,
        "fg": fg,
        "dark_fg": pick(raw, "dark_foreground") or _mix(fg, bg, 0.25),
        "accent": accent,
        "on_accent": _on(accent),
        "selection": selection,
        "border": _mix(bg, fg, 0.16),
        # Layout ladder for the message list / three-pane chrome. Omarchy
        # palettes carry no 'mode', so pick the direction from the background
        # luminance: dark themes go darkest->lightest (content first), light
        # themes lightest->darkest, mirroring Thunderbird's own defaults.
        "bg0": darker_bg if _lum(bg) < 0.5 else bg,
        "bg1": bg,
        "bg2": dark_bg if _lum(bg) < 0.5 else _mix(bg, "#000000", 0.06),
        "bg3": lighter_bg if _lum(bg) < 0.5 else _mix(bg, "#000000", 0.12),
        "bg4": (_mix(lighter_bg, dark_bg, 0.5) if _lum(bg) < 0.5
                else _mix(bg, "#000000", 0.20)),
        "tx0": bright_fg,
        "tx1": fg,
        "tx2": _mix(fg, bg, 0.35),
        "tx3": _mix(fg, bg, 0.55),
        "bd0": _mix(bg, fg, 0.10),
        "bd1": _mix(bg, fg, 0.18),
        "bd2": _mix(bg, fg, 0.28),
        # "Paper": the message/content surface. Slightly lighter than the chrome
        # on light themes (dark themes already go darker via bg0).
        "paper": _mix(bg, "#ffffff", 0.45) if _lum(bg) >= 0.5 else darker_bg,
    }


def build_theme_colors(raw):
    p = build_palette(raw)
    return {
        "frame": p["dark_bg"],
        "frame_inactive": p["darker_bg"],
        "tab_selected": p["bg"],
        "tab_text": p["fg"],
        "tab_background_text": p["dark_fg"],
        "tab_background_separator": p["border"],
        "tab_line": p["accent"],
        "tab_loading": p["accent"],
        "toolbar": p["bg"],
        "toolbar_text": p["fg"],
        "toolbar_field": p["lighter_bg"],
        "toolbar_field_text": p["fg"],
        "toolbar_field_border": p["border"],
        "toolbar_field_focus": p["lighter_bg"],
        "toolbar_field_text_focus": p["fg"],
        "toolbar_field_highlight": p["accent"],
        "toolbar_field_highlight_text": p["darker_bg"],
        "toolbar_top_separator": p["border"],
        "toolbar_bottom_separator": p["border"],
        "toolbar_vertical_separator": p["border"],
        "icons": p["fg"],
        "icons_attention": p["accent"],
        # Hover tint, NOT the saturated selection colour: the engine also feeds
        # this into --toolbarbutton-hover-bordercolor, which is used as the
        # border of compose address fields -- a saturated colour made every
        # unfocused To/Subject field glow red/green.
        "button_background_hover": _mix(p["bg"], p["accent"], 0.16),
        "button_background_active": _mix(p["bg"], p["accent"], 0.30),
        "popup": p["lighter_bg"],
        "popup_text": p["fg"],
        "popup_border": p["border"],
        "popup_highlight": p["accent"],
        "popup_highlight_text": p["darker_bg"],
        "sidebar": p["dark_bg"],
        "sidebar_text": p["fg"],
        "sidebar_border": p["border"],
        "sidebar_highlight": p["accent"],
        "sidebar_highlight_text": p["darker_bg"],
        "sidebar_highlight_border": p["accent"],
    }


def write_chrome_css(p):
    """Write the message-list overlay. Only tokens the extension cannot reach:
    the --layout-* ladder, the --tree-* card tokens and Thunderbird's stock
    --color-* accents (blue/green/yellow/amber) that are hardcoded in
    threadCard/threadPane."""
    if not os.path.isdir(CHROME_DIR):
        return
    try:
        with open(THEME_NAME_PATH) as f:
            theme = f.read().strip()
    except OSError:
        theme = "?"
    accent = p["accent"]
    mix = lambda color, pct: f"color-mix(in srgb, {color} {pct}%, transparent)"

    root = [
        ("--layout-background-0", p["bg0"]),
        ("--layout-background-1", p["bg1"]),
        ("--layout-background-2", p["bg2"]),
        ("--layout-background-3", p["bg3"]),
        ("--layout-background-4", p["bg4"]),
        ("--layout-color-0", p["tx0"]),
        ("--layout-color-1", p["tx1"]),
        ("--layout-color-2", p["tx2"]),
        ("--layout-color-3", p["tx3"]),
        ("--layout-border-0", p["bd0"]),
        ("--layout-border-1", p["bd1"]),
        ("--layout-border-2", p["bd2"]),
        ("--selected-item-color", accent),
        ("--selected-item-text-color", p["on_accent"]),
        ("--focus-outline-color", accent),
        ("--tabline-color", accent),
        ("--tree-pane-background", p["bg1"]),
        ("--tree-view-bg", p["bg0"]),
        ("--tree-view-color", p["tx1"]),
        ("--tree-card-background", p["bg1"]),
        ("--tree-card-border", "transparent"),
        ("--tree-card-border-hover", mix(accent, 18)),
        ("--tree-card-border-focus", mix(accent, 30)),
        ("--tree-card-border-selected", mix(accent, 30)),
        ("--tree-card-border-selected-unfocused", "transparent"),
        ("--tree-card-background-current", f"color-mix(in srgb, {accent} 7%, {p['bg1']})"),
        ("--tree-card-background-selected", f"color-mix(in srgb, {accent} 11%, {p['bg1']})"),
        ("--tree-card-background-selected-current", f"color-mix(in srgb, {accent} 14%, {p['bg1']})"),
        ("--tree-card-background-current-unfocused", f"color-mix(in srgb, {accent} 4%, {p['bg1']})"),
        ("--tree-card-background-selected-unfocused", f"color-mix(in srgb, {accent} 6%, {p['bg1']})"),
        ("--thread-line-color", p["bd1"]),
        ("--unread-color", p["tx0"]),
        ("--new-color", accent),
        ("--new-subject-color", accent),
        ("--read-status-fill", accent),
        ("--read-status-stroke", accent),
        ("--thread-pane-unread-fill", accent),
        ("--thread-pane-unread-stroke", accent),
        ("--thread-pane-flag-fill", accent),
        ("--thread-pane-flag-stroke", accent),
        # Fold Thunderbird's stock accent palette into the Omarchy palette.
        ("--color-blue-40", p["tx2"]),
        ("--color-blue-50", p["tx2"]),
        ("--color-blue-60", p["tx2"]),
        ("--color-blue-70", p["tx2"]),
        ("--color-green-40", accent),
        ("--color-green-50", accent),
        ("--color-green-60", accent),
        ("--color-yellow-30", accent),
        ("--color-yellow-40", accent),
        ("--color-amber-30", accent),
        ("--color-amber-50", accent),
        ("--color-amber-60", accent),
        ("--color-orange-30", accent),
        ("--color-orange-40", accent),
        ("--color-orange-50", accent),
        ("--color-orange-60", accent),
    ]

    lines = [
        "/* Auto-generated by omarchy_thunderbird_bridge — do not edit.",
        f"   Theme: {theme}  ·  {datetime.datetime.now().isoformat(timespec='seconds')}",
        "   Tokens the WebExtension theme API cannot reach: the message-list",
        "   layout ladder and Thunderbird's stock accent palette. */",
        ":root {",
    ]
    lines += [f"  {k}: {v} !important;" for k, v in root]
    lines += [
        "}",
        "",
        "/* Quick-filter bar: the lwtheme rule paints it as 50% of the toolbar over",
        "   the pane, which showed as a lighter band. Pin it to the pane colour. */",
        "#quick-filter-bar { background-color: var(--layout-background-1) !important; }",
        "/* Flatten the filter chips and the search field so nothing reads as a",
        "   lighter block; keep a subtle border + hover/pressed feedback. */",
        "#quick-filter-bar .button-group.quickFilterButtons,",
        "#quick-filter-bar .button-group.quickFilterButtons .button,",
        "#quick-filter-bar #qfb-sticky {",
        "  background-color: transparent !important;",
        "  border-color: transparent !important;",
        "}",
        "#quick-filter-bar .button-group.quickFilterButtons .button:hover {",
        "  background-color: color-mix(in srgb, var(--layout-color-1) 12%, transparent) !important;",
        "}",
        "#quick-filter-bar .button-group.quickFilterButtons .button[aria-pressed='true'] {",
        "  background-color: color-mix(in srgb, var(--selected-item-color) 25%, transparent) !important;",
        "  color: var(--layout-color-0) !important;",
        "}",
        "#quick-filter-bar #qfb-qs-textbox,",
        "#quick-filter-bar #qfb-qs-textbox input {",
        "  background-color: var(--layout-background-1) !important;",
        "  border-color: var(--layout-border-0) !important;",
        "}",
        "",
        "/* Smart/unified folders: the per-account colour bar is not part of the",
        "   Omarchy palette (the folder pane already hides it). To keep it as a",
        "   faint marker instead, replace display:none with:",
        "     background-color: var(--layout-color-3) !important; */",
        "#threadTree .account-indicator { display: none !important; }",
        "",
    ]
    with open(CSS_PATH, "w") as f:
        f.write("\n".join(lines))

    # Make sure userChrome.css pulls the overlay in.
    try:
        with open(USERCHROME_PATH) as f:
            current = f.read()
    except OSError:
        current = ""
    if CSS_IMPORT not in current:
        with open(USERCHROME_PATH, "w") as f:
            f.write(f"{CSS_IMPORT}\n\n{current}")
    else:
        # Bump mtime so Thunderbird re-reads the @import next launch.
        os.utime(USERCHROME_PATH)


def write_user_content_css(p):
    """userContent.css applies to the compose editor (about:blank?compose),
    where editorContent.css hardcodes red dotted borders around borderless
    tables and forms. Keep the guide lines, drop the red."""
    if not os.path.isdir(CHROME_DIR):
        return
    try:
        with open(THEME_NAME_PATH) as f:
            theme = f.read().strip()
    except OSError:
        theme = "?"
    body = f'''/* Auto-generated by omarchy_thunderbird_bridge — do not edit.
   Theme: {theme}  ·  {datetime.datetime.now().isoformat(timespec="seconds")}
   Compose editor (about:blank?compose) only. */
@-moz-document url("about:blank?compose") {{
  /* editorContent.css forces Thunderbird's own dark body; use the palette. */
  body {{
    color: {p["tx1"]} !important;
    background-color: {p["paper"]} !important;
  }}

  /* editorContent.css draws hardcoded "1px dotted red" around tables/cells
     that have no border, "otherwise they are invisible". Keep the guide
     lines, just quiet them to the palette. */
  table:is([empty-cells], [border="0"], :not([border])),
  table:is([border="0"], :not([border])) > tr > :is(td, th),
  table:is([border="0"], :not([border])) > :is(thead, tbody, tfoot) > tr > :is(td, th) {{
    border: 1px dotted {p["bd2"]} !important;
  }}

  form {{ border: 2px dashed {p["bd2"]} !important; }}
  label {{ border: 1px dotted {p["bd2"]} !important; }}
}}
'''

    conv = f'''
/* Conversations add-on view. It renders in its own document (root
   element #conversationWrapper) and hardcodes its own light-dark palette, so
   it needs its own copy of the Omarchy palette. */
html:has(#conversationWrapper) {{
  /* Must match the theme's lightness: Gecko propagates this color-scheme into
     the nested message-body iframes, so forcing "dark" on a light theme made
     every email render dark. */
  color-scheme: {"dark" if _lum(p["bg"]) < 0.5 else "light"} !important;
  --application-background-color: {p["paper"]} !important;
  --application-foreground-color: {p["tx1"]} !important;
  --layout-background-0: {p["paper"]} !important;
  --layout-background-1: {p["bg1"]} !important;
  --layout-background-2: {p["bg2"]} !important;
  --layout-background-3: {p["bg3"]} !important;
  --layout-background-4: {p["bg4"]} !important;
  --layout-color-0: {p["tx0"]} !important;
  --layout-color-1: {p["tx1"]} !important;
  --layout-color-2: {p["tx2"]} !important;
  --layout-color-3: {p["tx3"]} !important;
  --layout-border-0: {p["bd0"]} !important;
  --layout-border-1: {p["bd1"]} !important;
  --layout-border-2: {p["bd2"]} !important;
  --button-background-color: {p["bg2"]} !important;
  --button-background-color-hover: {_mix(p["bg"], p["accent"], 0.16)} !important;
  --button-background-color-active: {_mix(p["bg"], p["accent"], 0.30)} !important;
  --button-text-color: {p["tx1"]} !important;
  --button-border-color: {p["bd1"]} !important;
  --selected-item-color: {p["accent"]} !important;
  --selected-item-text-color: {p["on_accent"]} !important;
  --focus-outline-color: {p["accent"]} !important;
  --thread-pane-flag-fill: {p["accent"]} !important;
  --thread-pane-flag-stroke: {p["accent"]} !important;
  --color-gray-40: {p["bd2"]} !important;
  --color-gray-50: {p["tx2"]} !important;
  --color-gray-60: {p["tx2"]} !important;
}}
'''

    reader_color = "" if _lum(p["bg"]) >= 0.5 else f'  color: {p["tx1"]} !important;\n'
    reader = f'''
/* Traditional message reader: a message opened in a tab renders in its own
   document with no theme of its own, so it falls back to Canvas (white). Put
   the palette behind it so it matches the Conversations view. */
html:has(.moz-text-html),
html:has(.moz-text-flowed),
html:has(.moz-text-plain) {{
  background-color: {p["paper"]} !important;
}}
html:has(.moz-text-html) body,
html:has(.moz-text-flowed) body,
html:has(.moz-text-plain) body {{
  background-color: {p["paper"]} !important;
{reader_color}}}
'''
    with open(os.path.join(CHROME_DIR, "userContent.css"), "w") as f:
        f.write(body + "\n" + conv + "\n" + reader)


def push_current_theme():
    raw = load_colors()
    if raw is None:
        return
    p = build_palette(raw)
    colors = {k: v for k, v in build_theme_colors(raw).items() if v}
    if colors:
        send_message({"colors": colors})
    write_chrome_css(p)
    write_user_content_css(p)


def main():
    push_current_theme()

    watcher = subprocess.Popen(
        ["inotifywait", "-m", "-q", "-e", "create,moved_to,modify,delete", STATE_DIR],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )

    sel = selectors.DefaultSelector()
    sel.register(sys.stdin.buffer, selectors.EVENT_READ, "stdin")
    sel.register(watcher.stdout, selectors.EVENT_READ, "watch")

    try:
        while True:
            for key, _ in sel.select():
                if key.data == "stdin":
                    if read_message_stdin() is None:
                        return
                elif key.data == "watch":
                    if not watcher.stdout.readline():
                        continue
                    push_current_theme()
    finally:
        watcher.terminate()


if __name__ == "__main__":
    main()
