# Screen Monitor

- [Screen Monitor](#screen-monitor)
  - [What](#what)
  - [Why](#why)
  - [Who](#who)
  - [How](#how)
  - [Where](#where)
  - [When](#when)
  - [Before](#before)
    - [GNOME Wayland, zero-blink capture](#gnome-wayland-zero-blink-capture)
    - [Hyprland](#hyprland)
    - [macOS:](#macos)
  - [Known quirks](#known-quirks)

## What

is this?

```python
while True:
    # Capture a window/screen
    # if target_image not_found:
    #       mute_audio
    pass
```

## Why

is this?

To automatically mute my system volume when in-stream ads start on J\*oShitstar while watching some cricket match. (and unmute again ofc...).

## Who

is this for?

People who hate ads `(-_-)`.

## How

to run this?

**With Nix:**

```bash
nix run             # run the monitor (same as ".#start"); add flags after --, e.g. nix run . -- -v
nix run ".#test"    # run tests
```

**With uv:**

```bash
uv run main.py
```

## Where

to run this?

Tested on Arch Linux with:

- GNOME 49 + `xdg-desktop-portal-gnome`
- Hyprland 0.56 + `xdg-desktop-portal-hyprland` 1.4 (see [Hyprland](#hyprland))

The initial commit was tested on MacOS (i know, i know ).

## When

to run this?

Do you really want me to answer that for you? `(-_-)`.

## Before

you run this.

Additional platform-specific requirements:

### GNOME Wayland, zero-blink capture

Screen capture uses the `org.freedesktop.portal.ScreenCast` portal + a
persistent PipeWire stream, so there is no per-frame compositor flash. On
first launch you will see a GNOME picker dialog once; after you pick a monitor
or window, the `restore_token` is cached at
`~/.local/share/screen-monitor/portal.json` and subsequent runs start silently
(`main.py --select` shows the picker again).

Audio uses `pactl` against PipeWire's PulseAudio compatibility layer
(`pipewire-pulse`). If your distro still ships a standalone PulseAudio daemon,
`pactl` will continue to work and no extra changes are required.

```bash
# Arch
sudo pacman -S pipewire pipewire-pulse \
    xdg-desktop-portal xdg-desktop-portal-gnome \
    gstreamer gst-plugins-base gst-plugins-good gst-plugin-pipewire
```

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install pipewire pipewire-pulse \
    xdg-desktop-portal xdg-desktop-portal-gnome \
    gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
    gstreamer1.0-pipewire
```

### Hyprland

Install `xdg-desktop-portal-hyprland` instead of `xdg-desktop-portal-gnome`.
xdph only hands out a restore token when asked to, so without this the picker
reappears on every launch (the app logs a warning when that happens):

```ini
# ~/.config/hypr/xdph.conf
screencopy {
    allow_token_by_default = true
}
```

Or tick "Allow a restore token" in the picker. Pick the whole monitor, not a
window (see [Known quirks](#known-quirks)). The watermark is found at any window size from about
a quarter-size window up to fullscreen. To pick a different source, run `uv run main.py --select`.

To revoke the cached permission, visit GNOME Settings -> Privacy -> Screen
Sharing, or simply delete `~/.local/share/screen-monitor/portal.json`.

### macOS:

```bash
brew install python-tk
```

## Known quirks

What to expect:

- **Audio mutes whenever the target image (e.g. the channel logo) is missing**,
  not just during ads. When sharing the whole screen, a menu, popup, or window
  covering the logo also mutes. When sharing one window, things on top of it
  are ignored; only changes inside that window count.
- **Hyprland: share the whole monitor, not a window.** If a shared window is
  resized or made fullscreen, the picture freezes for good. Fix:
  `uv run main.py --select` and pick the monitor.
- **"No new frames for 30s" warning.** Hyprland only sends a new picture when
  something on screen changes. If a `Frames resumed` line follows, the screen
  was just still (e.g. a paused video) and all is fine. If it never comes, the
  picture is frozen: restart the app.
- **The app quits by itself if the shared window closes.** It turns the
  sound back on before exiting.

Debug tips: [docs/troubleshooting.md](docs/troubleshooting.md#debugging).
