"""Download ACS total population and matching TIGER/Line block-group geometry.

As of 2026, Census Data API queries require a free API key. Set
CENSUS_API_KEY or pass --api-key. The default pulls 2020-2024 ACS 5-year
population (B01003_001E) for Harris County, Texas, and 2024 block groups.
"""

from __future__ import annotations

import argparse
import csv
import os
import zipfile
from pathlib import Path

from common import download_file, request_json, utc_now, write_json


ACS_VARIABLE = "B01003_001E"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=2024)
    parser.add_argument("--state", default="48", help="Two-digit state FIPS; 48 is Texas.")
    parser.add_argument("--county", default="201", help="Three-digit county FIPS; 201 is Harris County.")
    parser.add_argument("--api-key", default=os.getenv("CENSUS_API_KEY"))
    parser.add_argument("--output", type=Path, default=Path("data/raw/census"))
    parser.add_argument("--skip-acs", action="store_true")
    parser.add_argument("--skip-boundaries", action="store_true")
    parser.add_argument("--extract-boundaries", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def normalize_acs(payload: list[list[str]]) -> list[dict]:
    if not payload or len(payload) < 2:
        return []
    header = payload[0]
    rows: list[dict] = []
    for raw in payload[1:]:
        row = dict(zip(header, raw, strict=True))
        state = row["state"].zfill(2)
        county = row["county"].zfill(3)
        tract = row["tract"].zfill(6)
        block_group = row["block group"]
        population_raw = row[ACS_VARIABLE]
        population_value = int(population_raw)
        rows.append(
            {
                "GEOID": f"{state}{county}{tract}{block_group}",
                "NAME": row["NAME"],
                "population": population_value if population_value >= 0 else None,
                "population_raw": population_raw,
                "state": state,
                "county": county,
                "tract": tract,
                "block_group": block_group,
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["GEOID", "NAME", "population", "population_raw", "state", "county", "tract", "block_group"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def safe_extract(zip_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if root not in target.parents and target != root:
                raise ValueError(f"Unsafe path in ZIP: {member.filename}")
        archive.extractall(destination)


def main() -> None:
    args = parse_args()
    if not (args.state.isdigit() and len(args.state) == 2):
        raise SystemExit("--state must be a two-digit FIPS code")
    if not (args.county.isdigit() and len(args.county) == 3):
        raise SystemExit("--county must be a three-digit FIPS code")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    metadata: dict = {
        "downloaded_at": utc_now(),
        "publisher": "U.S. Census Bureau",
        "year": args.year,
        "state_fips": args.state,
        "county_fips": args.county,
        "acs_variable": ACS_VARIABLE,
        "downloads": [],
    }

    if not args.skip_acs:
        if not args.api_key:
            raise SystemExit(
                "CENSUS_API_KEY or --api-key is required. Request a free key at "
                "https://api.census.gov/data/key_signup.html"
            )
        acs_url = f"https://api.census.gov/data/{args.year}/acs/acs5"
        payload = request_json(
            acs_url,
            {
                "get": f"NAME,{ACS_VARIABLE}",
                "for": "block group:*",
                "in": f"state:{args.state} county:{args.county}",
                "key": args.api_key,
            },
        )
        rows = normalize_acs(payload)
        write_json(output / f"acs5_{args.year}_population.json", rows)
        write_csv(output / f"acs5_{args.year}_population.csv", rows)
        metadata["acs_url_without_key"] = acs_url
        metadata["acs_row_count"] = len(rows)

    if not args.skip_boundaries:
        tiger_url = (
            f"https://www2.census.gov/geo/tiger/TIGER{args.year}/BG/"
            f"tl_{args.year}_{args.state}_bg.zip"
        )
        tiger_zip = output / f"tl_{args.year}_{args.state}_bg.zip"
        result = download_file(tiger_url, tiger_zip, overwrite=args.overwrite, max_bytes=2 * 1024**3)
        metadata["downloads"].append(result)
        if args.extract_boundaries:
            safe_extract(tiger_zip, output / f"tl_{args.year}_{args.state}_bg")

    write_json(output / "metadata.json", metadata)
    print(f"Census data saved under {output}")


if __name__ == "__main__":
    main()

