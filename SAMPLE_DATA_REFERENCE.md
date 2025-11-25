# RF Tools - Sample Data Reference

This document provides sample layer structures and data for each RF Tools feature.

## Site See

**Required Fields:**
```
SITE_X | SITE_Y | AZIMUTH | BEAMWIDTH | SECTOR_SIZE
```

**Sample Data:**
```
-95.123 | 29.456 | 0   | 65 | 1000
-95.123 | 29.456 | 120 | 65 | 1000
-95.123 | 29.456 | 240 | 65 | 1000
-95.234 | 29.567 | 30  | 65 | 1500
```

**Optional Fields:** SECTOR_X, SECTOR_Y (for remote radio heads)

**Color Coding:**
Sectors are automatically color-coded based on azimuth for easy visualization:
- **Red (0-60°)**: North-facing sectors
- **Green (60-180°)**: East/Southeast-facing sectors
- **Blue (180-300°)**: South/Southwest-facing sectors
- **Orange (300-360°)**: West/Northwest-facing sectors

---

## PCI/RSI Planner

**Required Fields:**
```
TECH | ENB_ID | CELL_ID | BAND | EARFCN | LOCKED
```

**Sample Data:**
```
LTE | 12345 | 0 | L1800 | 1575 | 0
LTE | 12345 | 1 | L1800 | 1575 | 0
LTE | 12345 | 2 | L1800 | 1575 | 0
NR  | 67890 | 0 | n78   | 632628 | 0
```

**Optional Fields:** EXISTING_PCI, EXISTING_RSI

**Output Fields:** PCI_PLAN, RSI_PLAN

**Enhanced Features:**
- **Reuse Distance:** Ensures cells with the same PCI are separated by minimum distance (default: 2 km)
- **PCI Mod 3/6 Checking:** Avoids mod 3 conflicts within 2x reuse distance and mod 6 conflicts within reuse distance
- **Geographic Distance Aware:** Uses actual geographic distance between cell sites for conflict checking
- **Intelligent Assignment:** Tries multiple PCI values to find one that satisfies all constraints

---

## Tilt Optimizer

**Required Fields:**
```
HEIGHT | V_BEAMWIDTH | H_BEAMWIDTH | PMAX | ANT_GAIN | BAND | FREQUENCY
```

**Sample Data:**
```
30 | 6.5 | 65 | 46 | 17.5 | L1800 | 1850
25 | 6.5 | 65 | 43 | 17.5 | L2100 | 2140
35 | 4.5 | 65 | 46 | 18.0 | n78   | 3600
```

**Output Field:** ETILT_OPT

---

## Azimuth Optimizer

**Required Fields:**
```
SITE_ID | AZIMUTH | BEAMWIDTH | BAND | LOCKED
```

**Sample Data:**
```
SITE_001 | 0   | 65 | L1800 | 0
SITE_001 | 120 | 65 | L1800 | 0
SITE_001 | 240 | 65 | L1800 | 1
SITE_002 | 30  | 65 | L2100 | 0
```

**Output Field:** AZIMUTH_OPT

---

## Coverage Prediction

**Required Fields:**
```
HEIGHT | AZIMUTH | BEAMWIDTH | PMAX | ANT_GAIN | FREQUENCY | BAND
```

**Sample Data:**
```
30 | 0   | 65 | 46 | 17.5 | 1850 | L1800
30 | 120 | 65 | 46 | 17.5 | 1850 | L1800
30 | 240 | 65 | 46 | 17.5 | 1850 | L1800
25 | 30  | 65 | 43 | 17.5 | 2140 | L2100
```

**Output:** Raster layer with RSRP values (dBm)

---

## Interference Analysis

**Required Fields:**
```
FREQUENCY | PCI | BAND | AZIMUTH | BEAMWIDTH
```

**Sample Data:**
```
1575   | 150 | L1800 | 0   | 65
1575   | 151 | L1800 | 120 | 65
1575   | 150 | L1800 | 30  | 65
632628 | 200 | n78   | 0   | 65
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
