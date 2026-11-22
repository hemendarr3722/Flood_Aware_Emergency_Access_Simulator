# Limitations, Assumptions & Safety Governance

## 1. Safety Governance & Ethical Disclaimer

> [!CAUTION]
> **NOT FOR OPERATIONAL EMERGENCY RESPONSE OR TACTICAL DISPATCH.**
> This software is an engineering and spatial analysis prototype designed strictly for municipal emergency planning, infrastructure vulnerability assessment, and scenario comparison. It must **NEVER** be used as a real-time navigation system, live dispatch guide, or evacuation routing tool during an active flood event.

---

## 2. Fundamental Scientific Limitations

### 2.1 Regulatory Hazard Zones vs Live Flood Inundation
- **Track A FEMA SFHA Polygons**: Represent statistical regulatory flood hazard boundaries (the 100-year / 1% annual-chance flood zone) determined from historical hydrology and insurance studies.
- **Limitation**: FEMA polygons do not indicate whether a specific road segment is actively inundated at any given moment, nor do they model localized storm surge, flash flooding, or drainage basin overflows.
- **Model Assumption**: In Scenario 2, any road edge intersecting an SFHA zone is modeled as potentially impassable to assess network redundancy under a severe regulatory scenario.

### 2.2 Elevation Grids vs Flood Inundation Depth
- **USGS 3DEP DEM**: Provides bare-earth terrain surface elevations at 1-metre resolution.
- **Limitation**: Terrain elevation alone does not indicate water depth. Subtracting terrain from a constant water level requires hydraulic boundary conditions and streamgage calibrations.
- **Governance**: Because official USGS FIM depth libraries were unavailable for Houston, Track B depth raster routing was deliberately disabled rather than using arbitrary synthetic water surfaces.

### 2.3 Census Aggregation & Origin Snapping
- **Census Block Group Scale**: Population counts are derived from ACS 2024 5-year Table B01003 aggregated at the block-group level (average 1,350 residents per block group).
- **Point-on-Surface Origins**: A single representative point is generated using `shapely.point_on_surface` to anchor the block group to the road network.
- **Limitation**: Individual residents are distributed across residential streets, not clustered at a single point. Origin travel times represent aggregate block-group accessibility rather than household-level arrival times.

### 2.4 Vehicle Clearance & Depth Thresholds
- **Current Model**: Employs binary edge exclusion (passable vs closed).
- **Future Hydrodynamic Model**: Once calibrated depth grids are acquired, clearance thresholds should be applied according to vehicle capabilities:
  - Passenger Vehicles: Restricted at $\ge 0.15\text{ m}$ ($6\text{ in}$)
  - Ambulances & Type 1 EMS: Restricted at $\ge 0.30\text{ m}$ ($12\text{ in}$)
  - High-Water Rescue & Heavy Fire Engines: Restricted at $\ge 0.60\text{ m}$ ($24\text{ in}$)
