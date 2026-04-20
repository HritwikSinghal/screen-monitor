#!/usr/bin/python3
"""Zero-blink screen capture on GNOME Wayland via the XDG ScreenCast portal and PipeWire.

The ScreenCast portal gives us a persistent PipeWire stream. Once the stream is
open, frames flow from the compositor without any per-frame portal round-trip,
so there is no visible flash. A ``restore_token`` is persisted so the user is
only prompted to pick a source on first run.
"""

import json
import logging
import os
import re
import secrets

import dbus
import gi
import numpy as np

gi.require_version("Gst", "1.0")
gi.require_version("GstApp", "1.0")
from dbus.mainloop.glib import DBusGMainLoop  # noqa: E402
from gi.repository import GLib, Gst, GstApp  # noqa: E402, F401

logger = logging.getLogger(__name__)

PORTAL_BUS_NAME = "org.freedesktop.portal.Desktop"
PORTAL_OBJECT_PATH = "/org/freedesktop/portal/desktop"
SCREENCAST_IFACE = "org.freedesktop.portal.ScreenCast"
REQUEST_IFACE = "org.freedesktop.portal.Request"

# SelectSources.types bitmask
SOURCE_MONITOR = 1
SOURCE_WINDOW = 2

# SelectSources.cursor_mode
CURSOR_EMBEDDED = 2

# SelectSources.persist_mode
PERSIST_UNTIL_REVOKED = 2

PORTAL_CALL_TIMEOUT_SEC = 180  # user may take time to pick a source on first run
FRAME_PULL_TIMEOUT_NS = 2 * Gst.SECOND if hasattr(Gst, "SECOND") else 2_000_000_000


class TokenStore:
    """Persists the ScreenCast ``restore_token`` to disk.

    Mirrors the pattern from speedofsound's PropertiesStore: write once, load
    every subsequent launch so the portal reuses the prior approval and skips
    the picker dialog.
    """

    def __init__(self, path: str | None = None):
        if path is None:
            xdg = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
            path = os.path.join(xdg, "screen-monitor", "portal.json")
        self.path = path

    def load(self) -> str | None:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Ignoring unreadable token store %s: %s", self.path, e)
            return None
        token = data.get("restore_token")
        return token if isinstance(token, str) and token else None

    def save(self, token: str) -> None:
        directory = os.path.dirname(self.path)
        os.makedirs(directory, mode=0o700, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"restore_token": token}, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    def clear(self) -> None:
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass


class _PortalBus:
    def __init__(self):
        DBusGMainLoop(set_as_default=True)
        self.bus = dbus.SessionBus()
        self.portal = self.bus.get_object(PORTAL_BUS_NAME, PORTAL_OBJECT_PATH)

    def sender_name(self) -> str:
        return re.sub(r"\.", "_", self.bus.get_unique_name()).lstrip(":")

    def request_handle(self, token: str) -> str:
        return f"/org/freedesktop/portal/desktop/request/{self.sender_name()}/{token}"

    @staticmethod
    def new_token(prefix: str) -> str:
        return f"{prefix}_{secrets.token_hex(8)}"


class _PortalCallError(RuntimeError):
    def __init__(self, method: str, code: int):
        super().__init__(f"Portal call {method} failed with response {code}")
        self.method = method
        self.code = code


def _run_portal_call(bus: dbus.SessionBus, request_path: str, invoke) -> dict:
    """Call a portal method and block on its ``Response`` signal.

    The portal's async request pattern: the method returns a request object
    path; completion fires a ``Response(u, a{sv})`` signal on that path.
    """
    loop = GLib.MainLoop()
    captured: dict = {}

    def on_response(code, results):
        captured["code"] = int(code)
        captured["results"] = results
        loop.quit()

    def on_timeout():
        captured.setdefault("timeout", True)
        loop.quit()
        return False

    def do_invoke():
        # Run inside the main loop so a synchronous exception from invoke()
        # (e.g. portal not on the bus, serialization failure) stops the loop
        # immediately instead of blocking until the timeout fires.
        try:
            invoke()
        except Exception as e:
            captured["invoke_error"] = e
            loop.quit()
        return False  # one-shot idle callback

    # Resolve the well-known portal name to its unique bus name so the match
    # rule binds reliably on older dbus-python versions and is not confused
    # by name-ownership flaps.
    try:
        sender_name = bus.get_name_owner(PORTAL_BUS_NAME)
    except dbus.DBusException:
        sender_name = PORTAL_BUS_NAME

    bus.add_signal_receiver(
        on_response,
        signal_name="Response",
        dbus_interface=REQUEST_IFACE,
        bus_name=sender_name,
        path=request_path,
    )
    timeout_id = GLib.timeout_add_seconds(PORTAL_CALL_TIMEOUT_SEC, on_timeout)
    GLib.idle_add(do_invoke)
    try:
        loop.run()
    finally:
        GLib.source_remove(timeout_id)
        bus.remove_signal_receiver(
            on_response,
            signal_name="Response",
            dbus_interface=REQUEST_IFACE,
            bus_name=sender_name,
            path=request_path,
        )

    if "invoke_error" in captured:
        raise captured["invoke_error"]
    if captured.get("timeout"):
        raise RuntimeError("Portal call timed out")
    return captured


