# -*- coding: utf-8 -*-

import os
import math
from qgis.PyQt import uic
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import QVariant
from qgis.core import QgsProject, QgsField, QgsVectorLayer, QgsDistanceArea, QgsCoordinateReferenceSystem, QgsVectorDataProvider, QgsFeature, QgsWkbTypes, QgsPointXY

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'pci_rsi_planner_dialog_base.ui'))


class PciRsiPlannerDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, iface, parent=None):
        """Constructor."""
        super(PciRsiPlannerDialog, self).__init__(parent)
        self.iface = iface
        self.setupUi(self)

        self.layerComboBox.currentIndexChanged.connect(self._on_layer_changed)
        self.runButton.clicked.connect(self._run_planner)
        
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
            self.techFieldComboBox,
            self.siteIdFieldComboBox,
            self.cellIdFieldComboBox,
            self.bandFieldComboBox,
            self.earfcnFieldComboBox,
            self.lockedFieldComboBox,
            self.existingPciFieldComboBox,
            self.existingRsiFieldComboBox,
        ]:
            combo.clear()

        if index < 0 or index >= len(self._layers):
            return

        layer = self._layers[index]
        fields = layer.fields()
        field_names = [f.name() for f in fields]
        
        # Add field names to required combo boxes
        for name in field_names:
            self.techFieldComboBox.addItem(name)
            self.siteIdFieldComboBox.addItem(name)
            self.cellIdFieldComboBox.addItem(name)
            self.bandFieldComboBox.addItem(name)
            self.earfcnFieldComboBox.addItem(name)
        
        # Add (None) option first for optional fields
        self.lockedFieldComboBox.addItem('(None)')
        for name in field_names:
            self.lockedFieldComboBox.addItem(name)
            
        for name in field_names:
            self.existingPciFieldComboBox.addItem(name)
            self.existingRsiFieldComboBox.addItem(name)
        
        # Add cell range field (optional) - check if UI element exists
        if hasattr(self, 'cellRangeFieldComboBox'):
            self.cellRangeFieldComboBox.clear()
            self.cellRangeFieldComboBox.addItem('(Use Auto-Calculated)')
            for name in field_names:
                self.cellRangeFieldComboBox.addItem(name)

    def _calculate_rsi_count(self, cell_range_km, ncs_config=13, prach_format=0):
        """
        Calculate the number of RSIs needed for a cell based on cell range and PRACH format.
        Based on 3GPP TS 36.211 - PRACH preamble format and Ncs configuration.
        
        Parameters:
        - cell_range_km: Cell range in kilometers
        - ncs_config: Cyclic shift configuration index (0-15)
                      Default: 13 (unrestricted set, suitable for most deployments)
        - prach_format: PRACH preamble format (0-4)
                       0: FDD 1.4ms (most common)
                       1: FDD 2ms
                       2: FDD 2ms (short sequence)
                       3: FDD 3ms
                       4: TDD 1.6ms
        
        The calculation is based on:
        - 3GPP TS 36.211 Table 5.7.2-2
        - Number of root sequences required for given cell range and Ncs
        - "Not High Speed" scenario (≤120km/h)
        """
        import math
        
        # 3GPP TS 36.211 Table: Max Cell Range and RSIs Needed per Ncs Configuration
        # Format: {ncs_index: (Ncs_value, max_cell_range_km, rsi_count_at_max_range)}
        # This table shows the max supportable cell range and how many RSIs are needed
        
        ncs_table = {
            # Index: (Ncs_value, Max_Range_km, RSI_count_needed)
            0:  (0,   118.93, 64),   # Ncs=0:   max 118.93 km, needs 64 RSIs
            1:  (13,  0.79,   1),    # Ncs=13:  max 0.79 km, needs 1 RSI
            2:  (15,  1.08,   2),    # Ncs=15:  max 1.08 km, needs 2 RSIs
            3:  (18,  1.51,   2),    # Ncs=18:  max 1.51 km, needs 2 RSIs
            4:  (22,  2.08,   2),    # Ncs=22:  max 2.08 km, needs 2 RSIs
            5:  (26,  2.65,   2),    # Ncs=26:  max 2.65 km, needs 2 RSIs
            6:  (32,  3.51,   3),    # Ncs=32:  max 3.51 km, needs 3 RSIs
            7:  (38,  4.37,   3),    # Ncs=38:  max 4.37 km, needs 3 RSIs
            8:  (46,  5.51,   4),    # Ncs=46:  max 5.51 km, needs 4 RSIs
            9:  (59,  7.37,   5),    # Ncs=59:  max 7.37 km, needs 5 RSIs
            10: (76,  9.80,   6),    # Ncs=76:  max 9.80 km, needs 6 RSIs
            11: (93,  12.23,  8),    # Ncs=93:  max 12.23 km, needs 8 RSIs
            12: (119, 15.95,  10),   # Ncs=119: max 15.95 km, needs 10 RSIs
            13: (167, 22.82,  13),   # Ncs=167: max 22.82 km, needs 13 RSIs (unrestricted, common)
            14: (279, 38.84,  22),   # Ncs=279: max 38.84 km, needs 22 RSIs
            15: (419, 58.86,  32),   # Ncs=419: max 58.86 km, needs 32 RSIs (unrestricted, long range)
        }
        
        # Get parameters for the given Ncs configuration
        if ncs_config not in ncs_table:
            ncs_config = 13  # Default to unrestricted set (Ncs=167)
        
        ncs_value, max_range, max_rsi_count = ncs_table[ncs_config]
        
        # Apply PRACH format multipliers to max range
        # Different formats have different durations and guard times
        format_multipliers = {
            0: 1.0,    # Format 0: 1.4ms (baseline, FDD)
            1: 1.15,   # Format 1: 2ms (longer, FDD)
            2: 0.85,   # Format 2: 2ms short sequence (FDD)
            3: 1.3,    # Format 3: 3ms (longest, FDD)
            4: 0.95,   # Format 4: 1.6ms (TDD, sequence length 139)
        }
        
        multiplier = format_multipliers.get(prach_format, 1.0)
        adjusted_max_range = max_range * multiplier
        
        # Calculate RSIs needed based on the ratio to max range
        # If cell_range <= adjusted_max_range: use the table's RSI count
        # If cell_range > adjusted_max_range: scale proportionally (shouldn't happen in practice)
        if cell_range_km <= adjusted_max_range:
            # Linear interpolation: RSI count scales with range
            # At max range, need max_rsi_count; at 0 km, need 1 RSI
            rsi_ratio = cell_range_km / adjusted_max_range
            num_rsi = max(1, math.ceil(rsi_ratio * max_rsi_count))
        else:
            # Cell range exceeds max for this Ncs - would need different config
            # Return max RSI count for this Ncs (conservative)
            num_rsi = max_rsi_count
        
        # Cap at 3GPP maximum (64 root sequences available)
        return min(num_rsi, 64)
    
    def _run_planner(self):
        if not self._layers:
            QtWidgets.QMessageBox.warning(self, 'PCI/RSI Planner', 'No vector layers available.')
            return

        layer_index = self.layerComboBox.currentIndex()
        if layer_index < 0 or layer_index >= len(self._layers):
            QtWidgets.QMessageBox.warning(self, 'PCI/RSI Planner', 'Please select a layer.')
            return

        # Show progress bar
        self.progressBar.setVisible(True)
        self.progressBar.setValue(0)
        QtWidgets.QApplication.processEvents()

        layer = self._layers[layer_index]

        tech_field_name = self.techFieldComboBox.currentText()
        site_field_name = self.siteIdFieldComboBox.currentText()
        cell_field_name = self.cellIdFieldComboBox.currentText()
        band_field_name = self.bandFieldComboBox.currentText()
        earfcn_field_name = self.earfcnFieldComboBox.currentText()
        locked_field_name = self.lockedFieldComboBox.currentText()
        # Handle optional locked field
        if locked_field_name == '(None)':
            locked_field_name = None
        existing_pci_field_name = self.existingPciFieldComboBox.currentText()
        existing_rsi_field_name = self.existingRsiFieldComboBox.currentText()
        
        # Get cell range field if available
        cell_range_field_name = None
        if hasattr(self, 'cellRangeFieldComboBox'):
            cell_range_field_name = self.cellRangeFieldComboBox.currentText()
            if cell_range_field_name == '(Use Auto-Calculated)':
                cell_range_field_name = None

        pci_plan_field_name = self.pciPlanFieldLineEdit.text().strip()
        rsi_plan_field_name = self.rsiPlanFieldLineEdit.text().strip()

        if not pci_plan_field_name or not rsi_plan_field_name:
            QtWidgets.QMessageBox.warning(self, 'PCI/RSI Planner', 'Please provide names for PCI and RSI plan fields.')
            return

        # Get existing field indexes before editing
        fields = layer.fields()
        locked_idx = fields.indexFromName(locked_field_name) if locked_field_name else -1
        existing_pci_idx = fields.indexFromName(existing_pci_field_name) if existing_pci_field_name else -1
        existing_rsi_idx = fields.indexFromName(existing_rsi_field_name) if existing_rsi_field_name else -1
        tech_idx = fields.indexFromName(tech_field_name) if tech_field_name else -1
        band_idx = fields.indexFromName(band_field_name) if band_field_name else -1
        cell_range_idx = fields.indexFromName(cell_range_field_name) if cell_range_field_name else -1

        if band_idx == -1:
            QtWidgets.QMessageBox.warning(self, 'PCI/RSI Planner', 'Band field is required.')
            return

        # Create new output layer with all source fields plus PCI/RSI plan fields
        crs = layer.crs().authid()
        geom_type = layer.geometryType()
        geom_type_str = ['Point', 'LineString', 'Polygon'][geom_type]
        
        output_layer_name = f'{layer.name()}_PCI_RSI_Plan'
        output_layer = QgsVectorLayer(f'{geom_type_str}?crs={crs}', output_layer_name, 'memory')
        output_provider = output_layer.dataProvider()
        
        # Add all fields from source layer
        output_provider.addAttributes(layer.fields().toList())
        
        # Add PCI and RSI plan fields
        pci_field = QgsField(pci_plan_field_name, QVariant.Int)
        pci_field.setLength(10)
        rsi_field = QgsField(rsi_plan_field_name, QVariant.Int)
        rsi_field.setLength(10)
        rsi_count_field = QgsField('RSI_COUNT', QVariant.Int)
        rsi_count_field.setLength(10)
        output_provider.addAttributes([pci_field, rsi_field, rsi_count_field])
        output_layer.updateFields()
        
        # Get field indexes in output layer
        output_fields = output_layer.fields()
        pci_plan_idx = output_fields.indexFromName(pci_plan_field_name)
        rsi_plan_idx = output_fields.indexFromName(rsi_plan_field_name)

        # Read user-configured ranges and options
        plan_pci = self.planPciCheckBox.isChecked()
        plan_rsi = self.planRsiCheckBox.isChecked()
        pci_min = self.pciMinSpinBox.value()
        pci_max = self.pciMaxSpinBox.value()
        rsi_min = self.rsiMinSpinBox.value()
        rsi_max = self.rsiMaxSpinBox.value()
        reuse_distance_km = self.reuseDistanceSpinBox.value()
        check_pci_mod = self.pciModCheckBox.isChecked()
        
        # Get PRACH format selection (if UI element exists)
        prach_format = 0  # Default to Format 0 (FDD)
        if hasattr(self, 'prachFormatComboBox'):
            prach_format = self.prachFormatComboBox.currentIndex()

        # Validate user selections
        if not plan_pci and not plan_rsi:
            QtWidgets.QMessageBox.warning(self, 'PCI/RSI Planner', 'Please select at least one planning option (PCI or RSI).')
            return

        if plan_pci and pci_min > pci_max:
            QtWidgets.QMessageBox.warning(self, 'PCI/RSI Planner', 'Invalid PCI range (min must be <= max).')
            return
        
        if plan_rsi and rsi_min > rsi_max:
            QtWidgets.QMessageBox.warning(self, 'PCI/RSI Planner', 'Invalid RSI range (min must be <= max).')
            return
        
        # Setup distance calculator
        distance_calc = QgsDistanceArea()
        distance_calc.setSourceCrs(layer.crs(), QgsProject.instance().transformContext())
        distance_calc.setEllipsoid('WGS84')

        # Group features per (tech, band)
        self.progressBar.setValue(10)
        self.progressBar.setFormat("Grouping features...")
        QtWidgets.QApplication.processEvents()
        
        groups = {}
        for feat in layer.getFeatures():
            tech_val = feat[tech_idx] if tech_idx != -1 else 'LTE/NR'
            band_val = feat[band_idx] if band_idx != -1 else None
            # Handle None values for band
            if band_val is None:
                band_val = 'Unknown'
            key = (str(tech_val), str(band_val))
            groups.setdefault(key, []).append(feat)

        # Dictionary to store PCI/RSI assignments: {feature_id: (pci, rsi, rsi_count)}
        assignments = {}
        
        # Assign PCI/RSI
        self.progressBar.setValue(30)
        self.progressBar.setFormat("Assigning PCI...")
        QtWidgets.QApplication.processEvents()
        
        total_groups = len(groups)
        for group_idx, ((tech_val, band_val), feats) in enumerate(groups.items()):
            used_pcis = set()
            used_rsis = set()
            next_pci = pci_min  # Track next PCI to try for this group
            next_rsi = rsi_min  # Track next RSI to try for this group

            # First pass: respect locked cells
            for feat in feats:
                # Check if cell is locked (handle various truthy values)
                is_locked = False
                if locked_idx != -1:
                    locked_val = feat[locked_idx]
                    # Handle different types: bool, int (0/1), string ('true'/'false', '0'/'1')
                    if isinstance(locked_val, bool):
                        is_locked = locked_val
                    elif isinstance(locked_val, (int, float)):
                        is_locked = bool(locked_val)
                    elif isinstance(locked_val, str):
                        is_locked = locked_val.lower() in ('true', '1', 'yes', 'locked')
                
                if is_locked:
                    pci_val = None
                    rsi_val = None
                    rsi_count = None
                    if plan_pci and existing_pci_idx != -1 and feat[existing_pci_idx] is not None:
                        try:
                            pci_val = int(float(feat[existing_pci_idx]))  # Convert via float first to handle string numbers
                            used_pcis.add(pci_val)
                        except (ValueError, TypeError):
                            # Skip invalid PCI values
                            pass
                    if plan_rsi and existing_rsi_idx != -1 and feat[existing_rsi_idx] is not None:
                        try:
                            rsi_val = int(float(feat[existing_rsi_idx]))  # Convert via float first to handle string numbers
                            used_rsis.add(rsi_val)
                            # For locked cells, we don't know the RSI count, so leave as None
                        except (ValueError, TypeError):
                            # Skip invalid RSI values
                            pass
                    assignments[feat.id()] = (pci_val, rsi_val, rsi_count)

            # Second pass: assign new values to unlocked cells with reuse distance and mod checking
            # Build a map of feature ID to geometry for distance calculations
            # Handle different geometry types - use centroid for non-point geometries
            feat_geom_map = {}
            for f in feats:
                geom = f.geometry()
                if geom and not geom.isEmpty():
                    try:
                        # Check if it's a point geometry
                        if geom.type() == QgsWkbTypes.PointGeometry:
                            point = geom.asPoint()
                            feat_geom_map[f.id()] = QgsPointXY(point)
                        else:
                            # For non-point geometries, use centroid
                            centroid = geom.centroid()
                            if not centroid.isEmpty():
                                point = centroid.asPoint()
                                feat_geom_map[f.id()] = QgsPointXY(point)
                    except Exception:
                        # Skip features with invalid geometries
                        continue
            # Track PCI assignments: {feat_id: pci}
            pci_assignments = {}
            # Build spatial index for faster neighbor lookups: {pci: [list of points with that pci]}
            pci_spatial_index = {}
            
            for f in feats:
                # Check if cell is locked (handle various truthy values)
                is_f_locked = False
                if locked_idx != -1:
                    locked_val = f[locked_idx]
                    if isinstance(locked_val, bool):
                        is_f_locked = locked_val
                    elif isinstance(locked_val, (int, float)):
                        is_f_locked = bool(locked_val)
                    elif isinstance(locked_val, str):
                        is_f_locked = locked_val.lower() in ('true', '1', 'yes', 'locked')
                
                if is_f_locked and existing_pci_idx != -1 and f[existing_pci_idx] is not None:
                    try:
                        pci_val = int(float(f[existing_pci_idx]))  # Convert via float first to handle string numbers
                        pci_assignments[f.id()] = pci_val
                        # Add to spatial index
                        if pci_val not in pci_spatial_index:
                            pci_spatial_index[pci_val] = []
                        if f.id() in feat_geom_map:
                            pci_spatial_index[pci_val].append((f.id(), feat_geom_map[f.id()]))
                    except (ValueError, TypeError):
                        # Skip invalid PCI values
                        pass
            
            # PHASE 1: Assign PCI if requested (complete all PCIs first)
            if plan_pci:
                for feat in feats:
                    # Check if cell is locked (handle various truthy values)
                    is_locked = False
                    if locked_idx != -1:
                        locked_val = feat[locked_idx]
                        if isinstance(locked_val, bool):
                            is_locked = locked_val
                        elif isinstance(locked_val, (int, float)):
                            is_locked = bool(locked_val)
                        elif isinstance(locked_val, str):
                            is_locked = locked_val.lower() in ('true', '1', 'yes', 'locked')
                    
                    if is_locked:
                        continue
                    
                    # Skip features without valid geometry (they won't participate in distance checks anyway)
                    has_valid_geom = feat.id() in feat_geom_map

                    # Find a suitable PCI considering reuse distance and mod 3/6 conflicts
                    candidate_pci = next_pci  # Start from last assigned PCI
                    assigned = False
                    attempts = 0
                    max_attempts = pci_max - pci_min + 1
                    
                    while not assigned and attempts < max_attempts:
                        if candidate_pci in used_pcis:
                            candidate_pci += 1
                            if candidate_pci > pci_max:
                                candidate_pci = pci_min
                            attempts += 1
                            continue
                        
                        # Check reuse distance - only check cells with same PCI (much faster!)
                        reuse_ok = True
                        if has_valid_geom and candidate_pci in pci_spatial_index:
                            feat_point = feat_geom_map[feat.id()]
                            # Only check cells that have the same candidate_pci
                            for other_id, other_point in pci_spatial_index[candidate_pci]:
                                dist_m = distance_calc.measureLine(feat_point, other_point)
                                dist_km = dist_m / 1000.0
                                if dist_km < reuse_distance_km:
                                    reuse_ok = False
                                    break
                        
                        # Check PCI mod 3/6 conflicts with nearby cells
                        mod_ok = True
                        if check_pci_mod and has_valid_geom:
                            feat_point = feat_geom_map[feat.id()]
                            candidate_mod3 = candidate_pci % 3
                            candidate_mod6 = candidate_pci % 6
                            
                            # Check all already-assigned PCIs for mod conflicts
                            for other_pci in pci_spatial_index.keys():
                                other_mod3 = other_pci % 3
                                other_mod6 = other_pci % 6
                                
                                # Check if there's a potential mod conflict
                                has_mod3_conflict = (candidate_mod3 == other_mod3)
                                has_mod6_conflict = (candidate_mod6 == other_mod6)
                                
                                # Skip if no mod conflict possible
                                if not has_mod3_conflict and not has_mod6_conflict:
                                    continue
                                
                                # Check distance to cells with this PCI
                                for other_id, other_point in pci_spatial_index[other_pci]:
                                    dist_m = distance_calc.measureLine(feat_point, other_point)
                                    dist_km = dist_m / 1000.0
                                    
                                    # Mod 3 conflict: avoid within 2x reuse distance
                                    if has_mod3_conflict and dist_km < (reuse_distance_km * 2):
                                        mod_ok = False
                                        break
                                    
                                    # Mod 6 conflict: stricter, avoid within reuse distance
                                    if has_mod6_conflict and dist_km < reuse_distance_km:
                                        mod_ok = False
                                        break
                                
                                if not mod_ok:
                                    break
                        
                        if reuse_ok and mod_ok:
                            used_pcis.add(candidate_pci)
                            pci_assignments[feat.id()] = candidate_pci
                            # Add to spatial index for future checks
                            if candidate_pci not in pci_spatial_index:
                                pci_spatial_index[candidate_pci] = []
                            if has_valid_geom:
                                pci_spatial_index[candidate_pci].append((feat.id(), feat_geom_map[feat.id()]))
                            # Store assignment
                            current_assignment = assignments.get(feat.id(), (None, None, None))
                            assignments[feat.id()] = (candidate_pci, current_assignment[1], current_assignment[2])
                            assigned = True
                            # Update next_pci for next feature
                            next_pci = candidate_pci + 1
                            if next_pci > pci_max:
                                next_pci = pci_min
                        else:
                            candidate_pci += 1
                            if candidate_pci > pci_max:
                                candidate_pci = pci_min
                            attempts += 1
                    
                    # If no suitable PCI found after all attempts, assign the next available (fallback)
                    if not assigned:
                        fallback_pci = next_pci
                        # Limit attempts to avoid infinite loop
                        fallback_attempts = 0
                        max_fallback_attempts = pci_max - pci_min + 1
                        
                        while fallback_pci in used_pcis and fallback_attempts < max_fallback_attempts:
                            fallback_pci += 1
                            if fallback_pci > pci_max:
                                fallback_pci = pci_min
                            fallback_attempts += 1
                        
                        # If we still can't find an unused PCI, reuse one (all PCIs exhausted)
                        if fallback_pci in used_pcis:
                            # Just use the next sequential PCI even if it's used
                            fallback_pci = next_pci
                        
                        used_pcis.add(fallback_pci)
                        pci_assignments[fallback_pci] = fallback_pci
                        # Add to spatial index
                        if fallback_pci not in pci_spatial_index:
                            pci_spatial_index[fallback_pci] = []
                        if has_valid_geom:
                            pci_spatial_index[fallback_pci].append((feat.id(), feat_geom_map[feat.id()]))
                        # Store assignment
                        current_assignment = assignments.get(feat.id(), (None, None, None))
                        assignments[feat.id()] = (fallback_pci, current_assignment[1], current_assignment[2])
                        # Update next_pci
                        next_pci = fallback_pci + 1
                        if next_pci > pci_max:
                            next_pci = pci_min

            # PHASE 2: Assign RSI if requested (after all PCIs are complete)
            if plan_rsi:
                # Build spatial index for RSI ranges: {rsi_start: [list of (feat_id, point, rsi_count)]}
                rsi_spatial_index = {}
                
                # For RSI, use similar reuse distance as PCI (can be slightly smaller)
                # RSI reuse distance is typically 0.5-0.7x of PCI reuse distance
                rsi_reuse_distance_km = reuse_distance_km * 0.6
                
                # Default cell range estimation (if no field provided)
                # Assume reuse distance is roughly 2-3x cell range for good planning
                default_cell_range_km = reuse_distance_km / 2.5
                
                for feat in feats:
                    # Check if cell is locked (handle various truthy values)
                    is_locked = False
                    if locked_idx != -1:
                        locked_val = feat[locked_idx]
                        if isinstance(locked_val, bool):
                            is_locked = locked_val
                        elif isinstance(locked_val, (int, float)):
                            is_locked = bool(locked_val)
                        elif isinstance(locked_val, str):
                            is_locked = locked_val.lower() in ('true', '1', 'yes', 'locked')
                    
                    if is_locked:
                        continue
                    
                    # Skip features without valid geometry
                    has_valid_geom = feat.id() in feat_geom_map
                    
                    # Get cell range for this feature (from field or use default)
                    cell_range_km = default_cell_range_km
                    if cell_range_idx != -1:
                        try:
                            # Try to get cell range from the field
                            range_val = feat[cell_range_idx]
                            if range_val is not None:
                                cell_range_km = float(range_val)
                        except (ValueError, TypeError):
                            # If invalid, use default
                            pass
                    
                    # Calculate number of RSIs needed for this cell based on its range
                    # Using Ncs=13 (typical for suburban/rural) as default
                    rsi_count_needed = self._calculate_rsi_count(cell_range_km, ncs_config=13, prach_format=prach_format)
                    
                    # Find a suitable RSI range considering reuse distance
                    candidate_rsi = next_rsi
                    assigned = False
                    attempts = 0
                    max_rsi_attempts = rsi_max - rsi_min + 1
                    
                    while not assigned and attempts < max_rsi_attempts:
                        # Check if we have enough consecutive RSIs available
                        rsi_range = list(range(candidate_rsi, candidate_rsi + rsi_count_needed))
                        
                        # Wrap around if needed
                        rsi_range_wrapped = []
                        for rsi in rsi_range:
                            if rsi > rsi_max:
                                wrapped_rsi = rsi_min + (rsi - rsi_max - 1)
                                rsi_range_wrapped.append(wrapped_rsi)
                            else:
                                rsi_range_wrapped.append(rsi)
                        
                        # Check if any RSI in the range is already used
                        range_available = not any(rsi in used_rsis for rsi in rsi_range_wrapped)
                        
                        if not range_available:
                            candidate_rsi += 1
                            if candidate_rsi > rsi_max:
                                candidate_rsi = rsi_min
                            attempts += 1
                            continue
                        
                        # Check reuse distance - avoid overlapping RSI ranges in neighboring cells
                        reuse_ok = True
                        if has_valid_geom:
                            feat_point = feat_geom_map[feat.id()]
                            # Check all RSIs in this range against neighboring cells
                            for check_rsi in rsi_range_wrapped:
                                if check_rsi in rsi_spatial_index:
                                    # Check distance to all cells that use this RSI
                                    for other_id, other_point, other_count in rsi_spatial_index[check_rsi]:
                                        dist_m = distance_calc.measureLine(feat_point, other_point)
                                        dist_km = dist_m / 1000.0
                                        if dist_km < rsi_reuse_distance_km:
                                            reuse_ok = False
                                            break
                                if not reuse_ok:
                                    break
                        
                        if reuse_ok:
                            # Good RSI range found - assign it
                            # Mark all RSIs in the range as used
                            for rsi in rsi_range_wrapped:
                                used_rsis.add(rsi)
                                # Add to spatial index for future checks
                                if rsi not in rsi_spatial_index:
                                    rsi_spatial_index[rsi] = []
                                if has_valid_geom:
                                    rsi_spatial_index[rsi].append((feat.id(), feat_geom_map[feat.id()], rsi_count_needed))
                            
                            # Store assignment (store the starting RSI and count)
                            current_assignment = assignments.get(feat.id(), (None, None, None))
                            assignments[feat.id()] = (current_assignment[0], candidate_rsi, rsi_count_needed)
                            assigned = True
                            
                            # Update next_rsi for next feature (skip past this range)
                            next_rsi = candidate_rsi + rsi_count_needed
                            if next_rsi > rsi_max:
                                next_rsi = rsi_min + (next_rsi - rsi_max - 1)
                        else:
                            # Try next RSI
                            candidate_rsi += 1
                            if candidate_rsi > rsi_max:
                                candidate_rsi = rsi_min
                            attempts += 1
                    
                    # If no suitable RSI range found after all attempts, assign with fallback
                    if not assigned:
                        fallback_rsi = next_rsi
                        # Limit fallback attempts
                        fallback_attempts = 0
                        max_fallback_attempts = (rsi_max - rsi_min + 1) // rsi_count_needed
                        
                        # Try to find any available range
                        while fallback_attempts < max_fallback_attempts:
                            # Check if range is available
                            fallback_range = []
                            for i in range(rsi_count_needed):
                                r = fallback_rsi + i
                                if r > rsi_max:
                                    r = rsi_min + (r - rsi_max - 1)
                                fallback_range.append(r)
                            
                            range_available = not any(rsi in used_rsis for rsi in fallback_range)
                            if range_available:
                                break
                            
                            fallback_rsi += rsi_count_needed
                            if fallback_rsi > rsi_max:
                                fallback_rsi = rsi_min
                            fallback_attempts += 1
                        
                        # If we still can't find an unused range, reuse starting from next_rsi
                        if not range_available:
                            fallback_rsi = next_rsi
                            fallback_range = []
                            for i in range(rsi_count_needed):
                                r = fallback_rsi + i
                                if r > rsi_max:
                                    r = rsi_min + (r - rsi_max - 1)
                                fallback_range.append(r)
                        
                        # Assign the range
                        for rsi in fallback_range:
                            used_rsis.add(rsi)
                            if rsi not in rsi_spatial_index:
                                rsi_spatial_index[rsi] = []
                            if has_valid_geom:
                                rsi_spatial_index[rsi].append((feat.id(), feat_geom_map[feat.id()], rsi_count_needed))
                        
                        # Store assignment (starting RSI and count)
                        current_assignment = assignments.get(feat.id(), (None, None, None))
                        assignments[feat.id()] = (current_assignment[0], fallback_rsi, rsi_count_needed)
                        
                        # Update next_rsi
                        next_rsi = fallback_rsi + rsi_count_needed
                        if next_rsi > rsi_max:
                            next_rsi = rsi_min + (next_rsi - rsi_max - 1)

            # Update progress for each group
            # Allocate 30-60% for PCI, 60-90% for RSI (if both are planned)
            if plan_pci and plan_rsi:
                # Both PCI and RSI - split progress 30-60 for PCI, 60-90 for RSI
                pci_progress = 30 + int((group_idx + 1) / total_groups * 30)
                rsi_progress = 60 + int((group_idx + 1) / total_groups * 30)
                if plan_pci and not plan_rsi:
                    # Only PCI
                    progress = pci_progress
                    self.progressBar.setFormat(f"PCI planning: {int((group_idx + 1) / total_groups * 100)}%")
                elif not plan_pci and plan_rsi:
                    # Only RSI
                    progress = 30 + int((group_idx + 1) / total_groups * 60)
                    self.progressBar.setFormat(f"RSI planning: {int((group_idx + 1) / total_groups * 100)}%")
                else:
                    # Both - show which phase we're in
                    if group_idx < total_groups:  # Still in progress
                        progress = rsi_progress  # We're in RSI phase now since it runs after PCI
                        self.progressBar.setFormat(f"RSI planning: {int((group_idx + 1) / total_groups * 100)}%")
            elif plan_pci:
                progress = 30 + int((group_idx + 1) / total_groups * 60)
                self.progressBar.setFormat(f"PCI planning: {int((group_idx + 1) / total_groups * 100)}%")
            elif plan_rsi:
                progress = 30 + int((group_idx + 1) / total_groups * 60)
                self.progressBar.setFormat(f"RSI planning: {int((group_idx + 1) / total_groups * 100)}%")
            else:
                progress = 30 + int((group_idx + 1) / total_groups * 60)
            
            self.progressBar.setValue(progress)
            QtWidgets.QApplication.processEvents()

        # Create output features with PCI/RSI assignments
        self.progressBar.setValue(95)
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
            
            # Add PCI/RSI plan values
            if feat.id() in assignments:
                pci_val, rsi_val, rsi_count = assignments[feat.id()]
                if plan_pci and pci_val is not None:
                    new_feat[pci_plan_field_name] = pci_val
                if plan_rsi and rsi_val is not None:
                    new_feat[rsi_plan_field_name] = rsi_val
                    # Add RSI count if RSI was assigned
                    if rsi_count is not None:
                        new_feat['RSI_COUNT'] = rsi_count
            else:
                # Feature wasn't assigned (might be locked) - leave fields as NULL
                # Note: NULL is better than 0 for unassigned values
                pass
            
            output_features.append(new_feat)
        
        # Add features to output layer
        output_provider.addFeatures(output_features)
        output_layer.updateExtents()
        
        # Add output layer to project
        QgsProject.instance().addMapLayer(output_layer)
        
        self.progressBar.setValue(100)
        self.progressBar.setFormat("Complete!")
        QtWidgets.QApplication.processEvents()
        
        # Build completion message
        planned_items = []
        if plan_pci:
            planned_items.append('PCI')
        if plan_rsi:
            planned_items.append('RSI')
        
        message = f'Planning complete!\n\n{" and ".join(planned_items)} assigned to {len(output_features)} features.\n\nNew layer created: {output_layer_name}'
        QtWidgets.QMessageBox.information(self, 'PCI/RSI Planner', message)
        self.progressBar.setVisible(False)
