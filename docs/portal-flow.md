# XDG ScreenCast Portal D-Bus Reference

## Overview

The XDG ScreenCast portal is accessed via D-Bus. The tool communicates with the compositor through four sequential D-Bus method calls, each using an asynchronous request-response pattern.

## D-Bus Basics

**Bus:** `org.freedesktop.portal.Desktop` (defined `src/capture.py:26`)  
**Object path:** `/org/freedesktop/portal/desktop` (defined `src/capture.py:27`)  
**ScreenCast interface:** `org.freedesktop.portal.ScreenCast` (defined `src/capture.py:28`)  
**Request interface:** `org.freedesktop.portal.Request` (defined `src/capture.py:29`)

All methods are called on the ScreenCast interface. Responses arrive as signals on dynamically created request object paths.

## Asynchronous Request-Response Pattern

Portal methods return immediately with a request object path. The actual response is delivered via a D-Bus signal. The tool waits for this signal using GLib's MainLoop via `_run_portal_call()` at `src/capture.py:111-153`.

### Request Path Derivation

Each method call creates a unique request path:

```
/org/freedesktop/portal/desktop/request/{sender_name}/{handle_token}
```

Where:
- `sender_name`: the application's unique D-Bus name (e.g., `:1.23`) with dots replaced by underscores and the leading colon stripped
- `handle_token`: a random hex token generated per-call

Code at `src/capture.py:96-97`:
```python
def request_handle(self, token: str) -> str:
    return f"/org/freedesktop/portal/desktop/request/{self.sender_name()}/{token}"
```

The sender name is computed at `src/capture.py:93-94`:
```python
def sender_name(self) -> str:
    return re.sub(r"\.", "_", self.bus.get_unique_name()).lstrip(":")
```

### Signal Handler Registration

`_run_portal_call()` registers a signal handler on the request path:

```python
bus.add_signal_receiver(
    on_response,
    signal_name="Response",
    dbus_interface=REQUEST_IFACE,
    bus_name=PORTAL_BUS_NAME,
    path=request_path,
)
```

The portal fires a `Response(u, a{sv})` signal on that path when the request completes. The signal carries:
- `u` (uint32): response code (0 = success, non-zero = error)
- `a{sv}` (dict): results (key => variant)

A 180-second timeout (line 137) ensures the call does not block indefinitely if the portal is unresponsive.

## Method: CreateSession

**Code location:** `src/capture.py:190-208`

Creates a portal session object. Must be called first.

### Options

| Key | Type | Value | Purpose |
|-----|------|-------|---------|
| `handle_token` | String | random hex token | uniquely identifies this request |
| `session_handle_token` | String | random hex token | identifier for the new session object |

Example invocation at line 203:
```python
self._bus.portal.CreateSession(options, dbus_interface=SCREENCAST_IFACE)
```

### Response

| Key | Type | Value |
|-----|------|-------|
| `session_handle` | String | D-Bus object path of the session (e.g., `/org/freedesktop/portal/desktop/session/1`) |

Extracted at line 208:
```python
self.session_handle = str(captured["results"]["session_handle"])
```

## Method: SelectSources

**Code location:** `src/capture.py:210-233`

Displays the source picker (monitor or window) and sets up the source selection. The picker UI only appears on first run if no `restore_token` is provided.

### Options

| Key | Type | Value | Purpose |
|-----|------|-------|---------|
| `handle_token` | String | random hex token | uniquely identifies this request |
| `types` | UInt32 | 1 (MONITOR) \| 2 (WINDOW) | bitmask of which source types to show |
| `multiple` | Boolean | False | allow selecting one source only |
| `cursor_mode` | UInt32 | 2 (CURSOR_EMBEDDED) | embed the cursor in the captured frame |
| `persist_mode` | UInt32 | 2 (PERSIST_UNTIL_REVOKED) | token valid until revocation or compositor upgrade |
| `restore_token` | String | *(optional)* cached token | if present, compositor skips the picker |

Constants at `src/capture.py:31-39`:
```python
SOURCE_MONITOR = 1
SOURCE_WINDOW = 2
CURSOR_EMBEDDED = 2
PERSIST_UNTIL_REVOKED = 2
```

