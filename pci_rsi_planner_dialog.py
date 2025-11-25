# -*- coding: utf-8 -*-

import os
import math
from qgis.PyQt import uic
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import QVariant
from qgis.core import QgsProject, QgsField, QgsVectorLayer, QgsDistanceArea, QgsCoordinateReferenceSystem, QgsVectorDataProvider, QgsFeature

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
        output_provider.addAttributes([pci_field, rsi_field])
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
            band_val = feat[band_idx]
            key = (str(tech_val), str(band_val))
            groups.setdefault(key, []).append(feat)

        # Dictionary to store PCI/RSI assignments: {feature_id: (pci, rsi)}
        assignments = {}
        
        # Assign PCI/RSI
        self.progressBar.setValue(30)
        self.progressBar.setFormat("Assigning PCI/RSI...")
        QtWidgets.QApplication.processEvents()
        
        total_groups = len(groups)
        for group_idx, ((tech_val, band_val), feats) in enumerate(groups.items()):
            used_pcis = set()
            used_rsis = set()
            next_pci = pci_min  # Track next PCI to try for this group
            next_rsi = rsi_min  # Track next RSI to try for this group

            # First pass: respect locked cells
            for feat in feats:
                if locked_idx != -1 and feat[locked_idx]:
                    pci_val = None
                    rsi_val = None
                    if plan_pci and existing_pci_idx != -1 and feat[existing_pci_idx] is not None:
                        pci_val = int(feat[existing_pci_idx])
                        used_pcis.add(pci_val)
                    if plan_rsi and existing_rsi_idx != -1 and feat[existing_rsi_idx] is not None:
                        rsi_val = int(feat[existing_rsi_idx])
                        used_rsis.add(rsi_val)
                    assignments[feat.id()] = (pci_val, rsi_val)

            # Second pass: assign new values to unlocked cells with reuse distance and mod checking
            # Build a map of feature ID to geometry for distance calculations
            feat_geom_map = {f.id(): f.geometry().asPoint() for f in feats if f.geometry()}
            # Track PCI assignments: {feat_id: pci}
            pci_assignments = {}
            # Build spatial index for faster neighbor lookups: {pci: [list of points with that pci]}
            pci_spatial_index = {}
            
            for f in feats:
                if locked_idx != -1 and f[locked_idx] and existing_pci_idx != -1 and f[existing_pci_idx] is not None:
                    pci_val = int(f[existing_pci_idx])
                    pci_assignments[f.id()] = pci_val
                    # Add to spatial index
                    if pci_val not in pci_spatial_index:
                        pci_spatial_index[pci_val] = []
                    if f.id() in feat_geom_map:
                        pci_spatial_index[pci_val].append((f.id(), feat_geom_map[f.id()]))
            
            for feat in feats:
                is_locked = bool(feat[locked_idx]) if locked_idx != -1 else False
                if is_locked:
                    continue

                # Assign PCI if requested
                if plan_pci:
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
                        if feat.geometry() and feat.id() in feat_geom_map and candidate_pci in pci_spatial_index:
                            feat_point = feat_geom_map[feat.id()]
                            # Only check cells that have the same candidate_pci
                            for other_id, other_point in pci_spatial_index[candidate_pci]:
                                dist_m = distance_calc.measureLine(feat_point, other_point)
                                dist_km = dist_m / 1000.0
                                if dist_km < reuse_distance_km:
                                    reuse_ok = False
                                    break
                        
                        # Check PCI mod 3/6 conflicts with nearby cells
                        # Only check PCIs with same mod 3 or mod 6 (much faster!)
                        mod_ok = True
                        if check_pci_mod and feat.geometry() and feat.id() in feat_geom_map:
                            feat_point = feat_geom_map[feat.id()]
                            candidate_mod3 = candidate_pci % 3
                            candidate_mod6 = candidate_pci % 6
                            
                            # Only check PCIs that could have mod conflicts
                            for other_pci in pci_spatial_index.keys():
                                # Skip if no mod conflict possible
                                if (other_pci % 3) != candidate_mod3 and (other_pci % 6) != candidate_mod6:
                                    continue
                                
                                # Check distance to cells with this PCI
                                for other_id, other_point in pci_spatial_index[other_pci]:
                                    dist_m = distance_calc.measureLine(feat_point, other_point)
                                    dist_km = dist_m / 1000.0
                                    # Check mod conflicts for neighbors within 2x reuse distance
                                    if dist_km < (reuse_distance_km * 2):
                                        # mod 3 conflict
                                        if (candidate_pci % 3) == (other_pci % 3):
                                            mod_ok = False
                                            break
                                        # mod 6 conflict (stricter for very close neighbors)
                                        if dist_km < reuse_distance_km and (candidate_pci % 6) == (other_pci % 6):
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
                            if feat.id() in feat_geom_map:
                                pci_spatial_index[candidate_pci].append((feat.id(), feat_geom_map[feat.id()]))
                            # Store assignment
                            current_assignment = assignments.get(feat.id(), (None, None))
                            assignments[feat.id()] = (candidate_pci, current_assignment[1])
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
                        while fallback_pci in used_pcis and fallback_pci <= pci_max:
                            fallback_pci += 1
                        if fallback_pci > pci_max:
                            fallback_pci = pci_min
                            while fallback_pci in used_pcis and fallback_pci < next_pci:
                                fallback_pci += 1
                        used_pcis.add(fallback_pci)
                        pci_assignments[feat.id()] = fallback_pci
                        # Add to spatial index
                        if fallback_pci not in pci_spatial_index:
                            pci_spatial_index[fallback_pci] = []
                        if feat.id() in feat_geom_map:
                            pci_spatial_index[fallback_pci].append((feat.id(), feat_geom_map[feat.id()]))
                        # Store assignment
                        current_assignment = assignments.get(feat.id(), (None, None))
                        assignments[feat.id()] = (fallback_pci, current_assignment[1])
                        # Update next_pci
                        next_pci = fallback_pci + 1
                        if next_pci > pci_max:
                            next_pci = pci_min

                # Assign RSI if requested (simpler, sequential)
                if plan_rsi:
                    # Find next available RSI
                    while next_rsi in used_rsis:
                        next_rsi += 1
                        if next_rsi > rsi_max:
                            next_rsi = rsi_min
                    used_rsis.add(next_rsi)
                    # Store assignment
                    current_assignment = assignments.get(feat.id(), (None, None))
                    assignments[feat.id()] = (current_assignment[0], next_rsi)
                    # Update next_rsi for next feature
                    next_rsi += 1
                    if next_rsi > rsi_max:
                        next_rsi = rsi_min

            # Update progress for each group
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
                pci_val, rsi_val = assignments[feat.id()]
                if pci_val is not None:
                    new_feat[pci_plan_field_name] = pci_val
                if rsi_val is not None:
                    new_feat[rsi_plan_field_name] = rsi_val
            
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
