# -*- coding: utf-8 -*-

import os
import math

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import QVariant
from qgis.core import (QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, 
                       QgsPointXY, QgsField, QgsFields, QgsLineString,
                       QgsWkbTypes, QgsSymbol, QgsSingleSymbolRenderer,
                       QgsSimpleLineSymbolLayer)
from qgis.PyQt.QtGui import QColor

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'interference_analysis_dialog_base.ui'))


class InterferenceAnalysisDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, iface, parent=None):
        """Constructor."""
        super(InterferenceAnalysisDialog, self).__init__(parent)
        self.iface = iface
        self.setupUi(self)

        self.layerComboBox.currentIndexChanged.connect(self._on_layer_changed)
        self.runButton.clicked.connect(self._run_analysis)

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
            self.frequencyFieldComboBox,
            self.pciFieldComboBox,
            self.bandFieldComboBox,
            self.azimuthFieldComboBox,
            self.beamwidthFieldComboBox,
        ]:
            combo.clear()

        if index < 0 or index >= len(self._layers):
            return

        layer = self._layers[index]
        fields = layer.fields()
        field_names = [f.name() for f in fields]
        for name in field_names:
            self.frequencyFieldComboBox.addItem(name)
            self.pciFieldComboBox.addItem(name)
            self.bandFieldComboBox.addItem(name)
            self.azimuthFieldComboBox.addItem(name)
            self.beamwidthFieldComboBox.addItem(name)
            self.siteIdFieldComboBox.addItem(name)
            self.sectorFieldComboBox.addItem(name)

    def _run_analysis(self):
        if not self._layers:
            QtWidgets.QMessageBox.warning(self, 'Interference Analysis', 'No vector layers available.')
            return

        layer_index = self.layerComboBox.currentIndex()
        if layer_index < 0 or layer_index >= len(self._layers):
            QtWidgets.QMessageBox.warning(self, 'Interference Analysis', 'Please select a layer.')
            return

        layer = self._layers[layer_index]

        # Get parameters
        frequency_field = self.frequencyFieldComboBox.currentText()
        pci_field = self.pciFieldComboBox.currentText()
        band_field = self.bandFieldComboBox.currentText()
        azimuth_field = self.azimuthFieldComboBox.currentText()
        beamwidth_field = self.beamwidthFieldComboBox.currentText()
        site_id_field = self.siteIdFieldComboBox.currentText()
        sector_field = self.sectorFieldComboBox.currentText()
        
        interference_distance = self.interferenceDistanceSpinBox.value()
        overlap_threshold = self.overlapThresholdSpinBox.value()
        output_prefix = self.outputPrefixLineEdit.text().strip() or 'Interference'
        
        # Get PCI conflict detection options
        detect_pci_collision = self.pciConflictCheckBox.isChecked()
        detect_pci_mod3 = self.pciMod3CheckBox.isChecked() if hasattr(self, 'pciMod3CheckBox') else True
        detect_pci_mod6 = self.pciMod6CheckBox.isChecked() if hasattr(self, 'pciMod6CheckBox') else True

        # Get field indices
        fields = layer.fields()
        freq_idx = fields.indexFromName(frequency_field) if frequency_field else -1
        pci_idx = fields.indexFromName(pci_field) if pci_field else -1
        band_idx = fields.indexFromName(band_field) if band_field else -1
        azimuth_idx = fields.indexFromName(azimuth_field) if azimuth_field else -1
        beamwidth_idx = fields.indexFromName(beamwidth_field) if beamwidth_field else -1
        site_id_idx = fields.indexFromName(site_id_field) if site_id_field else -1
        sector_idx = fields.indexFromName(sector_field) if sector_field else -1

        # Collect sector data
        sectors = []
        for feat in layer.getFeatures():
            geom = feat.geometry()
            if not geom or geom.isEmpty():
                continue
            
            # Create sector identifier from site_id + sector + band
            site_id = str(feat[site_id_idx]) if site_id_idx != -1 and feat[site_id_idx] is not None else ''
            sector = str(feat[sector_idx]) if sector_idx != -1 and feat[sector_idx] is not None else ''
            band = str(feat[band_idx]) if band_idx != -1 and feat[band_idx] is not None else ''
            sector_id = f"{site_id}_{sector}_{band}" if site_id and sector and band else f"Sector_{feat.id()}"
            
            # Helper function to safely convert QVariant to Python type
            def safe_float(value):
                if value is None:
                    return 0
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return 0
            
            def safe_int(value):
                if value is None:
                    return -1
                try:
                    return int(value)
                except (ValueError, TypeError):
                    return -1
            
            sectors.append({
                'feature': feat,
                'point': geom.asPoint(),
                'frequency': safe_float(feat[freq_idx]) if freq_idx != -1 else 0,
                'pci': safe_int(feat[pci_idx]) if pci_idx != -1 else -1,
                'band': str(feat[band_idx]) if band_idx != -1 else 'unknown',
                'azimuth': safe_float(feat[azimuth_idx]) if azimuth_idx != -1 else 0,
                'beamwidth': safe_float(feat[beamwidth_idx]) if beamwidth_idx != -1 else 65,
                'sector_id': sector_id,
            })

        # Run analyses
        interference_issues = []
        
        if self.coChannelCheckBox.isChecked():
            co_channel = self._detect_co_channel_interference(sectors, interference_distance, overlap_threshold)
            interference_issues.extend(co_channel)
        
        if self.adjacentChannelCheckBox.isChecked():
            adjacent_channel = self._detect_adjacent_channel_interference(sectors, interference_distance, overlap_threshold)
            interference_issues.extend(adjacent_channel)
        
        if self.pciConflictCheckBox.isChecked():
            # Only pass the detection options that are checked in the UI
            detect_pci_collision = self.pciCollisionCheckBox.isChecked() if hasattr(self, 'pciCollisionCheckBox') else True
            detect_pci_mod3 = self.pciMod3CheckBox.isChecked() if hasattr(self, 'pciMod3CheckBox') else True
            detect_pci_mod6 = self.pciMod6CheckBox.isChecked() if hasattr(self, 'pciMod6CheckBox') else True
            
            pci_conflicts = self._detect_pci_conflicts(
                sectors, 
                interference_distance, 
                overlap_threshold,
                detect_pci_collision=detect_pci_collision,
                detect_pci_mod3=detect_pci_mod3,
                detect_pci_mod6=detect_pci_mod6
            )
            interference_issues.extend(pci_conflicts)

        if not interference_issues:
            QtWidgets.QMessageBox.information(self, 'Interference Analysis', 
                                            'No interference issues detected.')
            return

        # Create visualization layer
        interference_layer = self._create_interference_layer(interference_issues, output_prefix, layer.crs())
        QgsProject.instance().addMapLayer(interference_layer)

        # Generate mitigation report
        mitigation_report = self._generate_mitigation_report(interference_issues)
        
        # Show results
        QtWidgets.QMessageBox.information(self, 'Interference Analysis', 
                                        f'Analysis complete.\n\n'
                                        f'Interference distance: {interference_distance:.1f} km\n\n'
                                        f'Total interference issues: {len(interference_issues)}\n'
                                        f'- Co-channel: {sum(1 for i in interference_issues if i["type"] == "Co-Channel")}\n'
                                        f'- Adjacent channel: {sum(1 for i in interference_issues if i["type"] == "Adjacent Channel")}\n'
                                        f'- PCI conflicts: {sum(1 for i in interference_issues if i["type"] == "PCI Conflict")}\n\n'
                                        f'Visualization layer created: {output_prefix}_Issues\n\n'
                                        f'{mitigation_report}')

    def _detect_co_channel_interference(self, sectors, max_distance_km, overlap_threshold):
        """Detect co-channel interference (same frequency)."""
        issues = []
        max_distance_deg = max_distance_km / 111.0
        
        for i, sector1 in enumerate(sectors):
            for sector2 in sectors[i+1:]:
                # Same band and frequency
                if sector1['band'] != sector2['band']:
                    continue
                if abs(sector1['frequency'] - sector2['frequency']) > 0.1:
                    continue
                
                # Check distance
                dx = sector2['point'].x() - sector1['point'].x()
                dy = sector2['point'].y() - sector1['point'].y()
                distance = math.sqrt(dx*dx + dy*dy)
                
                if distance > max_distance_deg:
                    continue
                
                # Check beam overlap
                bearing = math.degrees(math.atan2(dx, dy)) % 360
                reverse_bearing = (bearing + 180) % 360
                
                overlap1 = self._calculate_beam_overlap(sector1['azimuth'], sector1['beamwidth'], bearing)
                overlap2 = self._calculate_beam_overlap(sector2['azimuth'], sector2['beamwidth'], reverse_bearing)
                
                if overlap1 > overlap_threshold or overlap2 > overlap_threshold:
                    issues.append({
                        'type': 'Co-Channel',
                        'sector1': sector1,
                        'sector2': sector2,
                        'distance_km': distance * 111.0,
                        'overlap1': overlap1,
                        'overlap2': overlap2,
                        'severity': 'High' if (overlap1 > 60 and overlap2 > 60) else 'Medium'
                    })
        
        return issues

    def _detect_adjacent_channel_interference(self, sectors, max_distance_km, overlap_threshold):
        """Detect adjacent channel interference."""
        issues = []
        max_distance_deg = max_distance_km / 111.0
        
        for i, sector1 in enumerate(sectors):
            for sector2 in sectors[i+1:]:
                # Same band, adjacent frequency
                if sector1['band'] != sector2['band']:
                    continue
                
                freq_diff = abs(sector1['frequency'] - sector2['frequency'])
                # Check if adjacent (typically 5-20 MHz spacing)
                if freq_diff < 5 or freq_diff > 20:
                    continue
                
                # Check distance (must be very close for adjacent channel interference)
                dx = sector2['point'].x() - sector1['point'].x()
                dy = sector2['point'].y() - sector1['point'].y()
                distance = math.sqrt(dx*dx + dy*dy)
                
                if distance > max_distance_deg * 0.5:  # Half the distance for adjacent channel
                    continue
                
                # Check beam overlap
                bearing = math.degrees(math.atan2(dx, dy)) % 360
                reverse_bearing = (bearing + 180) % 360
                
                overlap1 = self._calculate_beam_overlap(sector1['azimuth'], sector1['beamwidth'], bearing)
                overlap2 = self._calculate_beam_overlap(sector2['azimuth'], sector2['beamwidth'], reverse_bearing)
                
                if overlap1 > overlap_threshold or overlap2 > overlap_threshold:
                    issues.append({
                        'type': 'Adjacent Channel',
                        'sector1': sector1,
                        'sector2': sector2,
                        'distance_km': distance * 111.0,
                        'freq_diff': freq_diff,
                        'overlap1': overlap1,
                        'overlap2': overlap2,
                        'severity': 'Medium' if distance * 111.0 < 0.5 else 'Low'
                    })
        
        return issues

    def _detect_pci_conflicts(self, sectors, max_distance_km, overlap_threshold, detect_pci_collision=True, detect_pci_mod3=True, detect_pci_mod6=True):
        """Detect PCI mod 3 and mod 6 conflicts.
        
        Args:
            sectors: List of sector dictionaries
            max_distance_km: Maximum distance in km to check for conflicts
            overlap_threshold: Minimum beam overlap percentage to consider
            detect_pci_collision: Whether to detect exact PCI collisions
            detect_pci_mod3: Whether to detect mod 3 conflicts
            detect_pci_mod6: Whether to detect mod 6 conflicts
            
        Returns:
            List of detected PCI conflict issues
        """
        if not any([detect_pci_collision, detect_pci_mod3, detect_pci_mod6]):
            return []
            
        issues = []
        
        # PCI re-use distance = interference distance (user input)
        pci_reuse_distance_km = max_distance_km
        pci_reuse_distance_deg = pci_reuse_distance_km / 111.0
        
        for i, sector1 in enumerate(sectors):
            if sector1['pci'] < 0:
                continue
            
            for sector2 in sectors[i+1:]:
                if sector2['pci'] < 0:
                    continue
                
                # Same band
                if sector1['band'] != sector2['band']:
                    continue
                
                # Skip if same site-sector-band combination (duplicate features)
                if sector1['sector_id'] == sector2['sector_id']:
                    continue
                
                # Check for PCI collision (same PCI) or mod 3/6 conflict
                same_pci = (sector1['pci'] == sector2['pci'])
                pci1_mod3 = sector1['pci'] % 3
                pci2_mod3 = sector2['pci'] % 3
                pci1_mod6 = sector1['pci'] % 6
                pci2_mod6 = sector2['pci'] % 6
                
                # Skip if no conflict at all based on enabled detection types
                has_conflict = (
                    (detect_pci_collision and same_pci) or
                    (detect_pci_mod3 and not same_pci and pci1_mod3 == pci2_mod3) or
                    (detect_pci_mod6 and not same_pci and not pci1_mod3 == pci2_mod3 and pci1_mod6 == pci2_mod6)
                )
                
                if not has_conflict:
                    continue
                
                # Check distance against PCI re-use distance (not max_distance)
                dx = sector2['point'].x() - sector1['point'].x()
                dy = sector2['point'].y() - sector1['point'].y()
                distance = math.sqrt(dx*dx + dy*dy)
                
                # Only flag PCI conflicts within re-use distance
                if distance > pci_reuse_distance_deg:
                    continue
                
                # Check beam overlap
                bearing = math.degrees(math.atan2(dx, dy)) % 360
                reverse_bearing = (bearing + 180) % 360
                
                overlap1 = self._calculate_beam_overlap(sector1['azimuth'], sector1['beamwidth'], bearing)
                overlap2 = self._calculate_beam_overlap(sector2['azimuth'], sector2['beamwidth'], reverse_bearing)
                
                if overlap1 > overlap_threshold or overlap2 > overlap_threshold:
                    # Determine conflict type: collision (same PCI) is most severe
                    if same_pci:
                        conflict_type = 'collision'
                        severity = 'Critical'
                    elif pci1_mod3 == pci2_mod3:
                        conflict_type = 'mod3'
                        severity = 'High'
                    else:
                        conflict_type = 'mod6'
                        severity = 'Medium'
                    
                    issues.append({
                        'type': 'PCI Conflict',
                        'sector1': sector1,
                        'sector2': sector2,
                        'distance_km': distance * 111.0,
                        'conflict_type': conflict_type,
                        'pci1': sector1['pci'],
                        'pci2': sector2['pci'],
                        'overlap1': overlap1,
                        'overlap2': overlap2,
                        'severity': severity
                    })
        
        return issues

    def _calculate_beam_overlap(self, azimuth, beamwidth, bearing):
        """Calculate how much a bearing overlaps with a beam."""
        angle_diff = abs(azimuth - bearing)
        if angle_diff > 180:
            angle_diff = 360 - angle_diff
        
        if angle_diff <= beamwidth / 2:
            # Full overlap
            return 100.0
        elif angle_diff <= beamwidth:
            # Partial overlap
            return 100.0 * (1 - (angle_diff - beamwidth/2) / (beamwidth/2))
        else:
            return 0.0

    def _create_interference_layer(self, issues, prefix, crs):
        """Create visualization layer for interference issues."""
        layer = QgsVectorLayer(f'LineString?crs={crs.authid()}', f'{prefix}_Issues', 'memory')
        provider = layer.dataProvider()
        
        # Add fields
        fields = QgsFields()
        
        # Basic info
        type_field = QgsField('type', QVariant.String)
        type_field.setLength(50)
        fields.append(type_field)
        
        severity_field = QgsField('severity', QVariant.String)
        severity_field.setLength(20)
        fields.append(severity_field)
        
        # Source sector info
        source_field = QgsField('source_sector', QVariant.String)
        source_field.setLength(100)
        fields.append(source_field)
        
        source_site_id = QgsField('source_site_id', QVariant.String)
        source_site_id.setLength(50)
        fields.append(source_site_id)
        
        source_sector = QgsField('source_sector_id', QVariant.String)
        source_sector.setLength(50)
        fields.append(source_sector)
        
        source_band = QgsField('source_band', QVariant.String)
        source_band.setLength(20)
        fields.append(source_band)
        
        # Target sector info
        target_field = QgsField('target_sector', QVariant.String)
        target_field.setLength(100)
        fields.append(target_field)
        
        target_site_id = QgsField('target_site_id', QVariant.String)
        target_site_id.setLength(50)
        fields.append(target_site_id)
        
        target_sector = QgsField('target_sector_id', QVariant.String)
        target_sector.setLength(50)
        fields.append(target_sector)
        
        target_band = QgsField('target_band', QVariant.String)
        target_band.setLength(20)
        fields.append(target_band)
        
        # Distance and details
        distance_field = QgsField('distance_km', QVariant.Double)
        distance_field.setLength(10)
        distance_field.setPrecision(2)
        fields.append(distance_field)
        
        details_field = QgsField('details', QVariant.String)
        details_field.setLength(255)
        fields.append(details_field)
        
        provider.addAttributes(fields)
        layer.updateFields()
        
        # Add features
        features = []
        for issue in issues:
            feat = QgsFeature()
            
            # Create line between interfering sectors
            line = QgsLineString([issue['sector1']['point'], issue['sector2']['point']])
            feat.setGeometry(QgsGeometry(line))
            
            # Set attributes
            details = f"{issue['type']}"
            if issue['type'] == 'PCI Conflict':
                details += f" ({issue['conflict_type']}: {issue['pci1']} vs {issue['pci2']})"
            elif issue['type'] == 'Adjacent Channel':
                details += f" (Δf={issue['freq_diff']:.1f} MHz)"
            
            # Get sector identifiers and additional info
            source_id = issue['sector1']['sector_id']
            target_id = issue['sector2']['sector_id']
            
            # Extract site_id, sector_id, and band from sector1 and sector2
            source_parts = source_id.split('_')
            target_parts = target_id.split('_')
            
            source_site = source_parts[0] if len(source_parts) > 0 else ''
            source_sec = source_parts[1] if len(source_parts) > 1 else ''
            source_bnd = source_parts[2] if len(source_parts) > 2 else issue['sector1'].get('band', '')
            
            target_site = target_parts[0] if len(target_parts) > 0 else ''
            target_sec = target_parts[1] if len(target_parts) > 1 else ''
            target_bnd = target_parts[2] if len(target_parts) > 2 else issue['sector2'].get('band', '')
            
            feat.setAttributes([
                issue['type'],                            # type
                issue['severity'],                        # severity
                source_id,                                # source_sector
                source_site,                              # source_site_id
                source_sec,                               # source_sector_id
                source_bnd,                               # source_band
                target_id,                                # target_sector
                target_site,                              # target_site_id
                target_sec,                               # target_sector_id
                target_bnd,                               # target_band
                issue['distance_km'],                     # distance_km
                details                                   # details
            ])
            features.append(feat)
        
        provider.addFeatures(features)
        layer.updateExtents()
        
        # Apply styling
        self._style_interference_layer(layer)
        
        return layer

    def _style_interference_layer(self, layer):
        """Apply color-coded styling to interference layer based on type."""
        from qgis.core import QgsCategorizedSymbolRenderer, QgsRendererCategory
        
        # Define styles for each interference type
        categories = []
        
        # Co-Channel: Red, thick (most severe)
        symbol_co = QgsSymbol.defaultSymbol(QgsWkbTypes.LineGeometry)
        symbol_co.setWidth(2.0)
        symbol_co.setColor(QColor(220, 20, 20, 200))  # Red
        categories.append(QgsRendererCategory('Co-Channel', symbol_co, 'Co-Channel'))
        
        # PCI Conflict: Orange/Yellow based on severity
        symbol_pci = QgsSymbol.defaultSymbol(QgsWkbTypes.LineGeometry)
        symbol_pci.setWidth(1.5)
        symbol_pci.setColor(QColor(255, 140, 0, 200))  # Orange
        categories.append(QgsRendererCategory('PCI Conflict', symbol_pci, 'PCI Conflict'))
        
        # Adjacent Channel: Yellow, medium thickness
        symbol_adj = QgsSymbol.defaultSymbol(QgsWkbTypes.LineGeometry)
        symbol_adj.setWidth(1.0)
        symbol_adj.setColor(QColor(255, 200, 0, 180))  # Yellow
        categories.append(QgsRendererCategory('Adjacent Channel', symbol_adj, 'Adjacent Channel'))
        
        # Create categorized renderer
        renderer = QgsCategorizedSymbolRenderer('type', categories)
        layer.setRenderer(renderer)

    def _generate_mitigation_report(self, issues):
        """Generate mitigation suggestions."""
        report_lines = ["Mitigation Suggestions:"]
        
        if self.suggestFrequencyCheckBox.isChecked():
            co_channel_count = sum(1 for i in issues if i['type'] == 'Co-Channel')
            if co_channel_count > 0:
                report_lines.append(f"\n• Frequency Changes: {co_channel_count} co-channel issues")
                report_lines.append("  - Consider changing frequency on one sector")
                report_lines.append("  - Ensure 2+ carrier separation")
        
        if self.suggestTiltCheckBox.isChecked():
            high_overlap = sum(1 for i in issues if i.get('overlap1', 0) > 70 or i.get('overlap2', 0) > 70)
            if high_overlap > 0:
                report_lines.append(f"\n• Tilt Adjustments: {high_overlap} high overlap issues")
                report_lines.append("  - Increase downtilt to reduce coverage overlap")
                report_lines.append("  - Typical adjustment: +2 to +5 degrees")
        
        if self.suggestPciCheckBox.isChecked():
            pci_count = sum(1 for i in issues if i['type'] == 'PCI Conflict')
            if pci_count > 0:
                report_lines.append(f"\n• PCI Changes: {pci_count} PCI conflicts")
                report_lines.append("  - Change PCI to avoid mod3/mod6 conflicts")
                report_lines.append("  - Ensure neighbors have different mod3 values")
        
        return '\n'.join(report_lines) if len(report_lines) > 1 else "No specific mitigations suggested."
