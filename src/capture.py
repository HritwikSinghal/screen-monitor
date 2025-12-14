#!/usr/bin/python3
import json

# this used to live at https://gitlab.gnome.org/snippets/814
# but has since been deleted, the original author is unknown
# reuploading here for safe keeping

import dbus
import secrets
import re

from gi.repository import GLib
from dbus.mainloop.glib import DBusGMainLoop


class PortalBus:
    def __init__(self):
        DBusGMainLoop(set_as_default=True)

        self.bus = dbus.SessionBus()
        self.portal = self.bus.get_object('org.freedesktop.portal.Desktop', '/org/freedesktop/portal/desktop')

    def sender_name(self):
        return re.sub('\.', '_', self.bus.get_unique_name()).lstrip(':')

    def request_handle(self, token) -> str:
        return '/org/freedesktop/portal/desktop/request/%s/%s' % (self.sender_name(), token)


class PortalScreenshot:
    def __init__(self):
        self.portal_bus = PortalBus()
        self.bus = self.portal_bus.bus
        self.portal = self.portal_bus.portal

    def request(self, callback, parent_window=''):
        request_token = self.new_unique_token()
        # https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.Screenshot.html#org-freedesktop-portal-screenshot-screenshot
        options = {
            'handle_token': request_token,
            "modal": False,
        }

        handle: str = self.portal_bus.request_handle(request_token)

        self.bus.add_signal_receiver(callback,
                                     'Response',
                                     'org.freedesktop.portal.Request',
                                     'org.freedesktop.portal.Desktop',
                                     handle)

        self.portal.Screenshot(parent_window, options, dbus_interface='org.freedesktop.portal.Screenshot')

    @staticmethod
    def new_unique_token():
        return 'screen_shot_py_%s' % secrets.token_hex(16)


class Capture:
    def __init__(self):
        self.loop = GLib.MainLoop()

    def callback(self, response, result):
        if response == 0:
            print(result['uri'])
        else:
            print("Failed to screenshot: %d" % response)

        self.loop.quit()

    def start(self):
        portal_screenshot = PortalScreenshot()
        portal_screenshot.request(self.callback)

        try:
            self.loop.run()
        except KeyboardInterrupt:
            self.loop.quit()
        finally:
            return