Example invocation at lines 227-229:
```python
self._bus.portal.SelectSources(
    self.session_handle, options, dbus_interface=SCREENCAST_IFACE
)
```

Note: `SelectSources` takes `self.session_handle` (the path returned by CreateSession) as the first argument.

### Response

No data is returned; the selection is stored internally by the portal. Successful response code 0 indicates the user completed the picker dialog (or the token was accepted without showing the picker).

## Method: Start

**Code location:** `src/capture.py:235-256`

Starts the capture stream. This is where the `restore_token` is generated and returned.

### Arguments

| Position | Type | Value | Purpose |
|----------|------|-------|---------|
| 1 (implicit) | object path | `self.session_handle` | the session from CreateSession |
| 2 (explicit) | String | `""` (empty string) | parent window (unused; leave empty) |
| 3 | Dict | options | request metadata |

### Options

| Key | Type | Value | Purpose |
|-----|------|-------|---------|
| `handle_token` | String | random hex token | uniquely identifies this request |

Example invocation at lines 243-245:
```python
self._bus.portal.Start(
    self.session_handle, "", options, dbus_interface=SCREENCAST_IFACE
)
```

### Response

| Key | Type | Value |
|-----|------|-------|
| `streams` | Array of (UInt32, Dict) | list of `(node_id, properties)` tuples |
| `restore_token` | String | *(optional)* token to cache for next run |

The `node_id` (first element of the tuple) is extracted at line 187:
```python
self.node_id = int(streams[0][0])
```

The `restore_token` is extracted at lines 254-255:
```python
new_token = results.get("restore_token")
new_token = str(new_token) if new_token else None
```

If a `restore_token` is returned, it is saved to disk at line 186:
```python
self._token_store.save(new_token)
```

## Method: OpenPipeWireRemote

**Code location:** `src/capture.py:258-264`

Obtains the file descriptor for the PipeWire stream. This is the final step before frame capture can begin.

### Arguments

| Position | Type | Value | Purpose |
|----------|------|-------|---------|
| 1 (implicit) | object path | `self.session_handle` | the session from CreateSession |
| 2 | Dict | options | request metadata (always empty) |

### Options

Empty dict (no options):
```python
options = dbus.Dictionary({}, signature="sv")
```

Example invocation at lines 260-261:
```python
fd_obj = self._bus.portal.OpenPipeWireRemote(
    self.session_handle, options, dbus_interface=SCREENCAST_IFACE
)
```

### Response

A **UnixFd** object representing the file descriptor. dbus-python wraps Unix file descriptors as UnixFd objects. To extract the raw fd:

```python
return int(fd_obj.take()) if hasattr(fd_obj, "take") else int(fd_obj)
```

Code at line 264:
```python
return int(fd_obj.take()) if hasattr(fd_obj, "take") else int(fd_obj)
```

The `.take()` method **transfers ownership** of the fd to the caller; the UnixFd object will not close it on garbage collection. This allows the fd to be passed to GStreamer for long-term use.

## Error Handling

All four methods are wrapped in `_run_portal_call()`. If the response code is non-zero, a `_PortalCallError` is raised (line 105-108):

```python
class _PortalCallError(RuntimeError):
    def __init__(self, method: str, code: int):
        super().__init__(f"Portal call {method} failed with response {code}")
        self.method = method
        self.code = code
```

Each method checks the response code and raises if non-zero. Example from `_create_session()` at lines 206-207:

```python
if captured["code"] != 0:
    raise _PortalCallError("CreateSession", captured["code"])
```

If `_start()` fails with a cached token, the `open()` method (line 169-179) catches the error and retries without the token:

```python
if restore_token and e.method == "Start":
    logger.warning("Cached restore_token rejected (%s); re-prompting.", e)
    self._token_store.clear()
    self._open_with(None)
```

## Timeout

All four method calls share a single 180-second timeout defined at `src/capture.py:41`:

```python
PORTAL_CALL_TIMEOUT_SEC = 180
```

If a response is not received within 180 seconds, `_run_portal_call()` raises `RuntimeError("Portal call timed out")` at line 152. This accommodates first-run scenarios where the user may take time to pick a source.
