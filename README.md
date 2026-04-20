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

People who hate ads `(⌐⊙_⊙)`.

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

For Linux:

```bash
# For Ubuntu/Debian
sudo apt-get update
sudo apt-get install python3-tk python3-dev scrot
# Install either PulseAudio or ALSA
sudo apt-get install pulseaudio
# or
sudo apt-get install alsa-utils
```

For macOS:

```bash
brew install python-tk
```

For Windows:

```bash
# No additional system dependencies required
```
