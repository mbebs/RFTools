# -*- coding: utf-8 -*-

import os

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets, QtGui
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'about_dialog_base.ui'))


class AboutRFToolsDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        """Constructor."""
        super(AboutRFToolsDialog, self).__init__(parent)
        self.setupUi(self)

        self.donateButton.clicked.connect(self._open_donate_link)

    def _open_donate_link(self):
        # Open PayPal donation link in the default browser
        url = QUrl('https://paypal.me/rftools')
        QDesktopServices.openUrl(url)
