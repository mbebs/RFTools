# -*- coding: utf-8 -*-

import os
import math

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import QVariant
from qgis.core import QgsProject, QgsField, QgsVectorLayer, QgsFeature, QgsWkbTypes

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'tilt_optimizer_dialog_base.ui'))


class TiltOptimizerDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, iface, parent=None):
        """Constructor."""
        super(TiltOptimizerDialog, self).__init__(parent)
        self.iface = iface
        self.setupUi(self)

        self.layerComboBox.currentIndexChanged.connect(self._on_layer_changed)
        self.runButton.clicked.connect(self._run_optimizer)
        
        # Initialize progress bar
        self.progressBar.setValue(0)

        self._populate_layers()

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
            self.vBeamwidthFieldComboBox,
            self.hBeamwidthFieldComboBox,
            self.pmaxFieldComboBox,
            self.antennaGainFieldComboBox,
            self.frequencyFieldComboBox,
        ]:
            combo.clear()

        if index < 0 or index >= len(self._layers):
            return

        layer = self._layers[index]
        fields = layer.fields()
        field_names = [f.name() for f in fields]
        for name in field_names:
            self.heightFieldComboBox.addItem(name)
            self.vBeamwidthFieldComboBox.addItem(name)
            self.hBeamwidthFieldComboBox.addItem(name)
            self.pmaxFieldComboBox.addItem(name)
            self.antennaGainFieldComboBox.addItem(name)
            self.frequencyFieldComboBox.addItem(name)

    def _run_optimizer(self):
        if not self._layers:
            QtWidgets.QMessageBox.warning(self, 'Tilt Optimizer', 'No vector layers available.')
            return

        # Show progress bar
        self.progressBar.setVisible(True)
        self.progressBar.setValue(0)
        self.progressBar.setFormat("Initializing...")
        QtWidgets.QApplication.processEvents()

        layer_index = self.layerComboBox.currentIndex()
        if layer_index < 0 or layer_index >= len(self._layers):
            QtWidgets.QMessageBox.warning(self, 'Tilt Optimizer', 'Please select a layer.')
            return

        layer = self._layers[layer_index]

        height_field = self.heightFieldComboBox.currentText()
        v_beamwidth_field = self.vBeamwidthFieldComboBox.currentText()
        h_beamwidth_field = self.hBeamwidthFieldComboBox.currentText()
        pmax_field = self.pmaxFieldComboBox.currentText()
        antenna_gain_field = self.antennaGainFieldComboBox.currentText()
        frequency_field = self.frequencyFieldComboBox.currentText()
        
        propagation_model = self.propagationModelComboBox.currentText()
        target_distance = self.targetDistanceSpinBox.value()
        output_field_name = self.outputFieldLineEdit.text().strip()

        if not output_field_name:
            QtWidgets.QMessageBox.warning(self, 'Tilt Optimizer', 'Please provide an output field name.')
            return

        # Get field indices
        fields = layer.fields()
        height_idx = fields.indexFromName(height_field) if height_field else -1
        v_beamwidth_idx = fields.indexFromName(v_beamwidth_field) if v_beamwidth_field else -1
        h_beamwidth_idx = fields.indexFromName(h_beamwidth_field) if h_beamwidth_field else -1
        pmax_idx = fields.indexFromName(pmax_field) if pmax_field else -1
        antenna_gain_idx = fields.indexFromName(antenna_gain_field) if antenna_gain_field else -1
        frequency_idx = fields.indexFromName(frequency_field) if frequency_field else -1

        # Create new output layer with all source fields plus optimal tilt field
        crs = layer.crs().authid()
        geom_type = layer.geometryType()
        geom_type_str = ['Point', 'LineString', 'Polygon'][geom_type]
        
        output_layer_name = f'{layer.name()}_Tilt_Optimized'
        output_layer = QgsVectorLayer(f'{geom_type_str}?crs={crs}', output_layer_name, 'memory')
        output_provider = output_layer.dataProvider()
        
        # Add all fields from source layer
        output_provider.addAttributes(layer.fields().toList())
        
        # Add optimal tilt field
        tilt_field = QgsField(output_field_name, QVariant.Double)
        tilt_field.setLength(10)
        tilt_field.setPrecision(2)
        output_provider.addAttributes([tilt_field])
        output_layer.updateFields()
        
        # Get field index in output layer
        output_fields = output_layer.fields()
        output_idx = output_fields.indexFromName(output_field_name)

        # Build sector list with positions for neighbor analysis
        self.progressBar.setValue(5)
        self.progressBar.setFormat("Analyzing sectors...")
        QtWidgets.QApplication.processEvents()
        
        features = list(layer.getFeatures())
        total_features = len(features)
        
        # Collect all sectors with their positions
        sectors = []
        for feat in features:
            geom = feat.geometry()
            if geom.type() == QgsWkbTypes.PointGeometry:
                point = geom.asPoint()
                sectors.append({
                    'feature': feat,
                    'point': point,
                    'height': float(feat[height_idx]) if height_idx != -1 and feat[height_idx] is not None else 30.0
                })
        
        # Calculate optimal tilt for each feature
        self.progressBar.setValue(10)
        self.progressBar.setFormat("Calculating tilts...")
        QtWidgets.QApplication.processEvents()
        
        output_features = []
        for idx, feat in enumerate(features):
            # Get parameters
            height = float(feat[height_idx]) if height_idx != -1 and feat[height_idx] is not None else 30.0
            v_beamwidth = float(feat[v_beamwidth_idx]) if v_beamwidth_idx != -1 and feat[v_beamwidth_idx] is not None else 10.0
            h_beamwidth = float(feat[h_beamwidth_idx]) if h_beamwidth_idx != -1 and feat[h_beamwidth_idx] is not None else 65.0
            pmax = float(feat[pmax_idx]) if pmax_idx != -1 and feat[pmax_idx] is not None else 43.0
            antenna_gain = float(feat[antenna_gain_idx]) if antenna_gain_idx != -1 and feat[antenna_gain_idx] is not None else 18.0
            frequency = float(feat[frequency_idx]) if frequency_idx != -1 and feat[frequency_idx] is not None else 2100.0

            # Get sector position
            geom = feat.geometry()
            if geom.type() == QgsWkbTypes.PointGeometry:
                point = geom.asPoint()
            else:
                point = None
            
            # Find neighbors for this sector
            neighbors = self._find_neighbors(point, sectors, feat.id(), target_distance * 2) if point else []
            
            # Calculate optimal tilt considering neighbors
            optimal_tilt = self._calculate_optimal_tilt(
                height, v_beamwidth, h_beamwidth, pmax, antenna_gain, frequency, 
                propagation_model, target_distance, neighbors
            )
            
            # Create new feature with all source attributes
            new_feat = QgsFeature(output_layer.fields())
            new_feat.setGeometry(feat.geometry())
            
            # Copy all source attributes
            for field in layer.fields():
                new_feat[field.name()] = feat[field.name()]
            
            # Add optimal tilt value
            new_feat[output_field_name] = round(optimal_tilt, 1)
            
            output_features.append(new_feat)
            
            # Update progress
            if idx % max(1, total_features // 20) == 0:
                progress = 10 + int((idx + 1) / total_features * 80)
                self.progressBar.setValue(progress)
                QtWidgets.QApplication.processEvents()

        # Add features to output layer
        self.progressBar.setValue(95)
        self.progressBar.setFormat("Creating output layer...")
        QtWidgets.QApplication.processEvents()
        
        output_provider.addFeatures(output_features)
        output_layer.updateExtents()
        
        # Add output layer to project
        QgsProject.instance().addMapLayer(output_layer)
        
        self.progressBar.setValue(100)
        self.progressBar.setFormat("Complete!")
        QtWidgets.QMessageBox.information(self, 'Tilt Optimizer', 
            f'Optimization complete!\n\n{total_features} features optimized.\n\nNew layer created: {output_layer_name}')
        self.progressBar.setVisible(False)

    def _calculate_optimal_tilt(self, height, v_beamwidth, h_beamwidth, pmax, 
                                antenna_gain, frequency, propagation_model, target_distance, neighbors):
        """
        Calculate optimal electrical tilt based on antenna parameters, propagation model, and neighbors.
        
        Returns: Optimal electrical tilt in degrees (positive = downtilt)
        """
        # Convert target distance from km to meters
        target_distance_m = target_distance * 1000.0
        
        # Calculate geometric tilt (angle from horizontal to target point)
        geometric_tilt = math.degrees(math.atan(height / target_distance_m))
        
        # Calculate path loss at target distance
        path_loss = self._calculate_path_loss(frequency, target_distance, height, propagation_model)
        
        # Calculate EIRP and received power at target distance
        eirp = pmax + antenna_gain
        rx_power = eirp - path_loss
        
        # Adjust tilt based on signal strength at target
        # If signal is very strong (rx_power > -70 dBm), increase tilt to limit overshoot
        # If signal is weak (rx_power < -100 dBm), reduce tilt to extend coverage
        signal_adjustment = 0.0
        if rx_power > -70:
            # Strong signal - increase tilt to reduce overshoot and interference
            signal_adjustment += 1.0
        elif rx_power < -100:
            # Weak signal - reduce tilt to extend coverage
            signal_adjustment -= 0.5
        
        # Adjust tilt based on horizontal beamwidth
        # Narrow beams (< 45°) can use higher tilt as they have less azimuthal coverage overlap
        # Wide beams (> 90°) should use lower tilt to avoid coverage gaps
        beamwidth_adjustment = 0.0
        if h_beamwidth < 45:
            # Narrow beam - can afford higher tilt
            beamwidth_adjustment += 0.5
        elif h_beamwidth > 90:
            # Wide beam (omni-like) - reduce tilt to maintain coverage
            beamwidth_adjustment -= 0.5
        
        # Adjust tilt based on neighbor density
        # If there are nearby neighbors (especially at different heights), adjust tilt
        neighbor_adjustment = 0.0
        if neighbors:
            # Calculate average neighbor distance and height difference
            avg_distance = sum(n['distance'] * 111.0 for n in neighbors) / len(neighbors)  # Convert to km
            avg_height_diff = sum(abs(n['height'] - height) for n in neighbors) / len(neighbors)
            
            # If neighbors are close, increase tilt to reduce interference
            if avg_distance < target_distance * 0.5:
                neighbor_adjustment += 1.0  # Add 1 degree for close neighbors
            
            # If neighbors are significantly higher/lower, adjust tilt
            if avg_height_diff > 10:  # More than 10m height difference
                if sum(n['height'] for n in neighbors) / len(neighbors) > height:
                    # Neighbors are higher on average - reduce tilt slightly
                    neighbor_adjustment -= 0.5
                else:
                    # Neighbors are lower - increase tilt slightly
                    neighbor_adjustment += 0.5
        
        # Calculate optimal tilt using 3GPP vertical antenna pattern
        # The 3GPP vertical pattern is: A_V(θ) = -min[12 * ((θ - θ_tilt) / θ_3dB)², SLA_v]
        # where θ_tilt is the electrical tilt, θ_3dB is vertical beamwidth, SLA_v is side lobe attenuation
        
        # For optimal coverage at target distance, we want the main beam (0 dB point) 
        # to hit the target. This means: θ_tilt = geometric_tilt
        # However, to maximize coverage area, we typically tilt slightly more to ensure
        # the 3dB point (half-power) reaches the target distance
        
        # Using 3GPP pattern: at 3dB loss, θ = θ_tilt ± θ_3dB/2
        # So optimal tilt = geometric_tilt + (v_beamwidth / 2) to put target at 3dB point
        # But this is too aggressive, so we use a factor between 1/4 and 1/2
        
        # Base tilt calculation with all adjustments
        optimal_tilt = (geometric_tilt + 
                       (v_beamwidth / 3.0) + 
                       signal_adjustment + 
                       beamwidth_adjustment + 
                       neighbor_adjustment)
        
        # Clamp tilt to reasonable values (0-15 degrees typical for macro cells)
        optimal_tilt = max(0.0, min(15.0, optimal_tilt))
        
        return round(optimal_tilt, 1)
    
    def _find_neighbors(self, point, all_sectors, exclude_id, max_distance_km):
        """Find neighboring sectors within max distance."""
        if not point:
            return []
        
        neighbors = []
        max_distance_deg = max_distance_km / 111.0  # Rough conversion
        
        for sector in all_sectors:
            if sector['feature'].id() == exclude_id:
                continue
            
            dx = sector['point'].x() - point.x()
            dy = sector['point'].y() - point.y()
            distance = math.sqrt(dx*dx + dy*dy)
            
            if distance <= max_distance_deg and distance > 0:
                neighbors.append({
                    'distance': distance,
                    'height': sector['height']
                })
        
        return neighbors

    def _calculate_path_loss(self, frequency_mhz, distance_km, height_m, model):
        """
        Calculate path loss using selected propagation model.
        
        Args:
            frequency_mhz: Frequency in MHz
            distance_km: Distance in kilometers
            height_m: Antenna height in meters
            model: Propagation model name
            
        Returns: Path loss in dB
        """
        if model == "Free Space Path Loss":
            # FSPL = 20*log10(d) + 20*log10(f) + 32.45
            # where d is in km and f is in MHz
            fspl = 20 * math.log10(distance_km) + 20 * math.log10(frequency_mhz) + 32.45
            return fspl
            
        elif model == "Okumura-Hata (Urban)":
            # Okumura-Hata model for urban areas
            # Valid for: 150-1500 MHz, 1-20 km, 30-200m BS height
            a_hm = (1.1 * math.log10(frequency_mhz) - 0.7) * 1.5 - (1.56 * math.log10(frequency_mhz) - 0.8)
            path_loss = (69.55 + 26.16 * math.log10(frequency_mhz) - 13.82 * math.log10(height_m) - a_hm +
                        (44.9 - 6.55 * math.log10(height_m)) * math.log10(distance_km))
            return path_loss
            
        elif model == "Okumura-Hata (Suburban)":
            # Okumura-Hata model for suburban areas
            urban_loss = (69.55 + 26.16 * math.log10(frequency_mhz) - 13.82 * math.log10(height_m) +
                         (44.9 - 6.55 * math.log10(height_m)) * math.log10(distance_km))
            suburban_correction = 2 * (math.log10(frequency_mhz / 28.0)) ** 2 + 5.4
            path_loss = urban_loss - suburban_correction
            return path_loss
            
        elif model == "COST-231 Hata":
            # COST-231 Hata extension (for 1500-2000 MHz)
            a_hm = (1.1 * math.log10(frequency_mhz) - 0.7) * 1.5 - (1.56 * math.log10(frequency_mhz) - 0.8)
            C_m = 3  # Urban correction factor
            path_loss = (46.3 + 33.9 * math.log10(frequency_mhz) - 13.82 * math.log10(height_m) - a_hm +
                        (44.9 - 6.55 * math.log10(height_m)) * math.log10(distance_km) + C_m)
            return path_loss
        
        else:
            # Default to Free Space Path Loss
            fspl = 20 * math.log10(distance_km) + 20 * math.log10(frequency_mhz) + 32.45
            return fspl
