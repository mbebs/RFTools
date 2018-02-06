# -*- coding: utf-8 -*-
"""
/***************************************************************************
 RFTools
                                 A QGIS plugin
 Simple Tools for the RF Engineer
                             -------------------
        begin                : 2018-01-29
        copyright            : (C) 2018 by Leonard Fodje
        email                : mbebs@live.com
        git sha              : $Format:%H$
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
 This script initializes the plugin, making it known to QGIS.
"""
import sys
import os
import site

site.addsitedir(os.path.abspath(os.path.dirname(__file__) + '/ext-libs'))

def classFactory(iface):
    from .rf_tools import RFTools
    return RFTools(iface)

