import os
import re
import math
from geographiclib.geodesic import Geodesic

from qgis.core import (QgsFeature,
    QgsCoordinateTransform, QgsVectorLayer, QgsPointXY, QgsFeature,
    QgsGeometry, QgsProject, QgsMapLayerProxyModel, Qgis, QgsCoordinateReferenceSystem, QgsUnitTypes)

from qgis.gui import QgsMessageBar

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QDialogButtonBox

epsg4326 = QgsCoordinateReferenceSystem("EPSG:4326")

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'ui/siteSee.ui'))

class SiteSeeWidget(QDialog, FORM_CLASS):
    def __init__(self, iface, parent):
        super(SiteSeeWidget, self).__init__(parent)
        self.setupUi(self)
        self.selectLayerComboBox.setFilters(QgsMapLayerProxyModel.PointLayer)
        self.selectLayerComboBox.layerChanged.connect(self.findFields)
        self.iface = iface
        self.polygonLayer = None
        self.geod = Geodesic.WGS84

    def apply(self):
        '''process the data'''
        layer = self.selectLayerComboBox.currentLayer()
        outname = self.layerNameLineEdit.text()
        if not layer:
            self.showErrorMessage("No valid layer to process")
            return


        # We need to make sure all the points in the layer are transformed to EPSG:4326
        layerCRS = layer.crs()
        self.transform = QgsCoordinateTransform(layerCRS, epsg4326)

        #Draw Sectors
        self.processSectors(layer, outname,
                        self.azimuthComboBox.currentIndex() - 1,
                        self.beamwidthComboBox.currentIndex() - 1,
                        self.sectorsizeComboBox.currentIndex() - 1,
                        self.defaultbeamWidth.value(),
                        self.defaultsectorSize.value())

    def showEvent(self, event):
        '''The dialog is being shown. We need to initialize it.'''
        super(SiteSeeWidget, self).showEvent(event)
        self.findFields()

    def findFields(self):
        if not self.isVisible():
            return
        layer = self.selectLayerComboBox.currentLayer()
        self.clearLayerFields()
        if layer:
            header = [u"[ Use Default ]"]
            fields = layer.pendingFields()
            for field in fields.toList():
                # force it to be lower case - makes matching easier
                name = field.name()
                header.append(name)
            self.configureLayerFields(header)

    def configureLayerFields(self, header):

        self.azimuthComboBox.addItems(header)
        self.beamwidthComboBox.addItems(header)
        self.sectorsizeComboBox.addItems(header)


    def clearLayerFields(self):

        self.azimuthComboBox.clear()
        self.beamwidthComboBox.clear()
        self.sectorsizeComboBox.clear()
        self.progressBar.setValue(0)


    def showErrorMessage(self, message):
        self.iface.messageBar().pushMessage("", message, level=QgsMessageBar.WARNING, duration=3)


    def processSectors(self, layer, outname, azimcol, beamwidthcol, sectorsizecol, defaultBW, defaultSS):

        fields = layer.pendingFields()

        polygonLayer = QgsVectorLayer("Polygon?crs=epsg:4326", outname, "memory")
        ppolygon = polygonLayer.dataProvider()
        ppolygon.addAttributes(fields)
        polygonLayer.updateFields()

        iter = layer.getFeatures()

        # Count all selected feature
        count = layer.featureCount()
        # set a counter to reference the progress
        i = 0
        for feature in iter:

            i = i + 1
            percent = (i / float(count)) * 100
            self.progressBar.setValue(percent)

            try:
                pts = []
                pt = feature.geometry().asPoint()
                # make sure the coordinates are in EPSG:4326
                pt = self.transform.transform(pt.x(), pt.y())
                pts.append(pt)

                if azimcol == -1:
                    azimuth = 360.0
                else:
                    azimuth = float(feature[azimcol])

                if beamwidthcol == -1:
                    beamwidth = defaultBW
                else:
                    beamwidth = float(feature[beamwidthcol])

                if sectorsizecol == -1:
                    sectorsize = float(defaultSS) * 1609.34
                else:
                    sectorsize = float(feature[sectorsizecol]) * 1609.34

                if 0.0 < beamwidth < 360.0:
                    halfbw = beamwidth / 2.0
                    sangle = (azimuth - halfbw) % 360.0
                    eangle = (azimuth + halfbw) % 360.0
                else:
                    sangle = 0.0 % 360.0
                    eangle = 359.9 % 360.0
                    sectorsize = sectorsize / 1.50

                if sangle > eangle:
                    # We are crossing the 0 boundry so lets just subtract
                    # 360 from it.
                    sangle -= 360.0
                while sangle < eangle:
                    g = self.geod.Direct(pt.y(), pt.x(), sangle, sectorsize, Geodesic.LATITUDE | Geodesic.LONGITUDE)
                    pts.append(QgsPoint(g['lon2'], g['lat2']))
                    sangle += 4.0

                g = self.geod.Direct(pt.y(), pt.x(), eangle, sectorsize, Geodesic.LATITUDE | Geodesic.LONGITUDE)
                pts.append(QgsPoint(g['lon2'], g['lat2']))
                pts.append(pt)

                featureout = QgsFeature()
                featureout.setGeometry(QgsGeometry.fromPolygon([pts]))
                featureout.setAttributes(feature.attributes())
                ppolygon.addFeatures([featureout])
            except:
                pass

        polygonLayer.updateExtents()
        #QgsMapLayerRegistry.instance().addMapLayer(polygonLayer)
        QgsProject.instance().addMapLayer(polygonLayer)

    def accept(self):
        self.apply()
        self.close()
