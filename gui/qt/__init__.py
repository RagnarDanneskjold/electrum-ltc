#!/usr/bin/env python
#
# Electrum - lightweight Bitcoin client
# Copyright (C) 2012 thomasv@gitorious
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import sys, time, datetime, re, threading
from electrum_ltc.i18n import _, set_language
from electrum_ltc.util import print_error, print_msg, parse_url
from electrum_ltc.plugins import run_hook
import os.path, json, ast, traceback
import shutil


try:
    import PyQt4
except Exception:
    sys.exit("Error: Could not import PyQt4 on Linux systems, you may try 'sudo apt-get install python-qt4'")

from PyQt4.QtGui import *
from PyQt4.QtCore import *
import PyQt4.QtCore as QtCore

from electrum_ltc import WalletStorage, Wallet
from electrum_ltc.i18n import _
from electrum_ltc.bitcoin import MIN_RELAY_TX_FEE

try:
    import icons_rc
except Exception:
    sys.exit("Error: Could not import icons_rc.py, please generate it with: 'pyrcc4 icons.qrc -o gui/qt/icons_rc.py'")

from util import *
from main_window import ElectrumWindow
from electrum_ltc.plugins import init_plugins


class OpenFileEventFilter(QObject):
    def __init__(self, windows):
        self.windows = windows
        super(OpenFileEventFilter, self).__init__()

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.FileOpen:
            if len(self.windows) >= 1:
                self.windows[0].set_url(event.url().toEncoded())
                return True
        return False


class ElectrumGui:

    def __init__(self, config, network, app=None):
        self.network = network
        self.config = config
        self.windows = []
        self.efilter = OpenFileEventFilter(self.windows)
        if app is None:
            self.app = QApplication(sys.argv)
        self.app.installEventFilter(self.efilter)
        init_plugins(self)


    def build_tray_menu(self):
        m = QMenu()
        m.addAction(_("Show/Hide"), self.show_or_hide)
        m.addAction(_("Dark/Light"), self.toggle_tray_icon)
        m.addSeparator()
        m.addAction(_("Exit Electrum-LTC"), self.close)
        self.tray.setContextMenu(m)

    def toggle_tray_icon(self):
        self.dark_icon = not self.dark_icon
        self.config.set_key("dark_icon", self.dark_icon, True)
        icon = QIcon(":icons/electrum_dark_icon.png") if self.dark_icon else QIcon(':icons/electrum_light_icon.png')
        self.tray.setIcon(icon)

    def show_or_hide(self):
        self.tray_activated(QSystemTrayIcon.DoubleClick)

    def tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            if self.current_window.isMinimized() or self.current_window.isHidden():
                self.current_window.show()
                self.current_window.raise_()
            else:
                self.current_window.hide()

    def close(self):
        self.current_window.close()



    def go_full(self):
        self.config.set_key('lite_mode', False, True)
        self.lite_window.hide()
        self.main_window.show()
        self.main_window.raise_()
        self.current_window = self.main_window

    def go_lite(self):
        self.config.set_key('lite_mode', True, True)
        self.main_window.hide()
        self.lite_window.show()
        self.lite_window.raise_()
        self.current_window = self.lite_window


    def init_lite(self):
        import lite_window
        if not self.check_qt_version():
            if self.config.get('lite_mode') is True:
                msg = "Electrum was unable to load the 'Lite GUI' because it needs Qt version >= 4.7.\nChanging your config to use the 'Classic' GUI"
                QMessageBox.warning(None, "Could not start Lite GUI.", msg)
                self.config.set_key('lite_mode', False, True)
                sys.exit(0)
            self.lite_window = None
            self.main_window.show()
            self.main_window.raise_()
            return

        actuator = lite_window.MiniActuator(self.main_window)
        actuator.load_theme()
        self.lite_window = lite_window.MiniWindow(actuator, self.go_full, self.config)
        driver = lite_window.MiniDriver(self.main_window, self.lite_window)

        if self.config.get('lite_mode') is True:
            self.go_lite()
        else:
            self.go_full()


    def check_qt_version(self):
        qtVersion = qVersion()
        return int(qtVersion[0]) >= 4 and int(qtVersion[2]) >= 7



    def main(self, url):

        storage = WalletStorage(self.config)
        if not storage.file_exists:
            import installwizard
            wizard = installwizard.InstallWizard(self.config, self.network, storage)
            wallet = wizard.run()
            if not wallet: 
                exit()

        elif storage.get('wallet_type') in ['2of3'] and storage.get('seed') is None:
            import installwizard
            wizard = installwizard.InstallWizard(self.config, self.network, storage)
            wallet = wizard.run(action= 'create2of3')
            if not wallet: 
                exit()

        else:
            wallet = Wallet(storage)
            wallet.start_threads(self.network)
            

        # init tray
        self.dark_icon = self.config.get("dark_icon", False)
        icon = QIcon(":icons/electrum_dark_icon.png") if self.dark_icon else QIcon(':icons/electrum_light_icon.png')
        self.tray = QSystemTrayIcon(icon, None)
        self.tray.setToolTip('Electrum-LTC')
        self.tray.activated.connect(self.tray_activated)
        self.build_tray_menu()
        self.tray.show()

        # main window
        self.main_window = w = ElectrumWindow(self.config, self.network, self)
        self.current_window = self.main_window

        #lite window
        self.init_lite()

        # plugins that need to change the GUI do it here
        run_hook('init')

        w.load_wallet(wallet)

        s = Timer()
        s.start()

        self.windows.append(w)
        if url: w.set_url(url)
        w.app = self.app
        w.connect_slots(s)
        w.update_wallet()

        self.app.exec_()

        wallet.stop_threads()