class ScreenCastSession:
    """Opens a ScreenCast portal session and resolves a PipeWire node + fd."""

    def __init__(self, token_store: TokenStore, source_types: int = SOURCE_MONITOR | SOURCE_WINDOW):
        self._bus = _PortalBus()
        self._token_store = token_store
        self._source_types = source_types
        self.session_handle: str | None = None
        self.node_id: int | None = None
        self.pipewire_fd: int | None = None

    def open(self) -> None:
        restore_token = self._token_store.load()
        try:
            self._open_with(restore_token)
        except _PortalCallError as e:
            # If Start fails with a cached token (revoked, compositor upgrade),
            # wipe it and retry once with a fresh picker dialog.
            if restore_token and e.method == "Start":
                logger.warning("Cached restore_token rejected (%s); re-prompting.", e)
                self._token_store.clear()
                # Release any session/fd opened on the first attempt before
                # starting a new one, otherwise they leak until process exit.
                self.close()
                self._open_with(None)
            else:
                self.close()
                raise
        except Exception:
            self.close()
            raise

    def _open_with(self, restore_token: str | None) -> None:
        self._create_session()
        self._select_sources(restore_token)
        streams, new_token = self._start()
        if new_token:
            self._token_store.save(new_token)
        self.node_id = int(streams[0][0])
        self.pipewire_fd = self._open_pipewire_remote()

    def _create_session(self) -> None:
        handle_token = _PortalBus.new_token("sm_create")
        session_token = _PortalBus.new_token("sm_sess")
        request_path = self._bus.request_handle(handle_token)
        options = dbus.Dictionary(
            {
                "handle_token": dbus.String(handle_token),
                "session_handle_token": dbus.String(session_token),
            },
            signature="sv",
        )

        def invoke():
            self._bus.portal.CreateSession(options, dbus_interface=SCREENCAST_IFACE)

        captured = _run_portal_call(self._bus.bus, request_path, invoke)
        code = captured.get("code", -1)
        if code != 0:
            raise _PortalCallError("CreateSession", code)
        results = captured.get("results") or {}
        handle = results.get("session_handle")
        if handle is None:
            raise RuntimeError("Portal CreateSession returned no session_handle")
        self.session_handle = str(handle)

    def _select_sources(self, restore_token: str | None) -> None:
        handle_token = _PortalBus.new_token("sm_select")
        request_path = self._bus.request_handle(handle_token)
        options = dbus.Dictionary(
            {
                "handle_token": dbus.String(handle_token),
                "types": dbus.UInt32(self._source_types),
                "multiple": dbus.Boolean(False),
                "cursor_mode": dbus.UInt32(CURSOR_EMBEDDED),
                "persist_mode": dbus.UInt32(PERSIST_UNTIL_REVOKED),
            },
            signature="sv",
        )
        if restore_token:
            options["restore_token"] = dbus.String(restore_token)

        def invoke():
            self._bus.portal.SelectSources(
                self.session_handle, options, dbus_interface=SCREENCAST_IFACE
            )

        captured = _run_portal_call(self._bus.bus, request_path, invoke)
        code = captured.get("code", -1)
        if code != 0:
            raise _PortalCallError("SelectSources", code)

    def _start(self) -> tuple[list, str | None]:
        handle_token = _PortalBus.new_token("sm_start")
        request_path = self._bus.request_handle(handle_token)
        options = dbus.Dictionary(
            {"handle_token": dbus.String(handle_token)}, signature="sv"
        )

        def invoke():
            self._bus.portal.Start(
                self.session_handle, "", options, dbus_interface=SCREENCAST_IFACE
            )

        captured = _run_portal_call(self._bus.bus, request_path, invoke)
        code = captured.get("code", -1)
        if code != 0:
            raise _PortalCallError("Start", code)
        results = captured.get("results") or {}
        streams = list(results.get("streams", []))
        if not streams:
            raise RuntimeError("Portal returned no streams")
        new_token = results.get("restore_token")
        new_token = str(new_token) if new_token else None
        return streams, new_token

    def _open_pipewire_remote(self) -> int:
        options = dbus.Dictionary({}, signature="sv")
        fd_obj = self._bus.portal.OpenPipeWireRemote(
            self.session_handle, options, dbus_interface=SCREENCAST_IFACE
        )
        # dbus-python returns a UnixFd whose .take() hands ownership of the raw fd.
        return int(fd_obj.take()) if hasattr(fd_obj, "take") else int(fd_obj)

    def close(self) -> None:
        # The session owns the PipeWire fd it received from OpenPipeWireRemote;
        # pipewiresrc does not take ownership, so we must close it ourselves
        # after the pipeline has been torn down.
        if self.session_handle is not None:
            try:
                session_obj = self._bus.bus.get_object(PORTAL_BUS_NAME, self.session_handle)
                session_obj.Close(dbus_interface="org.freedesktop.portal.Session")
            except dbus.DBusException as e:
                logger.warning("Session close failed: %s", e)
            finally:
                self.session_handle = None
        if self.pipewire_fd is not None:
            try:
                os.close(self.pipewire_fd)
            except OSError as e:
                logger.debug("pipewire fd close ignored: %s", e)
            finally:
                self.pipewire_fd = None


