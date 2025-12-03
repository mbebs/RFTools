# RF Tools

**Version:** 3.4  
**Author:** Leonard Fodje  
**Email:** mbebs@live.com  
**Repository:** https://github.com/mbebs/RFTools  
**QGIS Minimum Version:** 3.0

---

## Overview

RF Tools is a comprehensive QGIS plugin designed for RF and Wireless Telecom Engineers. It provides a suite of powerful tools for planning, optimizing, and analyzing cellular networks including LTE (4G) and 5G NR deployments.

---

## Features

### 🗺️ Site See
Visualize cellular sectors on a map with advanced multi-band support.

**Key Features:**
- Sector polygon visualization with customizable size and beamwidth
- Multi-band sector display with automatic size offset (higher frequencies = smaller nested sectors)
- Color coding by azimuth or frequency band
- Support for remote radio heads (RRH) with connection lines
- Site location markers (small filled circles)

**Color Schemes:**
- **By Azimuth:** Red (0-60°), Green (60-180°), Blue (180-300°), Orange (300-360°)
- **By Band:** 700 MHz (Dark Red), 850 MHz (Red), 1800 MHz (Orange), 2100 MHz (Yellow), 2600 MHz (Green), 3500 MHz (Blue)

---

### 📡 PCI/RSI Planner
Intelligent Physical Cell ID (PCI) and Root Sequence Index (RSI) planning with conflict avoidance.

**Key Features:**
- Automatic PCI and RSI assignment for LTE and 5G NR networks
- Configurable PCI reuse distance (default: 10 km, max: 50 km)
- PCI Mod 3 and Mod 6 conflict detection and avoidance
- Geographic distance-aware planning
- Lock/unlock individual cells to preserve existing assignments
- Support for multiple bands and technologies

**Planning Rules:**
- Same PCI conflicts avoided within reuse distance
- Mod 3 conflicts avoided within 2x reuse distance
- Mod 6 conflicts avoided within reuse distance
- Intelligent multi-pass assignment algorithm

---

### 📐 Tilt Optimizer
Optimize electrical tilt angles for optimal coverage and interference management.

**Key Features:**
- Neighbor-aware tilt optimization
- Considers antenna height, beamwidth, power, and gain
- Frequency-dependent path loss calculations
- Configurable optimization radius
- Preserves locked sectors

---

### 🧭 Azimuth Optimizer
Optimize sector azimuth angles for balanced coverage.

**Key Features:**
- Site-level azimuth optimization
- Band-aware optimization (maintains separation between bands)
- Lock/unlock individual sectors
- Automatic 120° spacing for 3-sector sites
- Considers neighboring sites for interference minimization

---

### 📊 Coverage Prediction
Generate coverage prediction heatmaps using industry-standard propagation models.

**Propagation Models:**
- **Okumura-Hata:** Urban/suburban environments
- **COST-231:** Extended Hata for higher frequencies
- **Ericsson 9999:** General purpose model
- **SUI (Stanford University Interim):** Suburban/rural
- **ECC-33:** European standard model

**Features:**
- RSRP (Reference Signal Received Power) calculation
- Configurable prediction radius and resolution
- Band filtering for multi-band analysis
- Raster output for GIS analysis

---

### ⚠️ Interference Analysis
Detect and visualize interference between sectors.

**Interference Types:**
- **Co-Channel:** Same frequency interference (Red, 2.0pt lines)
- **PCI Conflict:** Same PCI or Mod 3/6 conflicts (Orange, 1.5pt lines)
  - Collision (same PCI): Critical severity
  - Mod 3 conflict: High severity
  - Mod 6 conflict: Medium severity
- **Adjacent Channel:** Adjacent frequency interference (Yellow, 1.0pt lines)

**Features:**
- Configurable interference distance (0.5-10 km)
- Azimuth overlap threshold detection
- Detailed source/target sector identification (Site_Sector_Band)
- Visual differentiation by interference type and severity

---

## Installation

1. Download the plugin from the QGIS Plugin Repository or GitHub
2. In QGIS, go to **Plugins → Manage and Install Plugins**
3. Search for "RF Tools" and click **Install**
4. The plugin will appear in the **Plugins** menu

---

## Sample Data Reference

### Site See

**Required Fields:**
```
SITE_X | SITE_Y | AZIMUTH | BEAMWIDTH | SECTOR_SIZE
```

**Sample Data:**
```
-95.123 | 29.456 | 0   | 65 | 1000
-95.123 | 29.456 | 120 | 65 | 1000
-95.123 | 29.456 | 240 | 65 | 1000
```

**Optional Fields:** 
- `SECTOR_X`, `SECTOR_Y` (for remote radio heads)
- `BAND` (for multi-band visualization)

