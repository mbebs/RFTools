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

 ***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from qgis.PyQt.QtCore import QSettings, QTranslator, qVersion, QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.core import (QgsProject, QgsApplication, QgsVectorLayer, QgsFeature, 
                       QgsGeometry, QgsPointXY, QgsField, QgsFields, QgsWkbTypes,
                       QgsSymbol, QgsRendererCategory, QgsCategorizedSymbolRenderer,
                       QgsFillSymbol, QgsMarkerSymbol, QgsSingleSymbolRenderer)
from qgis.gui import QgsMapToolEmitPoint
from qgis.PyQt.QtCore import QVariant
import math
# Initialize Qt resources from file resources.py
from . import resources
# Import the code for the dialog
from .rf_tools_dialog import RFToolsDialog
from .pci_rsi_planner_dialog import PciRsiPlannerDialog
from .tilt_optimizer_dialog import TiltOptimizerDialog
from .azimuth_optimizer_dialog import AzimuthOptimizerDialog
from .coverage_prediction_dialog import CoveragePredictionDialog
from .interference_analysis_dialog import InterferenceAnalysisDialog
from .about_dialog import AboutRFToolsDialog
import os.path


class RFTools:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'RFTools_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)


        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&RF Tools')
        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'RFTools')
        self.toolbar.setObjectName(u'RFTools')

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('RFTools', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Icon for this action. Can be a QIcon instance or a
            resource path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: QIcon or str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        # Create the dialog (after translation) and keep reference
        self.dlg = RFToolsDialog()

        # Allow passing either a QIcon instance or a path
        if isinstance(icon_path, QIcon):
            icon = icon_path
        else:
            icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        # Use separate icons for each feature (with fallback to default icon.svg)
        default_icon_path = os.path.join(self.plugin_dir, 'icon.svg')
        if not os.path.exists(default_icon_path):
            default_icon_path = os.path.join(self.plugin_dir, 'icon.png')
        
        # Site See icon (green)
        sitesee_icon_path = os.path.join(self.plugin_dir, 'icon_sitesee.svg')
        if not os.path.exists(sitesee_icon_path):
            sitesee_icon_path = os.path.join(self.plugin_dir, 'icon_sitesee.png')
        if not os.path.exists(sitesee_icon_path):
            sitesee_icon_path = default_icon_path
        site_see_icon = QIcon(sitesee_icon_path)
        self.add_action(
            site_see_icon,
            text=self.tr(u'Site See'),
            callback=self.run,
            parent=self.iface.mainWindow())

        # PCI / RSI Planner icon (blue)
        planner_icon_path = os.path.join(self.plugin_dir, 'icon_planner.svg')
        if not os.path.exists(planner_icon_path):
            planner_icon_path = os.path.join(self.plugin_dir, 'icon_planner.png')
        if not os.path.exists(planner_icon_path):
            planner_icon_path = default_icon_path
        planner_icon = QIcon(planner_icon_path)
        planner_action = QAction(planner_icon, self.tr(u'PCI / RSI Planner'), self.iface.mainWindow())
        planner_action.triggered.connect(self.run_planner)
        self.toolbar.addAction(planner_action)
        self.iface.addPluginToMenu(self.menu, planner_action)
        self.actions.append(planner_action)

        # Tilt Optimizer icon (purple)
        tilt_icon_path = os.path.join(self.plugin_dir, 'icon_tilt.svg')
        if not os.path.exists(tilt_icon_path):
            tilt_icon_path = os.path.join(self.plugin_dir, 'icon_tilt.png')
        if not os.path.exists(tilt_icon_path):
            tilt_icon_path = default_icon_path
        tilt_icon = QIcon(tilt_icon_path)
        tilt_action = QAction(tilt_icon, self.tr(u'Tilt Optimizer'), self.iface.mainWindow())
        tilt_action.triggered.connect(self.run_tilt_optimizer)
        self.toolbar.addAction(tilt_action)
        self.iface.addPluginToMenu(self.menu, tilt_action)
        self.actions.append(tilt_action)

        # Azimuth Optimizer icon (cyan)
        azimuth_icon_path = os.path.join(self.plugin_dir, 'icon_azimuth.svg')
        if not os.path.exists(azimuth_icon_path):
            azimuth_icon_path = os.path.join(self.plugin_dir, 'icon_azimuth.png')
        if not os.path.exists(azimuth_icon_path):
            azimuth_icon_path = default_icon_path
        azimuth_icon = QIcon(azimuth_icon_path)
        azimuth_action = QAction(azimuth_icon, self.tr(u'Azimuth Optimizer'), self.iface.mainWindow())
        azimuth_action.triggered.connect(self.run_azimuth_optimizer)
        self.toolbar.addAction(azimuth_action)
        self.iface.addPluginToMenu(self.menu, azimuth_action)
        self.actions.append(azimuth_action)

        # Coverage Prediction icon (red/orange)
        coverage_icon_path = os.path.join(self.plugin_dir, 'icon_coverage.svg')
        if not os.path.exists(coverage_icon_path):
            coverage_icon_path = os.path.join(self.plugin_dir, 'icon_coverage.png')
        if not os.path.exists(coverage_icon_path):
            coverage_icon_path = default_icon_path
        coverage_icon = QIcon(coverage_icon_path)
        coverage_action = QAction(coverage_icon, self.tr(u'Coverage Prediction'), self.iface.mainWindow())
        coverage_action.triggered.connect(self.run_coverage_prediction)
        self.toolbar.addAction(coverage_action)
        self.iface.addPluginToMenu(self.menu, coverage_action)
        self.actions.append(coverage_action)

        # Interference Analysis icon (red)
        interference_icon_path = os.path.join(self.plugin_dir, 'icon_interference.svg')
        if not os.path.exists(interference_icon_path):
            interference_icon_path = os.path.join(self.plugin_dir, 'icon_interference.png')
        if not os.path.exists(interference_icon_path):
            interference_icon_path = default_icon_path
        interference_icon = QIcon(interference_icon_path)
        interference_action = QAction(interference_icon, self.tr(u'Interference Analysis'), self.iface.mainWindow())
        interference_action.triggered.connect(self.run_interference_analysis)
        self.toolbar.addAction(interference_action)
        self.iface.addPluginToMenu(self.menu, interference_action)
        self.actions.append(interference_action)

        # About RF Tools icon (orange)
        about_icon_path = os.path.join(self.plugin_dir, 'icon_about.svg')
        if not os.path.exists(about_icon_path):
            about_icon_path = os.path.join(self.plugin_dir, 'icon_about.png')
        if not os.path.exists(about_icon_path):
            about_icon_path = default_icon_path
        about_icon = QIcon(about_icon_path)
        about_action = QAction(about_icon, self.tr(u'About RF Tools'), self.iface.mainWindow())
        about_action.triggered.connect(self.run_about)
        self.toolbar.addAction(about_action)
        self.iface.addPluginToMenu(self.menu, about_action)
        self.actions.append(about_action)


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.menu,
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar


    def run(self):
        """Run method that performs all the real work"""
        layers = list(QgsProject.instance().mapLayers().values())
        layer_list = []
        self._layer_map = {}
        
        for layer in layers:
            if isinstance(layer, QgsVectorLayer):
                layer_list.append(layer.name())
                self._layer_map[layer.name()] = layer

        self.dlg.selectLayerComboBox.clear()
        self.dlg.selectLayerComboBox.addItems(layer_list)
        
        # Disconnect any existing connections to avoid duplicates
        try:
            self.dlg.selectLayerComboBox.currentTextChanged.disconnect(self._populate_fields)
        except:
            pass
        
        try:
            self.dlg.runButton.clicked.disconnect(self._create_sectors)
        except:
            pass
        
        # Populate field combo boxes when layer is selected
        self.dlg.selectLayerComboBox.currentTextChanged.connect(self._populate_fields)
        if layer_list:
            self._populate_fields(layer_list[0])
        
        # Connect the run button to create sectors
        self.dlg.runButton.clicked.connect(self._create_sectors)

        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        self.dlg.exec_()
    
    def _populate_fields(self, layer_name):
        """Populate field combo boxes based on selected layer"""
        if not layer_name or layer_name not in self._layer_map:
            return
        
        layer = self._layer_map[layer_name]
        field_names = [field.name() for field in layer.fields()]
        
        self.dlg.hubXComboBox.clear()
        self.dlg.hubXComboBox.addItems(field_names)
        
        self.dlg.hubYComboBox.clear()
        self.dlg.hubYComboBox.addItems(field_names)
        
        self.dlg.azimuthComboBox.clear()
        self.dlg.azimuthComboBox.addItems(field_names)
        
        self.dlg.beamwidthComboBox.clear()
        self.dlg.beamwidthComboBox.addItem('(Use Manual Value)')
        self.dlg.beamwidthComboBox.addItems(field_names)
        
        self.dlg.sectorSizeComboBox.clear()
        self.dlg.sectorSizeComboBox.addItem('(Use Manual Value)')
        self.dlg.sectorSizeComboBox.addItems(field_names)
        
        # Optional sector position fields
        self.dlg.sectorXComboBox.clear()
        self.dlg.sectorXComboBox.addItem('(Use Hub Position)')
        self.dlg.sectorXComboBox.addItems(field_names)
        
        self.dlg.sectorYComboBox.clear()
        self.dlg.sectorYComboBox.addItem('(Use Hub Position)')
        self.dlg.sectorYComboBox.addItems(field_names)
        
        # Optional band field
        self.dlg.bandComboBox.clear()
        self.dlg.bandComboBox.addItem('(No Band Field)')
        self.dlg.bandComboBox.addItems(field_names)
    
    def _create_sectors(self):
        """Create sector polygons and connection lines for remote sectors"""
        layer_name = self.dlg.selectLayerComboBox.currentText()
        if not layer_name or layer_name not in self._layer_map:
            QMessageBox.warning(self.iface.mainWindow(), 'RF Tools', 'Please select a valid layer.')
            return
        
        source_layer = self._layer_map[layer_name]
        site_lat_field = self.dlg.hubYComboBox.currentText()
        site_lon_field = self.dlg.hubXComboBox.currentText()
        azimuth_field = self.dlg.azimuthComboBox.currentText()
        beamwidth_field = self.dlg.beamwidthComboBox.currentText()
        sectorsize_field = self.dlg.sectorSizeComboBox.currentText()
        sector_x_field = self.dlg.sectorXComboBox.currentText()
        sector_y_field = self.dlg.sectorYComboBox.currentText()
        band_field = self.dlg.bandComboBox.currentText()
        if band_field == '(No Band Field)':
            band_field = None
        new_layer_name = 'Sectors'  # Default layer name
        
        # Create output layers
        crs = source_layer.crs().authid()
        sector_layer = QgsVectorLayer(f'Polygon?crs={crs}', new_layer_name, 'memory')
        line_layer = QgsVectorLayer(f'LineString?crs={crs}', f'{new_layer_name}_Links', 'memory')
        site_layer = QgsVectorLayer(f'Point?crs={crs}', f'{new_layer_name}_Sites', 'memory')
        
        # Add fields
        sector_provider = sector_layer.dataProvider()
        line_provider = line_layer.dataProvider()
        
        sector_fields = QgsFields()
        for field in source_layer.fields():
            sector_fields.append(field)
        sector_provider.addAttributes(sector_fields)
        sector_layer.updateFields()
        
        line_fields = QgsFields()
        site_id_field = QgsField('site_id', QVariant.String)
        site_id_field.setLength(255)
        line_fields.append(site_id_field)
        sector_id_field = QgsField('sector_id', QVariant.String)
        sector_id_field.setLength(255)
        line_fields.append(sector_id_field)
        line_provider.addAttributes(line_fields)
        line_layer.updateFields()
        
        site_provider = site_layer.dataProvider()
        site_fields = QgsFields()
        site_lat_field_obj = QgsField('site_lat', QVariant.Double)
        site_lat_field_obj.setLength(20)
        site_lat_field_obj.setPrecision(6)
        site_fields.append(site_lat_field_obj)
        site_lon_field_obj = QgsField('site_lon', QVariant.Double)
        site_lon_field_obj.setLength(20)
        site_lon_field_obj.setPrecision(6)
        site_fields.append(site_lon_field_obj)
        site_provider.addAttributes(site_fields)
        site_layer.updateFields()
        
        sector_features = []
        line_features = []
        site_points = {}  # Track unique site locations
        
        # First pass: collect all features and group by site+azimuth to find bands
        site_sectors = {}  # Key: (site_lat, site_lon, azimuth), Value: list of (feat, band_value)
        
        for feat in source_layer.getFeatures():
            geom = feat.geometry()
            
            # Get site coordinates
            if not site_lat_field or not site_lon_field:
                continue
            
            try:
                site_lat = float(feat[site_lat_field])
                site_lon = float(feat[site_lon_field])
            except (ValueError, KeyError, TypeError):
                continue
            
            # Get azimuth
            try:
                azimuth = float(feat[azimuth_field]) if azimuth_field else 0
            except:
                azimuth = 0
            
            # Get band value
            band_value = None
            if band_field:
                try:
                    band_value = float(feat[band_field])
                except:
                    band_value = 0
            
            # Group by site and azimuth
            key = (round(site_lat, 6), round(site_lon, 6), round(azimuth, 1))
            if key not in site_sectors:
                site_sectors[key] = []
            site_sectors[key].append((feat, band_value))
        
        # Determine band ordering for each site+azimuth group
        # Sort bands: lowest frequency (largest sector) first
        for key in site_sectors:
            site_sectors[key].sort(key=lambda x: x[1] if x[1] else 0)
        
        # Second pass: create sectors with proper sizing and z-order
        # First, collect all features with their calculated radius for sorting
        sector_data = []
        
        for feat in source_layer.getFeatures():
            geom = feat.geometry()
            
            # Get site coordinates first (required)
            if not site_lat_field or not site_lon_field:
                continue
            
            try:
                site_lat = float(feat[site_lat_field])
                site_lon = float(feat[site_lon_field])
                site_point = QgsPointXY(site_lon, site_lat)
                
                # Track unique site locations for site markers
                site_key = (round(site_lat, 6), round(site_lon, 6))
                if site_key not in site_points:
                    site_points[site_key] = (site_lat, site_lon)
            except (ValueError, KeyError, TypeError):
                # Skip if site coordinates are invalid
                continue
            
            # Check if sector has remote position
            if sector_x_field and sector_y_field and \
               sector_x_field != '(Use Hub Position)' and sector_y_field != '(Use Hub Position)':
                try:
                    sector_lon = float(feat[sector_x_field])
                    sector_lat = float(feat[sector_y_field])
                    sector_point = QgsPointXY(sector_lon, sector_lat)
                    # Create connection line for remote sector
                    line_geom = QgsGeometry.fromPolylineXY([site_point, sector_point])
                    line_feat = QgsFeature()
                    line_feat.setGeometry(line_geom)
                    line_feat.setAttributes([str(feat.id()), str(feat.id())])
                    line_features.append(line_feat)
                except (ValueError, KeyError, TypeError):
                    # If remote coordinates invalid, use site location
                    sector_point = site_point
            else:
                # Co-located sector
                sector_point = site_point
            
            # Get azimuth
            try:
                azimuth = float(feat[azimuth_field]) if azimuth_field else 0
            except:
                azimuth = 0
            
            # Get beamwidth - check if using manual value or field
            if beamwidth_field == '(Use Manual Value)' or not beamwidth_field:
                # Use manual value from spin box
                beamwidth = self.dlg.beamwidthSpinBox.value()
            else:
                # Use value from field
                try:
                    beamwidth = float(feat[beamwidth_field])
                except:
                    beamwidth = 65
            
            # Get sector size - check if using manual value or field
            if sectorsize_field == '(Use Manual Value)' or not sectorsize_field:
                # Use manual value from spin box
                radius_meters = self.dlg.sectorSizeSpinBox.value()
            else:
                # Use value from field
                try:
                    radius_meters = float(feat[sectorsize_field])
                except:
                    radius_meters = 1000
            
            # Get band value if band field is specified
            band_value = None
            if band_field:
                try:
                    band_value = float(feat[band_field])
                except:
                    band_value = 0
            
            # Determine sector size based on band position in group
            # Find this sector's position in its site+azimuth group
            key = (round(site_lat, 6), round(site_lon, 6), round(azimuth, 1))
            band_index = 0
            num_bands = 1
            
            if key in site_sectors and band_field:
                group = site_sectors[key]
                num_bands = len(group)
                # Find this feature's index in the sorted group
                for idx, (f, b) in enumerate(group):
                    if f.id() == feat.id():
                        band_index = idx
                        break
            
            # Calculate sector size with offset for multiple bands
            # Lowest frequency (index 0) gets full size
            # Each subsequent band gets progressively smaller
            if num_bands > 1 and band_field:
                # Create visible offset: each band is 15% smaller than the previous
                # This ensures all bands are visible as nested sectors
                scale_factor = 1.0 - (band_index * 0.15)
                scale_factor = max(0.4, scale_factor)  # Minimum 40% of original size
                adjusted_radius_meters = radius_meters * scale_factor
            else:
                adjusted_radius_meters = radius_meters
            
            # Convert meters to degrees (rough approximation: 1 degree ≈ 111,000 meters at equator)
            radius_deg = adjusted_radius_meters / 111000.0
            
            # Create sector polygon and store with calculated radius for sorting
            sector_geom = self._create_sector_polygon(sector_point, azimuth, beamwidth, radius_deg)
            
            # Store feature data with radius for sorting
            sector_data.append({
                'feature': feat,
                'geometry': sector_geom,
                'radius': radius_deg,
                'band_value': band_value if band_field else 0
            })
        
        # Sort sectors by radius in descending order (largest first) so smaller sectors are drawn on top
        sector_data.sort(key=lambda x: (-x['radius'], x['band_value']))
        
        # Create features in sorted order
        for data in sector_data:
            sector_feat = QgsFeature()
            sector_feat.setGeometry(data['geometry'])
            sector_feat.setAttributes(data['feature'].attributes())
            sector_features.append(sector_feat)
        
        # Create site point features
        site_features = []
        for site_key, (lat, lon) in site_points.items():
            site_feat = QgsFeature()
            site_geom = QgsGeometry.fromPointXY(QgsPointXY(lon, lat))
            site_feat.setGeometry(site_geom)
            site_feat.setAttributes([lat, lon])
            site_features.append(site_feat)
        
        # Add features to layers
        sector_provider.addFeatures(sector_features)
        sector_layer.updateExtents()
        
        if line_features:
            line_provider.addFeatures(line_features)
            line_layer.updateExtents()
        
        if site_features:
            site_provider.addFeatures(site_features)
            site_layer.updateExtents()
        
        # Add layers to project
        QgsProject.instance().addMapLayer(sector_layer)
        
        # Apply color coding to sectors
        if self.dlg.colorCodeByBandCheckBox.isChecked() and band_field:
            self._apply_band_colors(sector_layer, band_field)
        elif self.dlg.colorCodeCheckBox.isChecked():
            self._apply_sector_colors(sector_layer, azimuth_field)
        
        if line_features:
            QgsProject.instance().addMapLayer(line_layer)
        
        # Add and style site markers
        if site_features:
            QgsProject.instance().addMapLayer(site_layer)
            self._apply_site_marker_style(site_layer)
        
        # Show completion message
        message_parts = [f'Created {len(sector_features)} sectors']
        if site_features:
            message_parts.append(f'{len(site_features)} sites')
        if line_features:
            message_parts.append(f'{len(line_features)} connection lines')
        
        QMessageBox.information(self.iface.mainWindow(), 'RF Tools', 
                              ' and '.join(message_parts) + '.')
    
    def _create_sector_polygon(self, center, azimuth, beamwidth, radius):
        """Create a sector polygon geometry"""
        points = [center]
        
        # Calculate start and end angles
        start_angle = azimuth - beamwidth / 2.0
        end_angle = azimuth + beamwidth / 2.0
        
        # Create arc points
        num_points = max(int(beamwidth / 5), 10)  # At least 10 points
        for i in range(num_points + 1):
            angle = start_angle + (end_angle - start_angle) * i / num_points
            angle_rad = math.radians(angle)
            
            x = center.x() + radius * math.sin(angle_rad)
            y = center.y() + radius * math.cos(angle_rad)
            points.append(QgsPointXY(x, y))
        
        points.append(center)  # Close the polygon
        
        return QgsGeometry.fromPolygonXY([points])
    
    def _apply_site_marker_style(self, layer):
        """Apply styling to site marker points - small filled circles"""
        # Create a simple marker symbol
        symbol = QgsMarkerSymbol.createSimple({
            'name': 'circle',
            'color': '50,50,50,255',  # Dark gray/black
            'outline_color': 'white',
            'outline_width': '0.5',
            'size': '3'  # Small 3pt circle
        })
        
        renderer = QgsSingleSymbolRenderer(symbol)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
    
    def _apply_sector_colors(self, layer, azimuth_field):
        """Apply color coding to sectors based on azimuth ranges"""
        if not azimuth_field:
            return
        
        # Define azimuth ranges and colors (typical sector configurations)
        # Colors chosen to be distinct and visually appealing
        categories = []
        
        # Sector 1: 315-45° (North) - Red
        cat1 = QgsRendererCategory(
            '0-60',
            QgsFillSymbol.createSimple({'color': '231,76,60,180', 'outline_color': '192,57,43', 'outline_width': '0.5'}),
            'Sector 1 (0-60°)'
        )
        categories.append(cat1)
        
        # Sector 2: 60-180° (East/Southeast) - Green
        cat2 = QgsRendererCategory(
            '60-180',
            QgsFillSymbol.createSimple({'color': '46,204,113,180', 'outline_color': '39,174,96', 'outline_width': '0.5'}),
            'Sector 2 (60-180°)'
        )
        categories.append(cat2)
        
        # Sector 3: 180-300° (South/Southwest) - Blue
        cat3 = QgsRendererCategory(
            '180-300',
            QgsFillSymbol.createSimple({'color': '52,152,219,180', 'outline_color': '41,128,185', 'outline_width': '0.5'}),
            'Sector 3 (180-300°)'
        )
        categories.append(cat3)
        
        # Sector 4: 300-360° (West/Northwest) - Orange
        cat4 = QgsRendererCategory(
            '300-360',
            QgsFillSymbol.createSimple({'color': '230,126,34,180', 'outline_color': '211,84,0', 'outline_width': '0.5'}),
            'Sector 4 (300-360°)'
        )
        categories.append(cat4)
        
        # Create expression to categorize azimuths
        expression = f'''
        CASE 
            WHEN "{azimuth_field}" >= 0 AND "{azimuth_field}" < 60 THEN '0-60'
            WHEN "{azimuth_field}" >= 60 AND "{azimuth_field}" < 180 THEN '60-180'
            WHEN "{azimuth_field}" >= 180 AND "{azimuth_field}" < 300 THEN '180-300'
            WHEN "{azimuth_field}" >= 300 AND "{azimuth_field}" <= 360 THEN '300-360'
            ELSE 'Other'
        END
        '''
        
        renderer = QgsCategorizedSymbolRenderer(expression, categories)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
    
    def _apply_band_colors(self, layer, band_field):
        """Apply color coding to sectors based on unique band values"""
        if not band_field:
            return
        
        # Get unique band values from the layer
        unique_bands = set()
        for feature in layer.getFeatures():
            band_value = feature[band_field]
            if band_value is not None and str(band_value).strip():
                try:
                    # Try to convert to float for numeric bands, otherwise use as string
                    band_float = float(band_value)
                    # If conversion succeeds and it's a whole number, use as int string
                    if band_float.is_integer():
                        band_str = str(int(band_float))
                    else:
                        band_str = str(band_float)
                except (ValueError, TypeError):
                    # If conversion fails, use as string
                    band_str = str(band_value)
                unique_bands.add(band_str)
        
        if not unique_bands:
            return
        
        # Sort the bands for consistent ordering
        try:
            # Try to sort numerically if all bands can be converted to numbers
            sorted_bands = sorted(unique_bands, key=lambda x: float(x) if x.replace('.', '', 1).isdigit() else float('inf'))
        except (ValueError, TypeError):
            # Fall back to string sort if any band can't be converted to a number
            sorted_bands = sorted(unique_bands)
        
        # Define a color palette with enough distinct colors
        # Using a perceptually distinct color palette
        color_palette = [
            (192, 57, 43),    # Dark Red
            (52, 152, 219),   # Blue
            (46, 204, 113),   # Green
            (230, 126, 34),   # Orange
            (155, 89, 182),   # Purple
            (241, 196, 15),   # Yellow
            (22, 160, 133),   # Teal
            (231, 76, 60),    # Red
            (41, 128, 185),   # Dark Blue
            (39, 174, 96),    # Dark Green
            (211, 84, 0),     # Dark Orange
            (142, 68, 173),   # Dark Purple
            (243, 156, 18),   # Dark Yellow
            (44, 62, 80),     # Dark Gray
            (127, 140, 141)   # Gray
        ]
        
        # Create categories for each unique band
        categories = []
        for i, band in enumerate(sorted_bands):
            # Cycle through the color palette if we have more bands than colors
            color_idx = i % len(color_palette)
            r, g, b = color_palette[color_idx]
            
            # Create a slightly darker version for the outline
            outline_r = max(0, r - 40)
            outline_g = max(0, g - 40)
            outline_b = max(0, b - 40)
            
            # Create the symbol with semi-transparent fill
            symbol = QgsFillSymbol.createSimple({
                'color': f'{r},{g},{b},180',
                'outline_color': f'{outline_r},{outline_g},{outline_b}',
                'outline_width': '0.5'
            })
            
            # Create the category
            cat = QgsRendererCategory(
                band,
                symbol,
                f'Band {band}'
            )
            categories.append(cat)
        
        # Use the band field directly for rendering
        expression = f'"{band_field}"'
        
        renderer = QgsCategorizedSymbolRenderer(expression, categories)
        layer.setRenderer(renderer)
        layer.triggerRepaint()


    def run_planner(self):
        """Open the PCI/RSI planner dialog."""
        dlg = PciRsiPlannerDialog(self.iface, self.iface.mainWindow())
        dlg.exec_()


    def run_tilt_optimizer(self):
        """Open the Tilt Optimizer dialog."""
        dlg = TiltOptimizerDialog(self.iface, self.iface.mainWindow())
        dlg.exec_()


    def run_azimuth_optimizer(self):
        """Open the Azimuth Optimizer dialog."""
        dlg = AzimuthOptimizerDialog(self.iface, self.iface.mainWindow())
        dlg.exec_()


    def run_coverage_prediction(self):
        """Open the Coverage Prediction dialog."""
        # Store as instance variable to prevent garbage collection when using show()
        self.coverage_prediction_dlg = CoveragePredictionDialog(self.iface, self.iface.mainWindow())
        self.coverage_prediction_dlg.show()  # Use show() instead of exec_() to allow hide/show cycle for extent drawing


    def run_interference_analysis(self):
        """Open the Interference Analysis dialog."""
        dlg = InterferenceAnalysisDialog(self.iface, self.iface.mainWindow())
        dlg.exec_()


    def run_vendor_import(self):
        """Open the Vendor Import/Export dialog."""
        dlg = VendorImportDialog(self.iface, self.iface.mainWindow())
        dlg.exec_()


    def run_database_connector(self):
        """Open the Database Connector dialog."""
        dlg = DatabaseConnectorDialog(self.iface, self.iface.mainWindow())
        dlg.exec_()


    def run_drive_test(self):
        """Open the Drive Test Import/Analysis dialog."""
        dlg = DriveTestDialog(self.iface, self.iface.mainWindow())
        dlg.exec_()


    def run_performance_dashboard(self):
        """Open the Network Performance Dashboard dialog."""
        dlg = PerformanceDashboardDialog(self.iface, self.iface.mainWindow())
        dlg.exec_()


    def run_about(self):
        """Open the About RF Tools dialog."""
        dlg = AboutRFToolsDialog(self.iface.mainWindow())
        dlg.exec_()
