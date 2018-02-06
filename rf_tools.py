# -*- coding: utf-8 -*-
"""
/***************************************************************************
 RFTools
                                 A QGIS plugin
 Simple Tools for the RF Engineer
                              -------------------
        begin                : 2018-01-29
        git sha              : $Format:%H$
        copyright            : (C) 2018 by Leonard Fodje
        email                : mbebs@live.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from PyQt4.QtGui import QAction, QIcon
from PyQt4.QtCore import QUrl

# Import the code for the dialog
from .siteSee import SiteSeeWidget
import os.path
import webbrowser


class RFTools:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):

        # Save reference to the QGIS interface
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.siteSeeDialog = None
        self.toolbar = self.iface.addToolBar(u'RF Tools')
        self.toolbar.setObjectName(u'RFTools')


    def initGui(self):

        # Initialize the create shape menu item
        icon = QIcon(os.path.dirname(__file__) + '/images/tower.png')
        self.siteSeeAction = QAction(icon, u'SiteSee', self.iface.mainWindow())
        self.siteSeeAction.triggered.connect(self.siteSeeTool)
        self.iface.addPluginToMenu(u'RF Tools', self.siteSeeAction)
        self.toolbar.addAction(self.siteSeeAction)

        # Help
        icon = QIcon(os.path.dirname(__file__) + '/images/help.png')
        self.helpAction = QAction(icon, u'RF Tools Help', self.iface.mainWindow())
        self.helpAction.triggered.connect(self.help)
        self.iface.addPluginToMenu(u'RF Tools', self.helpAction)

    def unload(self):
        #Removes the plugin menu item and icon from QGIS GUI."""
        self.iface.removePluginMenu(u'RF Tools', self.siteSeeAction)
        self.iface.removePluginMenu(u'RF Tools', self.helpAction)

        # Remove from toolbar
        self.iface.removeToolBarIcon(self.siteSeeAction)

        # remove the toolbar
        del self.toolbar


    def siteSeeTool(self):
        if self.siteSeeDialog is None:
            self.siteSeeDialog = SiteSeeWidget(self.iface, self.iface.mainWindow())
        self.siteSeeDialog.show()


    def help(self):
        '''Display a help page'''
        url = QUrl.fromLocalFile(os.path.dirname(__file__) + '/index.html').toString()
        webbrowser.open(url, new=2)