---

### PCI/RSI Planner

**Required Fields:**
```
TECH | ENB_ID | CELL_ID | BAND | EARFCN | LOCKED
```

**Sample Data:**
```
LTE | 12345 | 0 | L1800 | 1575 | 0
LTE | 12345 | 1 | L1800 | 1575 | 0
NR  | 67890 | 0 | n78   | 632628 | 0
```

**Output Fields:** `PCI_PLAN`, `RSI_PLAN`

---

### Tilt Optimizer

**Required Fields:**
```
HEIGHT | V_BEAMWIDTH | H_BEAMWIDTH | PMAX | ANT_GAIN | BAND | FREQUENCY
```

**Sample Data:**
```
30 | 6.5 | 65 | 46 | 17.5 | L1800 | 1850
25 | 6.5 | 65 | 43 | 17.5 | L2100 | 2140
```

**Output Field:** `ETILT_OPT`

---

### Azimuth Optimizer

**Required Fields:**
```
SITE_ID | AZIMUTH | BEAMWIDTH | BAND | LOCKED
```

**Sample Data:**
```
SITE_001 | 0   | 65 | L1800 | 0
SITE_001 | 120 | 65 | L1800 | 0
SITE_001 | 240 | 65 | L1800 | 1
```

**Output Field:** `AZIMUTH_OPT`

---

### Coverage Prediction

**Required Fields:**
```
HEIGHT | AZIMUTH | BEAMWIDTH | PMAX | ANT_GAIN | FREQUENCY | BAND
```

**Sample Data:**
```
30 | 0   | 65 | 46 | 17.5 | 1850 | L1800
30 | 120 | 65 | 46 | 17.5 | 1850 | L1800
```

**Output:** Raster layer with RSRP values (dBm)

---

### Interference Analysis

**Required Fields:**
```
SITE_ID | SECTOR | FREQUENCY | PCI | BAND | AZIMUTH | BEAMWIDTH
```

**Sample Data:**
```
SITE_001 | 0 | 1575   | 150 | L1800 | 0   | 65
SITE_001 | 1 | 1575   | 151 | L1800 | 120 | 65
SITE_002 | 0 | 1575   | 150 | L1800 | 30  | 65
```

**Output:** Line layer showing interference pairs with severity classification

---

## Field Value Guidelines

### Coordinates
- **Longitude (X):** -180 to 180 (decimal degrees)
- **Latitude (Y):** -90 to 90 (decimal degrees)

### Angles
- **Azimuth:** 0-360 degrees (0 = North, 90 = East)
- **Beamwidth:** Typically 33, 65, or 90 degrees
- **Tilt:** 0-15 degrees (electrical tilt)

### Power & Gain
- **Pmax:** 40-50 dBm (transmit power)
- **Antenna Gain:** 15-21 dBi

### Frequencies
- **LTE Band 3 (L1800):** 1710-1880 MHz
- **LTE Band 1 (L2100):** 1920-2170 MHz
- **5G NR Band 78 (n78):** 3300-3800 MHz

### IDs
- **PCI (LTE):** 0-503
- **PCI (5G NR):** 0-1007
- **RSI (LTE):** 0-837
- **eNB ID:** 1-1048575
- **Cell ID:** 0-255

### Boolean Fields
- **Locked:** 0 = unlocked, 1 = locked

---

## Version History

### Version 3.3 (Current)
- ✨ Multi-band sector visualization with automatic size offset
- ✨ Band-based color coding for Site See
- ✨ Site location markers (small filled circles)
- ✨ Enhanced interference analysis with conflict type differentiation
- ✨ Source/target sector identification (Site_Sector_Band format)
- ✨ Visual line styling by interference type and severity
- 🐛 Fixed deprecated QgsField constructor warnings
- 📝 Updated PayPal donation link

### Version 2.3
- Enhanced PCI/RSI planner with configurable reuse distance
- Added multiple propagation models to coverage prediction
- Improved band filtering in coverage prediction
- Added locked field support in azimuth optimizer

---

## Support & Contribution

- **Issues & Bug Reports:** https://github.com/mbebs/RFTools/issues
- **Donations:** https://paypal.me/rftools

---

## License

This plugin is free and open source software.

---

## Author

**Leonard Fodje**  
Email: mbebs@live.com  
GitHub: https://github.com/mbebs/RFTools

---

## Acknowledgments

Special thanks to the QGIS community and all contributors who have helped improve RF Tools.

---

*For detailed sample data structures and additional examples, see [SAMPLE_DATA_REFERENCE.md](SAMPLE_DATA_REFERENCE.md)*
