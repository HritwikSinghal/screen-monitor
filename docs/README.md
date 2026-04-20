# Documentation

This directory contains implementation and developer reference documentation for the screen-monitor project.

For user-facing installation and run instructions, see the root [README.md](/README.md).

## Documentation Index

- **[architecture.md](architecture.md)** — Module responsibilities, components, and data flow. Start here to understand how the pieces fit together.

- **[zero-blink-capture.md](zero-blink-capture.md)** — Deep technical narrative on why ScreenCast + PipeWire eliminates blink artifacts, the restore_token caching mechanism, and atomic persistence patterns.

- **[portal-flow.md](portal-flow.md)** — D-Bus XDG portal method reference. Complete options dicts and response shapes for CreateSession, SelectSources, Start, and OpenPipeWireRemote.

- **[troubleshooting.md](troubleshooting.md)** — Failure modes by symptom, with root causes and fixes for all seven common issues.

- **[development.md](development.md)** — Project layout, test commands, Python version requirements, extension points, and the target image contract.

## Audience

- **Root README**: How to install and run the tool.
- **docs/**: How the tool works, how to extend it, how to debug it.
