# -*- coding: utf-8 -*-

import os
import math

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import QVariant
from qgis.core import QgsProject, QgsField, QgsVectorLayer, QgsFeature, QgsWkbTypes

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'azimuth_optimizer_dialog_base.ui'))


class AzimuthOptimizerDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, iface, parent=None):
        """Constructor."""
        super(AzimuthOptimizerDialog, self).__init__(parent)
        self.iface = iface
        self.setupUi(self)

        self.layerComboBox.currentIndexChanged.connect(self._on_layer_changed)
        self.runButton.clicked.connect(self._run_optimizer)

        self._populate_layers()
    
    def _safe_float(self, value, default=0.0):
        """Safely convert a value to float, returning default if conversion fails."""
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    def _get_point_from_geometry(self, geom):
        """Extract a point from any geometry type."""
        if geom.type() == QgsWkbTypes.PointGeometry:
            return geom.asPoint()
        else:
            # For LineString, Polygon, or other geometries, use centroid
            centroid = geom.centroid()
            return centroid.asPoint() if centroid else None

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
            self.siteIdFieldComboBox,
            self.azimuthFieldComboBox,
            self.beamwidthFieldComboBox,
            self.bandFieldComboBox,
        ]:
            combo.clear()

        self.lockedFieldComboBox.clear()
        self.lockedFieldComboBox.addItem('(None - optimize all)')

        if index < 0 or index >= len(self._layers):
            return

        layer = self._layers[index]
        fields = layer.fields()
        field_names = [f.name() for f in fields]
        for name in field_names:
            self.siteIdFieldComboBox.addItem(name)
            self.azimuthFieldComboBox.addItem(name)
            self.beamwidthFieldComboBox.addItem(name)
            self.bandFieldComboBox.addItem(name)
            self.lockedFieldComboBox.addItem(name)

    def _run_optimizer(self):
        if not self._layers:
            QtWidgets.QMessageBox.warning(self, 'Azimuth Optimizer', 'No vector layers available.')
            return

        layer_index = self.layerComboBox.currentIndex()
        if layer_index < 0 or layer_index >= len(self._layers):
            QtWidgets.QMessageBox.warning(self, 'Azimuth Optimizer', 'Please select a layer.')
            return

        layer = self._layers[layer_index]

        site_id_field = self.siteIdFieldComboBox.currentText()
        azimuth_field = self.azimuthFieldComboBox.currentText()
        beamwidth_field = self.beamwidthFieldComboBox.currentText()
        band_field = self.bandFieldComboBox.currentText()
        locked_field = self.lockedFieldComboBox.currentText()
        if locked_field == '(None - optimize all)':
            locked_field = None
        
        neighbor_distance = self.neighborDistanceSpinBox.value()
        optimization_mode = self.optimizationModeComboBox.currentText()
        output_field_name = self.outputFieldLineEdit.text().strip()

        if not output_field_name:
            QtWidgets.QMessageBox.warning(self, 'Azimuth Optimizer', 'Please provide an output field name.')
            return

        # Get field indices
        fields = layer.fields()
        site_id_idx = fields.indexFromName(site_id_field) if site_id_field else -1
        azimuth_idx = fields.indexFromName(azimuth_field) if azimuth_field else -1
        beamwidth_idx = fields.indexFromName(beamwidth_field) if beamwidth_field else -1
        band_idx = fields.indexFromName(band_field) if band_field else -1
        locked_idx = fields.indexFromName(locked_field) if locked_field else -1

        # Create new output layer with all source fields plus optimal azimuth field
        crs = layer.crs().authid()
        geom_type = layer.geometryType()
        geom_type_str = ['Point', 'LineString', 'Polygon'][geom_type]
        
        output_layer_name = f'{layer.name()}_Azimuth_Optimized'
        output_layer = QgsVectorLayer(f'{geom_type_str}?crs={crs}', output_layer_name, 'memory')
        output_provider = output_layer.dataProvider()
        
        # Add all fields from source layer
        output_provider.addAttributes(layer.fields().toList())
        
        # Add optimal azimuth field
        azimuth_field = QgsField(output_field_name, QVariant.Double)
        azimuth_field.setLength(10)
        azimuth_field.setPrecision(2)
        output_provider.addAttributes([azimuth_field])
        output_layer.updateFields()
        
        # Get field index in output layer
        output_fields = output_layer.fields()
        output_idx = output_fields.indexFromName(output_field_name)

        # Group sectors by site and band
        site_sectors = {}
        for feat in layer.getFeatures():
            geom = feat.geometry()
            if not geom or geom.isEmpty():
                continue
            
            # Extract point from geometry (handles Point, LineString, Polygon, etc.)
            point = self._get_point_from_geometry(geom)
            if point is None:
                continue
            
            site_id = str(feat[site_id_idx]) if site_id_idx != -1 else 'unknown'
            band = str(feat[band_idx]) if band_idx != -1 else 'default'
            key = f"{site_id}_{band}"
            
            if key not in site_sectors:
                site_sectors[key] = []
            
            site_sectors[key].append({
                'feature': feat,
                'point': point,
                'azimuth': self._safe_float(feat[azimuth_idx], 0.0) if azimuth_idx != -1 else 0.0,
                'beamwidth': self._safe_float(feat[beamwidth_idx], 65.0) if beamwidth_idx != -1 else 65.0,
                'locked': bool(feat[locked_idx]) if locked_idx != -1 and feat[locked_idx] is not None else False,
            })

        # Store optimal azimuth values: {feature_id: optimal_azimuth}
        azimuth_assignments = {}
        
        # Optimize azimuths
        optimized_count = 0
        for site_key, sectors in site_sectors.items():
            # Find neighboring sites
            neighbors = self._find_neighbors(sectors[0]['point'], site_sectors, site_key, neighbor_distance)
            
            # Optimize each sector at this site
            for sector in sectors:
                if sector['locked']:
                    # Keep locked azimuth
                    azimuth_assignments[sector['feature'].id()] = sector['azimuth']
                else:
                    # Calculate optimal azimuth
                    optimal_azimuth = self._calculate_optimal_azimuth(
                        sector, sectors, neighbors, optimization_mode
                    )
                    azimuth_assignments[sector['feature'].id()] = optimal_azimuth
                    optimized_count += 1

        # Create output features with optimal azimuth values
        self.progressBar.setValue(90)
        self.progressBar.setFormat("Creating output layer...")
        QtWidgets.QApplication.processEvents()
        
        output_features = []
        for feat in layer.getFeatures():
            # Create new feature with all source attributes
            new_feat = QgsFeature(output_layer.fields())
            new_feat.setGeometry(feat.geometry())
            
            # Copy all source attributes
            for field in layer.fields():
                new_feat[field.name()] = feat[field.name()]
            
            # Add optimal azimuth value
            if feat.id() in azimuth_assignments:
                new_feat[output_field_name] = round(azimuth_assignments[feat.id()], 1)
            
            output_features.append(new_feat)
        
        # Add features to output layer
        output_provider.addFeatures(output_features)
        output_layer.updateExtents()
        
        # Add output layer to project
        QgsProject.instance().addMapLayer(output_layer)
        
        self.progressBar.setValue(100)
        self.progressBar.setFormat("Complete!")
        QtWidgets.QMessageBox.information(self, 'Azimuth Optimizer', 
            f'Optimization complete!\n\n{optimized_count} sectors optimized.\n\nNew layer created: {output_layer_name}')
        self.progressBar.setVisible(False)

    def _find_neighbors(self, point, all_sites, exclude_key, max_distance_km):
        """Find neighboring sites within max distance."""
        neighbors = []
        max_distance_deg = max_distance_km / 111.0  # Rough conversion
        
        for site_key, sectors in all_sites.items():
            if site_key == exclude_key:
                continue
            
            for sector in sectors:
                dx = sector['point'].x() - point.x()
                dy = sector['point'].y() - point.y()
                distance = math.sqrt(dx*dx + dy*dy)
                
                if distance <= max_distance_deg:
                    neighbors.append({
                        'sector': sector,
                        'distance': distance,
                        'bearing': math.degrees(math.atan2(dx, dy)) % 360
                    })
        
        return neighbors

    def _calculate_optimal_azimuth(self, sector, site_sectors, neighbors, mode):
        """Calculate optimal azimuth for a sector."""
        current_azimuth = sector['azimuth']
        beamwidth = sector['beamwidth']
        
        # If this is the only sector at the site, point away from nearest neighbor
        if len(site_sectors) == 1:
            if neighbors:
                # Point away from nearest neighbor
                nearest = min(neighbors, key=lambda n: n['distance'])
                optimal = (nearest['bearing'] + 180) % 360
                return round(optimal, 1)
            else:
                # No neighbors, keep current azimuth
                return round(current_azimuth, 1)
        
        # Multi-sector site - distribute evenly and avoid neighbors
        num_sectors = len(site_sectors)
        sector_idx = site_sectors.index(sector)
        
        if mode == "Minimize Overlap":
            # Evenly distribute sectors around the site
            base_azimuth = (360.0 / num_sectors) * sector_idx
            
            # Adjust to avoid strong neighbor interference
            adjustment = self._calculate_interference_adjustment(base_azimuth, beamwidth, neighbors)
            optimal = (base_azimuth + adjustment) % 360
            
        elif mode == "Maximize Coverage":
            # Point towards coverage gaps
            base_azimuth = (360.0 / num_sectors) * sector_idx
            
            # Find coverage gaps (areas with no neighbors)
            gap_direction = self._find_coverage_gap(neighbors)
            if gap_direction is not None:
                # Bias towards gap
                optimal = (base_azimuth * 0.7 + gap_direction * 0.3) % 360
            else:
                optimal = base_azimuth
                
        else:  # Balanced
            # Balance between even distribution and neighbor avoidance
            base_azimuth = (360.0 / num_sectors) * sector_idx
            adjustment = self._calculate_interference_adjustment(base_azimuth, beamwidth, neighbors) * 0.5
            optimal = (base_azimuth + adjustment) % 360
        
        return round(optimal, 1)

    def _calculate_interference_adjustment(self, azimuth, beamwidth, neighbors):
        """Calculate azimuth adjustment to minimize interference using 3GPP antenna pattern."""
        if not neighbors:
            return 0.0
        
        # Calculate interference score for each neighbor using 3GPP pattern
        total_adjustment = 0.0
        weight_sum = 0.0
        
        for neighbor in neighbors:
            # Calculate angle difference
            angle_diff = abs(azimuth - neighbor['bearing'])
            if angle_diff > 180:
                angle_diff = 360 - angle_diff
            
            # Calculate antenna pattern loss using 3GPP standard
            # A(θ) = -min[12 * (θ/θ_3dB)², A_m]
            theta_3dB = beamwidth
            A_m = 25  # Maximum attenuation in dB
            antenna_loss = min(12 * (angle_diff / theta_3dB) ** 2, A_m)
            
            # If significant signal towards neighbor (low loss), adjust away
            if antenna_loss < 15:  # Less than 15 dB attenuation means significant signal
                # Weight by proximity and antenna pattern
                # Higher weight for closer neighbors with lower antenna loss
                weight = (1.0 / (neighbor['distance'] + 0.1)) * (1.0 - antenna_loss / 25.0)
                
                # Adjust away from neighbor
                if (neighbor['bearing'] - azimuth) % 360 < 180:
                    adjustment = -15  # Adjust counter-clockwise
                else:
                    adjustment = 15   # Adjust clockwise
                
                total_adjustment += adjustment * weight
                weight_sum += weight
        
        if weight_sum > 0:
            return total_adjustment / weight_sum
        return 0.0

    def _find_coverage_gap(self, neighbors):
        """Find the direction with least neighbor coverage."""
        if not neighbors:
            return None
        
        # Divide 360 degrees into sectors and count neighbors in each
        num_sectors = 12
        sector_size = 360.0 / num_sectors
        sector_counts = [0] * num_sectors
        
        for neighbor in neighbors:
            sector_idx = int(neighbor['bearing'] / sector_size) % num_sectors
            sector_counts[sector_idx] += 1
        
        # Find sector with minimum neighbors
        min_count = min(sector_counts)
        min_idx = sector_counts.index(min_count)
        
        # Return center of gap sector
        gap_direction = (min_idx * sector_size + sector_size / 2) % 360
        return gap_direction
