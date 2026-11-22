# Data acquisition

These commands create an immutable local snapshot for the canonical pilot in
`config/study_area.json`. Outputs go under the gitignored `data/raw/` tree and
do not connect to PostgreSQL or Supabase.

Run commands from the repository root with Python 3.11-3.13 and the pipeline
dependencies installed.

```powershell
python pipelines/acquire/download_osm.py --output data/raw/osm
python pipelines/acquire/download_fema_nfhl.py --bbox=-95.45,29.68,-95.25,29.85 --output data/raw/fema_nfhl
python pipelines/acquire/discover_usgs_fim.py --bbox=-95.8,29.4,-94.9,30.2 --output data/raw/usgs_fim
python pipelines/acquire/download_usgs_3dep.py --bbox=-95.45,29.68,-95.25,29.85 --output data/raw/usgs_3dep
python pipelines/acquire/download_usgs_3dep.py --bbox=-95.45,29.68,-95.25,29.85 --output data/raw/usgs_3dep --download --title-contains TX_Houston_B24 --max-file-gb 1
python pipelines/acquire/download_census_population.py --year 2024 --state 48 --county 201 --extract-boundaries --output data/raw/census
```

Set `CENSUS_API_KEY` in the local shell before the final command. Never commit
the key or pass it through browser/frontend variables.

FEMA NFHL polygons are regulatory hazard information, USGS 3DEP is terrain
elevation, and neither source is an observed flood-depth or road-closure feed.
