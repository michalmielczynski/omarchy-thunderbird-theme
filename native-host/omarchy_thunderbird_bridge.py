#!/usr/bin/env python3
"""Native messaging host: watches the active Omarchy theme and pushes its
colors into Thunderbird via browser.theme.update(), live, on every change.

Spawned by Thunderbird when the "Omarchy Theme Sync" extension calls
browser.runtime.connectNative(). Exits cleanly when Thunderbird closes the
connection (stdin EOF), per the native messaging protocol.
"""
import json
import os
import selectors
import struct
import subprocess
import sys
import tomllib

STATE_DIR = os.path.expanduser("~/.local/state/omarchy/current")
COLORS_PATH = os.path.join(STATE_DIR, "theme", "colors.toml")


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


def build_theme_colors(raw):
    bg = pick(raw, "background")
    dark_bg = pick(raw, "dark_background") or bg
    darker_bg = pick(raw, "darker_background") or dark_bg
    lighter_bg = pick(raw, "lighter_background") or bg
    fg = pick(raw, "foreground")
    dark_fg = pick(raw, "dark_foreground") or fg
    accent = pick(raw, "accent")
    selection = pick(raw, "selection") or lighter_bg

    return {
        "frame": dark_bg,
        "frame_inactive": darker_bg,
        "tab_selected": bg,
        "tab_text": fg,
        "tab_background_text": dark_fg,
        "tab_background_separator": selection,
        "tab_line": accent,
        "tab_loading": accent,
        "toolbar": bg,
        "toolbar_text": fg,
        "toolbar_field": lighter_bg,
        "toolbar_field_text": fg,
        "toolbar_field_border": selection,
        "toolbar_field_focus": lighter_bg,
        "toolbar_field_text_focus": fg,
        "toolbar_field_highlight": accent,
        "toolbar_field_highlight_text": darker_bg,
        "toolbar_top_separator": selection,
        "toolbar_bottom_separator": selection,
        "toolbar_vertical_separator": selection,
        "icons": fg,
        "icons_attention": accent,
        "button_background_hover": selection,
        "button_background_active": accent,
        "popup": lighter_bg,
        "popup_text": fg,
        "popup_border": selection,
        "popup_highlight": accent,
        "popup_highlight_text": darker_bg,
        "sidebar": dark_bg,
        "sidebar_text": fg,
        "sidebar_border": selection,
        "sidebar_highlight": accent,
        "sidebar_highlight_text": darker_bg,
        "sidebar_highlight_border": accent,
    }


def push_current_theme():
    raw = load_colors()
    if raw is None:
        return
    colors = {k: v for k, v in build_theme_colors(raw).items() if v}
    if not colors:
        return
    send_message({"colors": colors})


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
