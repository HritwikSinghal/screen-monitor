# Screen Monitor

- [Screen Monitor](#screen-monitor)
  - [What](#what)
  - [Why](#why)
  - [Who](#who)
  - [How](#how)
  - [Where](#where)
  - [When](#when)
  - [Before](#before)

## What

is this?

```python
while True:
    # Capture SS of your screen
    # if a condition is met:
    #       runs an action
    # sleep(<time_period>)
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

- install `uv`
- `uv run main.py`

## Where

to run this?

Currently tested on GNOME 49 on arch linux with `xdg-desktop-portal-gnome` installed.

The initial commit was tested on MacOS (i know, i know ).

## When

to run this?

Do you really want me to answer that for you? `(-_-)`.

## Before

Additional platform-specific requirements:

For Linux (GNOME Wayland, zero-blink capture):

Screen capture uses the `org.freedesktop.portal.ScreenCast` portal + a
persistent PipeWire stream, so there is no per-frame compositor flash. On
first launch you will see a GNOME picker dialog once; after you pick a monitor
or window, the `restore_token` is cached at
`~/.local/share/screen-monitor/portal.json` and subsequent runs start silently.

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

To revoke the cached permission, visit GNOME Settings -> Privacy -> Screen
Sharing, or simply delete `~/.local/share/screen-monitor/portal.json`.

For macOS:

```bash
brew install python-tk
```

For Windows:

```bash
# No additional system dependencies required
```
