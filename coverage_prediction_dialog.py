# -*- coding: utf-8 -*-

import os
import math
import numpy as np
import requests
import json

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor
from qgis.core import (QgsProject, QgsVectorLayer, QgsRasterLayer, 
                       QgsRasterFileWriter, QgsRasterPipe, QgsRasterShader,
                       QgsColorRampShader, QgsSingleBandPseudoColorRenderer,
                       QgsPointXY, QgsRectangle, QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform)
from qgis.gui import QgsMapToolExtent
from osgeo import gdal, osr
import tempfile

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'coverage_prediction_dialog_base.ui'))

# Clutter loss values in dB based on land use type
CLUTTER_LOSSES = {
    'water': 0,
    'forest': 10,
    'wood': 10,
    'grass': 3,
    'meadow': 3,
    'farmland': 4,
    'residential': 12,
    'commercial': 18,
    'industrial': 20,
    'retail': 18,
    'default': 5
}


class CoveragePredictionDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, iface, parent=None):
        """Constructor."""
        super(CoveragePredictionDialog, self).__init__(parent)
        self.iface = iface
        self.setupUi(self)
        
        # Set window flags to keep dialog on top but allow interaction with main window
        from qgis.PyQt.QtCore import Qt
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint)
        
        self.custom_extent = None
        self.extent_tool = None
        self._drawing_extent = False  # Flag to track if we're drawing
        self.elevation_cache = {}  # Cache for elevation data

        self.layerComboBox.currentIndexChanged.connect(self._on_layer_changed)
        self.bandFieldComboBox.currentIndexChanged.connect(self._on_band_field_changed)
        self.generateButton.clicked.connect(self._run_prediction)
        
        # Check if there's a draw button (new UI) or radio button (old UI)
        if hasattr(self, 'drawExtentButton'):
            self.drawExtentButton.clicked.connect(self._draw_custom_extent)
        elif hasattr(self, 'useCustomExtentRadio'):
            self.useCustomExtentRadio.toggled.connect(self._on_extent_mode_changed)
        
        # Initialize progress bar
        self.progressBar.setValue(0)
        
        # Initialize extent info label
        if hasattr(self, 'extentInfoLabel'):
            self.extentInfoLabel.setText('')

        self._populate_layers()
    
    def _draw_custom_extent(self):
        """Start drawing custom extent on map."""
        reply = QtWidgets.QMessageBox.information(
            self, 'Draw Extent',
            'The dialog will close temporarily.\n\n'
            'Click and drag on the map to draw a rectangle.\n\n'
            'The dialog will reopen when you finish drawing.',
            QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel
        )
        
        if reply == QtWidgets.QMessageBox.Cancel:
            return
        
        # Set drawing flag
        self._drawing_extent = True
        
        # Close dialog temporarily to allow map interaction
        self.hide()
        
        # Create extent tool and connect to canvas
        self.extent_tool = QgsMapToolExtent(self.iface.mapCanvas())
        self._temp_extent = None
        
        # Store extent as it changes and use timer to capture final one
        from qgis.PyQt.QtCore import QTimer
        self._extent_timer = QTimer()
        self._extent_timer.setSingleShot(True)
        self._extent_timer.timeout.connect(self._check_extent)
        
        # Store extent and restart timer on each change
        def on_extent_changed(extent):
            self._temp_extent = extent
            self._extent_timer.start(500)
        
        self.extent_tool.extentChanged.connect(on_extent_changed)
        self.iface.mapCanvas().setMapTool(self.extent_tool)
    
    def _check_extent(self):
        """Check if extent tool has a valid extent after user stops dragging."""
        if self._temp_extent and not self._temp_extent.isEmpty():
            self._extent_captured(self._temp_extent)
            self._temp_extent = None
    
    def _on_extent_mode_changed(self, checked):
        """Handle extent mode change (for old radio button UI)."""
        if checked:
            self._draw_custom_extent()
        else:
            # Use map extent - clean up any active drawing
            self.custom_extent = None
            if self.extent_tool:
                self.iface.mapCanvas().unsetMapTool(self.extent_tool)
                self.extent_tool = None
            if hasattr(self, '_extent_timer') and self._extent_timer:
                self._extent_timer.stop()
                self._extent_timer = None
            # Clear extent info label
            if hasattr(self, 'extentInfoLabel'):
                self.extentInfoLabel.setText('')
            # Make sure dialog is visible if it was hidden
            if not self.isVisible():
                self.show()
    
    def _extent_captured(self, extent):
        """Capture the drawn extent."""
        if not extent or extent.isEmpty():
            return
            
        self.custom_extent = extent
        
        # Clean up timer
        if hasattr(self, '_extent_timer'):
            self._extent_timer.stop()
            self._extent_timer = None
        
        # Disconnect and clean up tool
        if self.extent_tool:
            try:
                self.extent_tool.extentChanged.disconnect()
            except:
                pass
            self.iface.mapCanvas().unsetMapTool(self.extent_tool)
            self.extent_tool = None
        
        # Clear drawing flag
        self._drawing_extent = False
        
        # Update UI to show custom extent is active
        if hasattr(self, 'useCustomExtentRadio'):
            self.useCustomExtentRadio.setChecked(True)
        
        # Update extent info label with captured coordinates
        if hasattr(self, 'extentInfoLabel'):
            extent_text = (
                f"Custom Area: {extent.width():.4f}° × {extent.height():.4f}°\n"
                f"({extent.xMinimum():.4f}, {extent.yMinimum():.4f}) to "
                f"({extent.xMaximum():.4f}, {extent.yMaximum():.4f})"
            )
            self.extentInfoLabel.setText(extent_text)
        
        # Show dialog again
        self.show()
        self.raise_()
        self.activateWindow()
        
        # Process events to ensure dialog is fully shown
        QtWidgets.QApplication.processEvents()
        
        # Show confirmation using QGIS message bar instead of dialog
        # This avoids the issue with message box closing the parent dialog
        from qgis.core import Qgis
        self.iface.messageBar().pushMessage(
            "Extent Captured",
            f"Custom area defined: {extent.width():.4f}° × {extent.height():.4f}°. Click Generate to create prediction.",
            level=Qgis.Success,
            duration=5
        )

    def _populate_layers(self):
        self.layerComboBox.clear()
        self._layers = []
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsVectorLayer):
                self.layerComboBox.addItem(layer.name())
                self._layers.append(layer)

        if self._layers:
            self._on_layer_changed(0)

    def _on_layer_changed(self, index):
        for combo in [
            self.heightFieldComboBox,
            self.azimuthFieldComboBox,
            self.beamwidthFieldComboBox,
            self.powerFieldComboBox,
            self.gainFieldComboBox,
            self.frequencyFieldComboBox,
            self.bandFieldComboBox,
        ]:
            combo.clear()
        
        # Clear band filter
        self.bandFilterComboBox.clear()

        if index < 0 or index >= len(self._layers):
            return

        layer = self._layers[index]
        fields = layer.fields()
        field_names = [f.name() for f in fields]
        for name in field_names:
            self.heightFieldComboBox.addItem(name)
            self.azimuthFieldComboBox.addItem(name)
            self.beamwidthFieldComboBox.addItem(name)
            self.powerFieldComboBox.addItem(name)
            self.gainFieldComboBox.addItem(name)
            self.frequencyFieldComboBox.addItem(name)
            self.bandFieldComboBox.addItem(name)
    
    def _on_band_field_changed(self, index):
        """Update band filter when band field selection changes."""
        layer_index = self.layerComboBox.currentIndex()
        if layer_index < 0 or layer_index >= len(self._layers):
            return
        
        layer = self._layers[layer_index]
        self._populate_band_filter(layer)
    
    def _populate_band_filter(self, layer):
        """Populate band filter dropdown with unique band values from the layer."""
        # Clear existing items first
        self.bandFilterComboBox.clear()
        
        # Add "All Bands" option first
        self.bandFilterComboBox.addItem("All Bands", None)
        
        # Get the band field name
        band_field = self.bandFieldComboBox.currentText()
        if not band_field:
            return
        
        # Get unique band values from the layer
        band_idx = layer.fields().indexFromName(band_field)
        if band_idx == -1:
            return
        
        unique_bands = set()
        for feature in layer.getFeatures():
            band_value = feature[band_idx]
            if band_value is not None and band_value != '':
                unique_bands.add(str(band_value))
        
        # Add unique bands to dropdown (sorted)
        for band in sorted(unique_bands):
            self.bandFilterComboBox.addItem(band, band)

    def _run_prediction(self):
        if not self._layers:
            QtWidgets.QMessageBox.warning(self, 'Coverage Prediction', 'No vector layers available.')
            return

        layer_index = self.layerComboBox.currentIndex()
        if layer_index < 0 or layer_index >= len(self._layers):
            QtWidgets.QMessageBox.warning(self, 'Coverage Prediction', 'Please select a layer.')
            return

        layer = self._layers[layer_index]

        # Get parameters
        height_field = self.heightFieldComboBox.currentText()
        azimuth_field = self.azimuthFieldComboBox.currentText()
        beamwidth_field = self.beamwidthFieldComboBox.currentText()
        power_field = self.powerFieldComboBox.currentText()
        gain_field = self.gainFieldComboBox.currentText()
        frequency_field = self.frequencyFieldComboBox.currentText()
        band_field = self.bandFieldComboBox.currentText()
        
        # Get band filter value from combobox (use currentData to get the actual value, not display text)
        band_filter = self.bandFilterComboBox.currentData()
        if band_filter is None:  # "All Bands" selected
            band_filter = ''
        
        propagation_model = self.propagationModelComboBox.currentText()
        max_distance_km = self.maxDistanceSpinBox.value()
        resolution_m = self.resolutionSpinBox.value()
        output_name = self.outputNameLineEdit.text().strip() or 'Coverage_Prediction'
        use_clutter = self.useClutterCheckBox.isChecked()
        use_terrain = self.useTerrainCheckBox.isChecked()
        
        # Add band to output name
        if band_filter:
            output_name = f"{output_name}_{band_filter}"
        else:
            output_name = f"{output_name}_All_Bands"
        
        # Get extent
        if self.useCustomExtentRadio.isChecked():
            if not self.custom_extent:
                QtWidgets.QMessageBox.warning(self, 'Coverage Prediction', 
                                            'Please draw a custom extent on the map first.')
                return
            extent = self.custom_extent
        else:
            # Use current map extent
            extent = self.iface.mapCanvas().extent()

        # Show progress
        progress = QtWidgets.QProgressDialog("Generating coverage prediction...", "Cancel", 0, 100, self)
        progress.setWindowModality(2)  # Qt.WindowModal
        progress.show()

        try:
            # Calculate coverage
            raster_layer = self._generate_coverage_raster(
                layer, height_field, azimuth_field, beamwidth_field,
                power_field, gain_field, frequency_field, band_field, band_filter,
                propagation_model, max_distance_km, resolution_m,
                output_name, extent, use_clutter, use_terrain, progress
            )

            if raster_layer:
                QgsProject.instance().addMapLayer(raster_layer)
                
                # Show completion message with styling tip
                msg = f'Coverage prediction complete: {output_name}\n\n'
                msg += 'Tip: You can customize the color ramp and RSRP thresholds by:\n'
                msg += '1. Right-click the layer → Properties → Symbology\n'
                msg += '2. Adjust color stops and values as needed'
                
                QtWidgets.QMessageBox.information(self, 'Coverage Prediction', msg)
            else:
                QtWidgets.QMessageBox.warning(self, 'Coverage Prediction', 
                                            'Failed to generate coverage prediction.')
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Coverage Prediction', 
                                         f'Error: {str(e)}')
        finally:
            progress.close()

    def _generate_coverage_raster(self, layer, height_field, azimuth_field, beamwidth_field,
                                  power_field, gain_field, frequency_field, band_field, band_filter,
                                  model, max_dist_km, resolution_m, output_name, extent, use_clutter, use_terrain, progress):
        """Generate coverage prediction raster."""
        
        # Transform extent to WGS84 (EPSG:4326) if needed
        canvas_crs = self.iface.mapCanvas().mapSettings().destinationCrs()
        wgs84_crs = QgsCoordinateReferenceSystem("EPSG:4326")
        
        if canvas_crs != wgs84_crs:
            transform = QgsCoordinateTransform(canvas_crs, wgs84_crs, QgsProject.instance())
            extent = transform.transformBoundingBox(extent)
        
        # Query OSM data for clutter if enabled
        clutter_data = None
        if use_clutter:
            progress.setLabelText("Querying OpenStreetMap for clutter data...")
            progress.setValue(5)
            clutter_data = self._query_osm_clutter(extent)
            if clutter_data:
                progress.setLabelText("Processing clutter data...")
                progress.setValue(10)
        
        # Calculate raster dimensions first
        resolution_deg = resolution_m / 111000.0  # Convert meters to degrees
        cols = int((extent.width()) / resolution_deg)
        rows = int((extent.height()) / resolution_deg)
        
        # Limit raster size for performance
        max_size = 2000
        if cols > max_size or rows > max_size:
            scale = max(cols / max_size, rows / max_size)
            cols = int(cols / scale)
            rows = int(rows / scale)
            resolution_deg *= scale
        
        # Query elevation data for terrain if enabled (after dimension calculation)
        elevation_grid = None
        if use_terrain:
            progress.setLabelText("Querying elevation data (SRTM)...")
            progress.setValue(8 if not use_clutter else 12)
            elevation_grid = self._get_elevation_grid(extent, resolution_deg, rows, cols)
            if elevation_grid is not None:
                progress.setLabelText("Processing terrain data...")
                progress.setValue(15)
        
        # Initialize raster array with very low signal (-140 dBm)
        raster_data = np.full((rows, cols), -140.0, dtype=np.float32)
        
        # Get field indices
        fields = layer.fields()
        height_idx = fields.indexFromName(height_field) if height_field else -1
        azimuth_idx = fields.indexFromName(azimuth_field) if azimuth_field else -1
        beamwidth_idx = fields.indexFromName(beamwidth_field) if beamwidth_field else -1
        power_idx = fields.indexFromName(power_field) if power_field else -1
        gain_idx = fields.indexFromName(gain_field) if gain_field else -1
        frequency_idx = fields.indexFromName(frequency_field) if frequency_field else -1
        band_idx = fields.indexFromName(band_field) if band_field else -1
        
        # Process each site (filter by band if specified)
        features = list(layer.getFeatures())
        if band_filter and band_idx != -1:
            features = [f for f in features if str(f[band_idx]) == band_filter]
            if not features:
                QtWidgets.QMessageBox.warning(None, 'Coverage Prediction', 
                                            f'No features found with band = "{band_filter}"')
                return None
        
        for feat_idx, feat in enumerate(features):
            if progress.wasCanceled():
                return None
            
            progress.setValue(int(50 * feat_idx / len(features)))
            
            geom = feat.geometry()
            if not geom or geom.isEmpty():
                continue
            
            site_point = geom.asPoint()
            
            # Get parameters
            try:
                height = float(feat[height_idx]) if height_idx != -1 and feat[height_idx] is not None else 30.0
                azimuth = float(feat[azimuth_idx]) if azimuth_idx != -1 and feat[azimuth_idx] is not None else 0.0
                beamwidth = float(feat[beamwidth_idx]) if beamwidth_idx != -1 and feat[beamwidth_idx] is not None else 65.0
                power = float(feat[power_idx]) if power_idx != -1 and feat[power_idx] is not None else 43.0
                gain = float(feat[gain_idx]) if gain_idx != -1 and feat[gain_idx] is not None else 18.0
                frequency = float(feat[frequency_idx]) if frequency_idx != -1 and feat[frequency_idx] is not None else 2100.0
            except (ValueError, TypeError):
                continue
            
            # Calculate coverage for this site
            self._calculate_site_coverage(
                raster_data, extent, resolution_deg, rows, cols,
                site_point, height, azimuth, beamwidth, power, gain, frequency,
                model, max_dist_km, clutter_data, elevation_grid
            )
        
        progress.setValue(75)
        
        # Create temporary GeoTIFF file with unique name to avoid permission issues
        import time
        temp_dir = tempfile.gettempdir()
        timestamp = int(time.time() * 1000)  # milliseconds
        output_file = os.path.join(temp_dir, f'{output_name}_{timestamp}.tif')
        
        # Write raster
        driver = gdal.GetDriverByName('GTiff')
        out_raster = driver.Create(output_file, cols, rows, 1, gdal.GDT_Float32)
        
        # Set geotransform
        geotransform = (
            extent.xMinimum(),
            resolution_deg,
            0,
            extent.yMaximum(),
            0,
            -resolution_deg
        )
        out_raster.SetGeoTransform(geotransform)
        
        # Set projection (WGS84)
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(4326)
        out_raster.SetProjection(srs.ExportToWkt())
        
        # Write data
        out_band = out_raster.GetRasterBand(1)
        out_band.WriteArray(raster_data)
        out_band.SetNoDataValue(-140)
        
        # Calculate and set statistics for proper rendering
        stats = out_band.ComputeStatistics(False)
        out_band.FlushCache()
        
        out_raster = None  # Close file
        
        progress.setValue(90)
        
        # Load raster layer
        raster_layer = QgsRasterLayer(output_file, output_name)
        
        if raster_layer.isValid():
            # Apply color ramp
            self._apply_color_ramp(raster_layer)
            # Refresh layer
            raster_layer.triggerRepaint()
        
        progress.setValue(100)
        
        return raster_layer if raster_layer.isValid() else None
    
    def _calculate_site_coverage(self, raster_data, extent, resolution_deg, rows, cols,
                                 site_point, height, azimuth, beamwidth, power, gain, frequency,
                                 model, max_dist_km, clutter_data=None, elevation_grid=None):
        """Calculate coverage contribution from one site using vectorized operations."""
        
        # Create coordinate grids (vectorized)
        x_coords = extent.xMinimum() + (np.arange(cols) + 0.5) * resolution_deg
        y_coords = extent.yMaximum() - (np.arange(rows) + 0.5) * resolution_deg
        
        # Create meshgrid
        xx, yy = np.meshgrid(x_coords, y_coords)
        
        # Calculate clutter loss grid if clutter data available
        clutter_loss_grid = None
        if clutter_data:
            clutter_loss_grid = self._calculate_clutter_loss_grid(xx, yy, clutter_data)
        
        # Calculate terrain loss grid if elevation data available
        terrain_loss_grid = None
        if elevation_grid is not None:
            terrain_loss_grid = self._calculate_terrain_loss_grid(
                xx, yy, elevation_grid, site_point, height, frequency
            )
        
        # Calculate distances (vectorized)
        dx = xx - site_point.x()
        dy = yy - site_point.y()
        distance_deg = np.sqrt(dx*dx + dy*dy)
        distance_km = distance_deg * 111.0
        
        # Create mask for valid distances
        valid_mask = (distance_km <= max_dist_km) & (distance_km >= 0.001)
        
        # Only process valid pixels
        if not np.any(valid_mask):
            return
        
        # Calculate bearings (vectorized)
        bearings = np.degrees(np.arctan2(dx, dy))
        bearings[bearings < 0] += 360
        
        # Calculate angle differences from azimuth
        angle_diff = np.abs(bearings - azimuth)
        angle_diff = np.where(angle_diff > 180, 360 - angle_diff, angle_diff)
        
        # Calculate antenna pattern loss using 3GPP/ITU standard horizontal pattern (vectorized)
        # A(θ) = -min[12 * (θ/θ_3dB)^2, A_m]
        # where θ_3dB is the 3dB beamwidth and A_m is the maximum attenuation (typically 20-30 dB)
        theta_3dB = beamwidth
        A_m = 25  # Maximum attenuation in dB (front-to-back ratio)
        
        # Standard 3GPP horizontal pattern
        antenna_pattern_loss = np.minimum(
            12 * (angle_diff / theta_3dB) ** 2,
            A_m
        )
        
        # Calculate path loss for all valid pixels
        path_loss = np.zeros_like(distance_km)
        valid_distances = distance_km[valid_mask]
        
        if model == "Free Space Path Loss":
            path_loss[valid_mask] = 20 * np.log10(valid_distances) + 20 * np.log10(frequency) + 32.45
        elif model == "Okumura-Hata (Urban)":
            a_hm = (1.1 * np.log10(frequency) - 0.7) * 1.5 - (1.56 * np.log10(frequency) - 0.8)
            path_loss[valid_mask] = (69.55 + 26.16 * np.log10(frequency) - 13.82 * np.log10(height) - a_hm +
                                     (44.9 - 6.55 * np.log10(height)) * np.log10(valid_distances))
        elif model == "COST-231 Hata":
            a_hm = (1.1 * np.log10(frequency) - 0.7) * 1.5 - (1.56 * np.log10(frequency) - 0.8)
            path_loss[valid_mask] = (46.3 + 33.9 * np.log10(frequency) - 13.82 * np.log10(height) - a_hm +
                                     (44.9 - 6.55 * np.log10(height)) * np.log10(valid_distances) + 3)
        else:  # Ericsson 9999
            path_loss[valid_mask] = (36.2 + 30.2 * np.log10(frequency) + 12 * np.log10(height) +
                                     (43.2 - 3.1 * np.log10(height)) * np.log10(valid_distances))
        
        # Calculate RSRP (vectorized)
        rsrp = power + gain - antenna_pattern_loss - path_loss
        
        # Apply clutter loss if available
        if clutter_loss_grid is not None:
            rsrp = rsrp - clutter_loss_grid
        
        # Apply terrain loss if available
        if terrain_loss_grid is not None:
            rsrp = rsrp - terrain_loss_grid
        
        # Apply valid mask (set invalid pixels to -140 dBm)
        rsrp = np.where(valid_mask, rsrp, -140)
        
        # Update raster with best signal only (maximum RSRP across all sites)
        # This ensures overlapping coverage uses the strongest signal
        raster_data[:] = np.maximum(raster_data, rsrp)
    
    def _calculate_path_loss(self, frequency_mhz, distance_km, height_m, model):
        """Calculate path loss using selected propagation model."""
        
        if distance_km < 0.001:
            return 0
        
        if model == "Free Space Path Loss":
            fspl = 20 * math.log10(distance_km) + 20 * math.log10(frequency_mhz) + 32.45
            return fspl
            
        elif model == "Okumura-Hata (Urban)":
            a_hm = (1.1 * math.log10(frequency_mhz) - 0.7) * 1.5 - (1.56 * math.log10(frequency_mhz) - 0.8)
            path_loss = (69.55 + 26.16 * math.log10(frequency_mhz) - 13.82 * math.log10(height_m) - a_hm +
                        (44.9 - 6.55 * math.log10(height_m)) * math.log10(distance_km))
            return path_loss
            
        elif model == "Okumura-Hata (Suburban)":
            urban_loss = (69.55 + 26.16 * math.log10(frequency_mhz) - 13.82 * math.log10(height_m) +
                         (44.9 - 6.55 * math.log10(height_m)) * math.log10(distance_km))
            suburban_correction = 2 * (math.log10(frequency_mhz / 28.0)) ** 2 + 5.4
            path_loss = urban_loss - suburban_correction
            return path_loss
            
        elif model == "Okumura-Hata (Rural)":
            urban_loss = (69.55 + 26.16 * math.log10(frequency_mhz) - 13.82 * math.log10(height_m) +
                         (44.9 - 6.55 * math.log10(height_m)) * math.log10(distance_km))
            rural_correction = 4.78 * (math.log10(frequency_mhz)) ** 2 - 18.33 * math.log10(frequency_mhz) + 40.94
            path_loss = urban_loss - rural_correction
            return path_loss
            
        elif model == "COST-231 Hata (Urban)" or model == "COST-231 Hata":
            a_hm = (1.1 * math.log10(frequency_mhz) - 0.7) * 1.5 - (1.56 * math.log10(frequency_mhz) - 0.8)
            C_m = 3  # Urban
            path_loss = (46.3 + 33.9 * math.log10(frequency_mhz) - 13.82 * math.log10(height_m) - a_hm +
                        (44.9 - 6.55 * math.log10(height_m)) * math.log10(distance_km) + C_m)
            return path_loss
            
        elif model == "COST-231 Hata (Suburban)":
            a_hm = (1.1 * math.log10(frequency_mhz) - 0.7) * 1.5 - (1.56 * math.log10(frequency_mhz) - 0.8)
            C_m = 0  # Suburban
            path_loss = (46.3 + 33.9 * math.log10(frequency_mhz) - 13.82 * math.log10(height_m) - a_hm +
                        (44.9 - 6.55 * math.log10(height_m)) * math.log10(distance_km) + C_m)
            return path_loss
            
        elif model == "Ericsson 9999":
            # Ericsson 9999 model (empirical model for urban/suburban)
            a0 = 36.2
            a1 = 30.2
            a2 = 12.0
            a3 = 0.1
            path_loss = (a0 + a1 * math.log10(distance_km) + a2 * math.log10(frequency_mhz) + 
                        a3 * math.log10(height_m) * math.log10(distance_km) - 
                        3.2 * (math.log10(11.75 * 1.5)) ** 2)
            return path_loss
            
        elif model == "SUI (Suburban)":
            # Stanford University Interim (SUI) model - Terrain Type B (Suburban)
            d0 = 0.1  # Reference distance in km
            A = 20 * math.log10(4 * math.pi * d0 * 1000 * frequency_mhz / 300)
            gamma = 4.0  # Path loss exponent for suburban (Terrain B)
            Xf = 6 * math.log10(frequency_mhz / 2000)  # Frequency correction
            Xh = -10.8 * math.log10(1.5 / 2)  # Height correction for 1.5m mobile
            s = 8.2  # Shadowing std deviation
            path_loss = A + 10 * gamma * math.log10(distance_km / d0) + Xf + Xh
            return path_loss
            
        elif model == "SUI (Urban)":
            # Stanford University Interim (SUI) model - Terrain Type C (Urban)
            d0 = 0.1  # Reference distance in km
            A = 20 * math.log10(4 * math.pi * d0 * 1000 * frequency_mhz / 300)
            gamma = 4.6  # Path loss exponent for urban (Terrain C)
            Xf = 6 * math.log10(frequency_mhz / 2000)  # Frequency correction
            Xh = -10.8 * math.log10(1.5 / 2)  # Height correction for 1.5m mobile
            path_loss = A + 10 * gamma * math.log10(distance_km / d0) + Xf + Xh
            return path_loss
            
        elif model == "ECC-33 (Urban)":
            # ECC-33 model (CEPT) for urban areas
            path_loss = (69.55 + 26.16 * math.log10(frequency_mhz) - 13.82 * math.log10(height_m) +
                        (44.9 - 6.55 * math.log10(height_m)) * math.log10(distance_km))
            return path_loss
            
        elif model == "ECC-33 (Suburban)":
            # ECC-33 model (CEPT) for suburban areas
            urban_loss = (69.55 + 26.16 * math.log10(frequency_mhz) - 13.82 * math.log10(height_m) +
                         (44.9 - 6.55 * math.log10(height_m)) * math.log10(distance_km))
            suburban_correction = 2 * (math.log10(frequency_mhz / 28.0)) ** 2 + 5.4
            path_loss = urban_loss - suburban_correction
            return path_loss
        
        else:
            # Default to Free Space Path Loss
            fspl = 20 * math.log10(distance_km) + 20 * math.log10(frequency_mhz) + 32.45
            return fspl
    
    def _apply_color_ramp(self, raster_layer):
        """Apply color ramp to raster layer for signal strength visualization."""
        
        # Get data provider
        provider = raster_layer.dataProvider()
        
        # Define color ramp for RSRP values
        color_ramp_items = [
            QgsColorRampShader.ColorRampItem(-140, QColor(0, 0, 0, 0), '-140 dBm (No Signal)'),
            QgsColorRampShader.ColorRampItem(-120, QColor(139, 0, 0), '-120 dBm (Very Poor)'),
            QgsColorRampShader.ColorRampItem(-110, QColor(255, 0, 0), '-110 dBm (Poor)'),
            QgsColorRampShader.ColorRampItem(-100, QColor(255, 165, 0), '-100 dBm (Fair)'),
            QgsColorRampShader.ColorRampItem(-90, QColor(255, 255, 0), '-90 dBm (Good)'),
            QgsColorRampShader.ColorRampItem(-80, QColor(144, 238, 144), '-80 dBm (Very Good)'),
            QgsColorRampShader.ColorRampItem(-70, QColor(0, 255, 0), '-70 dBm (Excellent)'),
        ]
        
        # Create shader
        shader = QgsRasterShader()
        color_ramp_shader = QgsColorRampShader()
        color_ramp_shader.setColorRampType(QgsColorRampShader.Interpolated)
        color_ramp_shader.setColorRampItemList(color_ramp_items)
        shader.setRasterShaderFunction(color_ramp_shader)
        
        # Create renderer
        renderer = QgsSingleBandPseudoColorRenderer(provider, 1, shader)
        raster_layer.setRenderer(renderer)
        
        # Refresh the layer
        raster_layer.reload()
        raster_layer.triggerRepaint()
    
    def _query_osm_clutter(self, extent):
        """Query OpenStreetMap Overpass API for buildings and land use data."""
        try:
            # Overpass API endpoint
            overpass_url = "http://overpass-api.de/api/interpreter"
            
            # Build Overpass QL query for buildings and landuse
            query = f"""
            [out:json][timeout:25];
            (
              way["building"]({extent.yMinimum()},{extent.xMinimum()},{extent.yMaximum()},{extent.xMaximum()});
              way["landuse"]({extent.yMinimum()},{extent.xMinimum()},{extent.yMaximum()},{extent.xMaximum()});
              way["natural"]({extent.yMinimum()},{extent.xMinimum()},{extent.yMaximum()},{extent.xMaximum()});
            );
            out geom;
            """
            
            # Query API
            response = requests.post(overpass_url, data={'data': query}, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                return self._process_osm_data(data, extent)
            else:
                self.iface.messageBar().pushWarning('Coverage Prediction', 
                    f'OSM query failed (status {response.status_code}). Continuing without clutter data.')
                return None
                
        except requests.exceptions.Timeout:
            self.iface.messageBar().pushWarning('Coverage Prediction', 
                'OSM query timeout. Continuing without clutter data.')
            return None
        except Exception as e:
            self.iface.messageBar().pushWarning('Coverage Prediction', 
                f'OSM query error: {str(e)}. Continuing without clutter data.')
            return None
    
    def _process_osm_data(self, osm_data, extent):
        """Process OSM data into a usable format for clutter loss calculation."""
        clutter_features = []
        
        for element in osm_data.get('elements', []):
            if element['type'] != 'way':
                continue
            
            tags = element.get('tags', {})
            geometry = element.get('geometry', [])
            
            if not geometry:
                continue
            
            # Determine clutter type
            clutter_type = None
            
            if 'building' in tags:
                # Building density will be calculated separately
                clutter_type = 'building'
            elif 'landuse' in tags:
                landuse = tags['landuse']
                if landuse in CLUTTER_LOSSES:
                    clutter_type = landuse
            elif 'natural' in tags:
                natural = tags['natural']
                if natural in CLUTTER_LOSSES:
                    clutter_type = natural
            
            if clutter_type:
                # Extract coordinates
                coords = [(node['lon'], node['lat']) for node in geometry]
                clutter_features.append({
                    'type': clutter_type,
                    'coords': coords
                })
        
        return clutter_features
    
    def _calculate_clutter_loss_grid(self, xx, yy, clutter_data):
        """Calculate clutter loss for each pixel in the grid."""
        # Initialize with default loss
        clutter_loss = np.full_like(xx, CLUTTER_LOSSES['default'])
        
        # Calculate building density in grid cells
        building_density = np.zeros_like(xx)
        
        for feature in clutter_data:
            if feature['type'] == 'building':
                # Count buildings in each grid cell
                for lon, lat in feature['coords']:
                    # Find nearest grid cell
                    col_idx = np.argmin(np.abs(xx[0, :] - lon))
                    row_idx = np.argmin(np.abs(yy[:, 0] - lat))
                    if 0 <= row_idx < xx.shape[0] and 0 <= col_idx < xx.shape[1]:
                        building_density[row_idx, col_idx] += 1
            else:
                # Apply land use loss
                loss_value = CLUTTER_LOSSES.get(feature['type'], CLUTTER_LOSSES['default'])
                for lon, lat in feature['coords']:
                    col_idx = np.argmin(np.abs(xx[0, :] - lon))
                    row_idx = np.argmin(np.abs(yy[:, 0] - lat))
                    if 0 <= row_idx < xx.shape[0] and 0 <= col_idx < xx.shape[1]:
                        clutter_loss[row_idx, col_idx] = max(clutter_loss[row_idx, col_idx], loss_value)
        
        # Apply building density loss (additional loss based on density)
        # High density: +20 dB, Medium: +12 dB, Low: +5 dB
        building_loss = np.where(building_density > 10, 20,
                        np.where(building_density > 5, 12,
                        np.where(building_density > 0, 5, 0)))
        
        # Combine land use and building losses
        total_clutter_loss = clutter_loss + building_loss
        
        return total_clutter_loss
    
    def _get_elevation_grid(self, extent, resolution_deg, target_rows, target_cols):
        """Get elevation grid for entire extent with caching and interpolation."""
        # Check cache first
        cache_key = f"{extent.xMinimum():.6f}_{extent.yMinimum():.6f}_{extent.xMaximum():.6f}_{extent.yMaximum():.6f}_{target_rows}_{target_cols}"
        if cache_key in self.elevation_cache:
            return self.elevation_cache[cache_key]
        
        try:
            # Sample at coarser resolution for API efficiency (every ~250m)
            sample_resolution = max(resolution_deg * 5, 0.002)  # At least 0.002 degrees (~220m)
            
            # Create sample grid
            sample_lats = np.arange(extent.yMinimum(), extent.yMaximum() + sample_resolution, sample_resolution)
            sample_lons = np.arange(extent.xMinimum(), extent.xMaximum() + sample_resolution, sample_resolution)
            
            # Limit to reasonable number of samples
            if len(sample_lats) * len(sample_lons) > 400:
                # Reduce resolution if too many points
                factor = np.sqrt((len(sample_lats) * len(sample_lons)) / 400)
                sample_resolution *= factor
                sample_lats = np.arange(extent.yMinimum(), extent.yMaximum() + sample_resolution, sample_resolution)
                sample_lons = np.arange(extent.xMinimum(), extent.xMaximum() + sample_resolution, sample_resolution)
            
            # Query elevation API in batches
            elevations = self._batch_query_elevation(sample_lats, sample_lons)
            
            if elevations is None:
                return None
            
            # Interpolate to full resolution grid with exact dimensions
            elevation_grid = self._interpolate_elevation_grid(
                elevations, sample_lats, sample_lons, extent, target_rows, target_cols
            )
            
            # Cache result
            self.elevation_cache[cache_key] = elevation_grid
            
            return elevation_grid
            
        except Exception as e:
            self.iface.messageBar().pushWarning('Coverage Prediction', 
                f'Elevation query error: {str(e)}. Continuing without terrain data.')
            return None
    
    def _batch_query_elevation(self, sample_lats, sample_lons):
        """Query elevation API for a grid of points."""
        try:
            # Use Open-Elevation API
            api_url = "https://api.open-elevation.com/api/v1/lookup"
            
            # Create location list
            locations = []
            for lat in sample_lats:
                for lon in sample_lons:
                    locations.append({"latitude": float(lat), "longitude": float(lon)})
            
            # Query API (batch request)
            response = requests.post(
                api_url,
                json={'locations': locations},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                
                # Extract elevations into 2D array
                elevations = np.array([r['elevation'] for r in results])
                elevations = elevations.reshape(len(sample_lats), len(sample_lons))
                
                return elevations
            else:
                self.iface.messageBar().pushWarning('Coverage Prediction', 
                    f'Elevation API returned status {response.status_code}. Continuing without terrain data.')
                return None
                
        except requests.exceptions.Timeout:
            self.iface.messageBar().pushWarning('Coverage Prediction', 
                'Elevation API timeout. Continuing without terrain data.')
            return None
        except Exception as e:
            self.iface.messageBar().pushWarning('Coverage Prediction', 
                f'Elevation API error: {str(e)}. Continuing without terrain data.')
            return None
    
    def _interpolate_elevation_grid(self, elevations, sample_lats, sample_lons, extent, target_rows, target_cols):
        """Interpolate coarse elevation samples to full resolution grid."""
        from scipy.interpolate import RectBivariateSpline
        
        # Create full resolution grid with exact dimensions
        full_lats = np.linspace(extent.yMinimum(), extent.yMaximum(), target_rows)
        full_lons = np.linspace(extent.xMinimum(), extent.xMaximum(), target_cols)
        
        # Use bivariate spline interpolation
        try:
            interpolator = RectBivariateSpline(sample_lats, sample_lons, elevations, kx=1, ky=1)
            elevation_grid = interpolator(full_lats, full_lons)
            return elevation_grid
        except:
            # Fallback to simple linear interpolation if scipy not available
            return self._simple_interpolate(elevations, sample_lats, sample_lons, full_lats, full_lons)
    
    def _simple_interpolate(self, elevations, sample_lats, sample_lons, full_lats, full_lons):
        """Simple bilinear interpolation fallback."""
        elevation_grid = np.zeros((len(full_lats), len(full_lons)))
        
        for i, lat in enumerate(full_lats):
            for j, lon in enumerate(full_lons):
                # Find nearest sample points
                lat_idx = np.searchsorted(sample_lats, lat)
                lon_idx = np.searchsorted(sample_lons, lon)
                
                # Clamp to valid range
                lat_idx = max(1, min(lat_idx, len(sample_lats) - 1))
                lon_idx = max(1, min(lon_idx, len(sample_lons) - 1))
                
                # Simple average of 4 nearest points
                elevation_grid[i, j] = np.mean([
                    elevations[lat_idx-1, lon_idx-1],
                    elevations[lat_idx-1, lon_idx],
                    elevations[lat_idx, lon_idx-1],
                    elevations[lat_idx, lon_idx]
                ])
        
        return elevation_grid
    
    def _calculate_terrain_loss_grid(self, xx, yy, elevation_grid, site_point, site_height, frequency_mhz):
        """Calculate terrain diffraction loss for all pixels using knife-edge diffraction."""
        # Get site elevation (interpolate from grid)
        site_row = np.argmin(np.abs(yy[:, 0] - site_point.y()))
        site_col = np.argmin(np.abs(xx[0, :] - site_point.x()))
        site_elevation = elevation_grid[site_row, site_col] if 0 <= site_row < elevation_grid.shape[0] and 0 <= site_col < elevation_grid.shape[1] else 0
        
        # Calculate distances from site
        dx = xx - site_point.x()
        dy = yy - site_point.y()
        distance_deg = np.sqrt(dx*dx + dy*dy)
        distance_km = distance_deg * 111.0
        
        # Avoid division by zero
        distance_km = np.maximum(distance_km, 0.001)
        
        # Calculate line-of-sight elevation at each pixel
        # Simplified: assume linear path from site to pixel
        site_agl = site_elevation + site_height  # Site antenna height above ground level
        target_agl = elevation_grid + 1.5  # Assume 1.5m receiver height
        
        # Calculate elevation angle from site to target
        elevation_diff = target_agl - site_agl
        distance_m = distance_km * 1000
        
        # Line of sight angle (radians)
        los_angle = np.arctan2(elevation_diff, distance_m)
        
        # Calculate Fresnel zone radius at midpoint
        # F1 = sqrt(lambda * d1 * d2 / (d1 + d2))
        # For simplification, use d1 = d2 = distance/2
        wavelength = 3e8 / (frequency_mhz * 1e6)  # meters
        fresnel_radius = np.sqrt(wavelength * distance_m / 4)  # meters
        
        # Calculate clearance (simplified)
        # Positive clearance = clear path, negative = obstruction
        midpoint_elevation = (site_agl + target_agl) / 2
        midpoint_row = (site_row + np.clip(np.round((yy - site_point.y()) / (yy[1, 0] - yy[0, 0]) + site_row).astype(int), 0, elevation_grid.shape[0] - 1))
        midpoint_col = (site_col + np.clip(np.round((xx - site_point.x()) / (xx[0, 1] - xx[0, 0]) + site_col).astype(int), 0, elevation_grid.shape[1] - 1))
        
        # Simplified terrain clearance (using target elevation as proxy for obstacles)
        # In reality, would need to sample along path
        terrain_clearance = target_agl - midpoint_elevation
        
        # Calculate Fresnel clearance parameter
        # v = h * sqrt(2 * (d1 + d2) / (lambda * d1 * d2))
        # Simplified: v = clearance / fresnel_radius
        v = terrain_clearance / np.maximum(fresnel_radius, 0.1)
        
        # Knife-edge diffraction loss (ITU-R P.526)
        # For v > -0.78: Loss = 6.9 + 20*log10(sqrt((v-0.1)^2 + 1) + v - 0.1)
        # For v <= -0.78: Loss = 0 (no obstruction)
        
        diffraction_loss = np.zeros_like(v)
        
        # Calculate loss where there's obstruction (v < 0)
        obstructed = v < -0.78
        diffraction_loss[obstructed] = 6.9 + 20 * np.log10(
            np.sqrt((v[obstructed] - 0.1)**2 + 1) + v[obstructed] - 0.1
        )
        
        # Clamp to reasonable values (0 to 40 dB)
        diffraction_loss = np.clip(diffraction_loss, 0, 40)
        
        return diffraction_loss