class PipeWireCapture:
    """GStreamer pipeline that consumes the portal's PipeWire node as BGR frames."""

    _gst_initialized = False

    def __init__(self, pipewire_fd: int, node_id: int):
        self.pipewire_fd = pipewire_fd
        self.node_id = node_id
        self.pipeline: Gst.Pipeline | None = None
        self.appsink = None

    @classmethod
    def _ensure_gst(cls) -> None:
        if not cls._gst_initialized:
            Gst.init(None)
            cls._gst_initialized = True

    def start(self) -> None:
        self._ensure_gst()
        desc = (
            f"pipewiresrc fd={self.pipewire_fd} path={self.node_id} do-timestamp=true "
            f"! videoconvert "
            f"! video/x-raw,format=BGR "
            f"! appsink name=sink max-buffers=1 drop=true sync=false emit-signals=false"
        )
        try:
            self.pipeline = Gst.parse_launch(desc)
        except GLib.Error as e:
            raise RuntimeError(
                "Failed to build GStreamer pipeline. Ensure 'gst-plugin-pipewire' "
                "and 'gst-plugins-good' are installed. Original error: %s" % e
            ) from e
        self.appsink = self.pipeline.get_by_name("sink")
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError("GStreamer pipeline refused to enter PLAYING")

    def get_frame(self) -> np.ndarray:
        if self.appsink is None:
            raise RuntimeError("PipeWireCapture.start() was not called")
        sample = self.appsink.try_pull_sample(FRAME_PULL_TIMEOUT_NS)
        if sample is None:
            raise RuntimeError("No frame available from PipeWire stream (timeout)")
        caps = sample.get_caps().get_structure(0)
        width = caps.get_value("width")
        height = caps.get_value("height")
        buf = sample.get_buffer()
        success, mapinfo = buf.map(Gst.MapFlags.READ)
        if not success:
            raise RuntimeError("Failed to map PipeWire buffer")
        try:
            raw = bytes(mapinfo.data)
            expected = width * height * 3
            if len(raw) == expected:
                frame = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3)
            else:
                # Row padding: compute stride from total size, then trim.
                stride = len(raw) // height
                frame = (
                    np.frombuffer(raw, dtype=np.uint8)
                    .reshape(height, stride)[:, : width * 3]
                    .reshape(height, width, 3)
                )
            return frame.copy()
        finally:
            buf.unmap(mapinfo)

    def stop(self) -> None:
        if self.pipeline is not None:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline = None
            self.appsink = None


class Capture:
    """Public façade: open a persistent ScreenCast + PipeWire session, pull frames."""

    def __init__(self, token_store: TokenStore | None = None):
        self.token_store = token_store or TokenStore()
        self._session: ScreenCastSession | None = None
        self._stream: PipeWireCapture | None = None

    def start(self) -> "Capture":
        logger.info("Opening ScreenCast portal session")
        session = ScreenCastSession(self.token_store)
        session.open()
        logger.info("Portal session opened: node=%s fd=%s", session.node_id, session.pipewire_fd)
        try:
            stream = PipeWireCapture(session.pipewire_fd, session.node_id)
            stream.start()
        except Exception:
            # Release the portal session + fd if the GStreamer pipeline fails
            # to build; otherwise we leak both until process exit.
            session.close()
            raise
        self._session = session
        self._stream = stream
        return self

    def get_frame(self) -> np.ndarray:
        if self._stream is None:
            raise RuntimeError("Capture.start() was not called")
        return self._stream.get_frame()

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream = None
        if self._session is not None:
            self._session.close()
            self._session = None

    def __enter__(self) -> "Capture":
        return self.start()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
