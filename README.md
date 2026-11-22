# Flood-Aware Emergency Access Simulator — Houston starter

**Status: scaffold, not yet deployed or connected to a database.** Existing Supabase projects remain untouched.

## Architecture
- Frontend: React, Vite, MapLibre GL JS
- API: FastAPI, psycopg
- DB: Supabase PostgreSQL + PostGIS + pgRouting; private `gis` schema
- Offline ETL: OSMnx for road graph; later Census population and verified inundation-depth raster via Rasterio
- No heavy raster/OSMnx imports in serverless API

## Provision a **new** Supabase project (once a free slot is available)
1. Create project in the intended organization. Do not use the `resume` or `Clipzo` projects.
2. Run `database/migrations/001_initial.sql` in its SQL editor. Verify extension schemas/function namespace: if pgRouting is installed into `public`, change `extensions.pgr_dijkstra` accordingly (or move it into the configured extension schema before applying the function).
3. Keep `gis` private. Use a least-privilege backend DB user with access only to the required schema/data; do not put database credentials in the browser.
4. Set `DATABASE_URL` to the new project's connection pooler or a suitable direct connection string. Store only in backend environment secrets.

## Local API
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL='postgresql://...'
uvicorn app.main:app --reload --port 8000
```
API documentation: http://localhost:8000/docs

## Local UI
```bash
cd frontend
npm install
npm run dev
```
Optional `frontend/.env.local`: `VITE_API_URL=http://localhost:8000`

## Import starter OSM road data
```bash
cd pipelines
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python ingest_osm.py                     # dry run (download and count only)
DATABASE_URL='postgresql://...' python ingest_osm.py --confirm-write
```
OSMnx requires Internet access on the workstation/CI runner. Do **not** rerun inserts with the same name; current ingestion is one-time and lacks idempotent merge logic. The small bbox is a technical starting point, not yet selected for flood raster coverage.

## Current implemented endpoints
- `GET /api/health`
- `GET /api/study-areas`
- `GET /api/facilities?area_id=1`
- `GET /api/scenarios?area_id=1`
- `GET /api/roads?area_id=1`
- `GET /api/routes?origin_node_id=...&destination_node_id=...&scenario_id=...`
- `GET /api/scenarios/{id}/closed-roads`
- `GET /api/scenarios/{id}/impact`

## Important work still to implement
- Geolocate, verify, and snap facilities to network nodes. OSM hospitals are *not* necessarily confirmed emergency departments; shelters need authoritative status.
- Census population ETL, network origin snapping, accessibility calculations and cache/job orchestration.
- Pick a Houston area overlapping downloadable legitimate flood-depth rasters; verify horizontal/vertical CRS, raster meaning, date, nodata, roadway elevations, bridges and underpasses.
- Link sampled depths to scenario edge impacts, make scenario creation/run endpoints, precompute outputs, and validate routes.
- Add API auth/rate limits, safer scoped read-only SQL role, pagination/vector-tile strategy, spatial clipping/LOD for larger areas, unit tests and integration tests.
- Add route geometry ordered/directed correctly; current route endpoint returns an unordered geometry collection, useful only as a skeleton.
- Configure Git-based frontend and backend deployment to Vercel. Validate native Python service routing and hobby allowances against current docs before going live.

**Safety:** outputs are simulated and must not be used for real-time emergency dispatch or flood crossing decisions.

## OSM facility ingestion (after the road import)
```bash
cd pipelines
python ingest_facilities.py --area-id 1
DATABASE_URL='postgresql://...' python ingest_facilities.py --area-id 1 --confirm-write
```
OSM hospitals and fire stations are mapped; this pipeline deliberately does not invent shelter locations. Verify eligibility before accessibility calculations.

## Depth scenario import (after a **verified** depth GeoTIFF is acquired)
Export `edge_id,wkt` for the road edges with `ST_AsText(geom)`; then run:
```bash
cd pipelines
python sample_road_depth.py --raster /path/to/depth_meters.tif --edges-csv /path/to/edges.csv --output depths.csv
python load_scenario_depths.py --area-id 1 --csv depths.csv --name 'Sample depth scenario' --threshold-m 0.3 --source 'Verified dataset name and vintage'  # dry run
# add --confirm-write and DATABASE_URL only after reviewing depth coverage and units
```
A threshold is a model assumption and is not a safe-vehicle-crossing recommendation. Unknown depth remains unknown; it is not treated as measured dry road.
