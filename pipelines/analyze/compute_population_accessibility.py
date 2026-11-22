"""
compute_population_accessibility.py — Phase 5 Population Accessibility Analysis.

Computes travel times from Census block-group origins to nearest emergency facilities
under baseline and flood scenarios using many-to-many pgRouting Dijkstra.

Rules:
1. No double counting: each origin contributes its population exactly once per scenario.
2. Thresholds: evaluates 15-min (900s), 30-min (1800s), and 45-min (2700s) accessibility.
3. Categorization:
   - within threshold (travel_time_s <= threshold)
   - beyond threshold (travel_time_s > threshold)
   - network_unreachable (valid snap but no path in graph)
   - invalid_snap (origin > 500m from pilot road network)
4. Reconciliation: sum of mutually exclusive categories equals total modeled population.
5. Invariant: edge removals cannot improve shortest travel times.

Usage:
    python pipelines/analyze/compute_population_accessibility.py --area-id 1 --confirm-write
"""
from __future__ import annotations
import argparse
import json
import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipelines"))

from psycopg import connect
from psycopg.rows import dict_row


def compute_scenario_accessibility(
    scenario_id: int,
    area_id: int,
    conn,
    dry_run: bool = False,
) -> dict:
    """Compute and store accessibility for a given scenario."""
    # 1. Fetch scenario info
    sc = conn.execute(
        "select id, name, scenario_kind from gis.flood_scenarios where id = %s",
        (scenario_id,),
    ).fetchone()
    if not sc:
        raise ValueError(f"Scenario {scenario_id} not found")

    print(f"\nComputing accessibility for Scenario {sc['id']}: '{sc['name']}' ({sc['scenario_kind']})")

    # 2. Fetch all population origins for area
    origins = conn.execute(
        """
        select id, geoid, population, road_node_id, snap_distance_m, snap_valid
        from gis.population_origins
        where area_id = %s
        order by id
        """,
        (area_id,),
    ).fetchall()

    total_origins = len(origins)
    total_population = sum(o["population"] for o in origins)
    print(f"Total origins: {total_origins}, total population: {total_population:,}")

    # 3. Fetch active verified/candidate emergency facilities
    fac_rows = conn.execute(
        """
        select id, name, facility_type, road_node_id
        from gis.facilities
        where area_id = %s
          and is_active = true
          and validation_status in ('verified', 'candidate')
          and road_node_id is not null
        """,
        (area_id,),
    ).fetchall()

    if not fac_rows:
        raise RuntimeError("No active verified/candidate emergency facilities found")

    fac_map = {f["road_node_id"]: f["id"] for f in fac_rows}
    facility_node_ids = list(fac_map.keys())
    print(f"Active emergency facilities: {len(fac_rows)} (node IDs: {facility_node_ids})")

    # 4. Filter valid origins for graph routing
    valid_origins = [o for o in origins if o["snap_valid"] and o["road_node_id"] is not None]
    valid_origin_nodes = list({o["road_node_id"] for o in valid_origins})
    print(f"Valid snapped origins: {len(valid_origins)} ({len(valid_origin_nodes)} unique road nodes)")

    # 5. Many-to-many Dijkstra routing via pgRouting
    # Build edges SQL dynamically: for baseline (sc_kind == 'baseline'), no edge impacts
    if sc["scenario_kind"] == "baseline":
        edges_sql = (
            "select id, source, target, cost_s as cost, reverse_cost_s as reverse_cost "
            "from gis.road_edges where area_id = " + str(area_id)
        )
    else:
        edges_sql = (
            f"select id, source, target, "
            f"case when exists ("
            f"  select 1 from gis.scenario_edge_impacts i "
            f"  where i.edge_id = e.id and i.scenario_id = {scenario_id} and i.is_closed"
            f") then -1.0 else cost_s end as cost, "
            f"case when exists ("
            f"  select 1 from gis.scenario_edge_impacts i "
            f"  where i.edge_id = e.id and i.scenario_id = {scenario_id} and i.is_closed"
            f") then -1.0 else reverse_cost_s end as reverse_cost "
            f"from gis.road_edges e where area_id = {area_id}"
        )

    # Execute many-to-many Dijkstra
    # Returns rows with start_vid, end_vid, edge = -1, agg_cost = total travel time
    pgr_rows = conn.execute(
        """
        select
            d.start_vid as origin_node,
            d.end_vid as facility_node,
            d.agg_cost as travel_time_s
        from pgr_dijkstra(
            %s,
            %s::bigint[],
            %s::bigint[],
            directed := true
        ) d
        where d.edge = -1
        order by d.start_vid, d.agg_cost asc;
        """,
        (edges_sql, valid_origin_nodes, facility_node_ids),
    ).fetchall()

    # Find nearest facility (minimum travel time) per origin road node
    node_nearest: dict[int, dict] = {}
    for r in pgr_rows:
        onode = r["origin_node"]
        if onode not in node_nearest:
            node_nearest[onode] = {
                "facility_id": fac_map[r["facility_node"]],
                "facility_node": r["facility_node"],
                "travel_time_s": float(r["travel_time_s"]),
            }

    print(f"Origins reaching a facility: {len(node_nearest)} / {len(valid_origin_nodes)} nodes")

    # 6. Build records for every origin in the dataset
    accessibility_rows = []
    stats = {
        "total_origins": total_origins,
        "total_population": total_population,
        "reachable_origins": 0,
        "reachable_population": 0,
        "pop_within_15min": 0,
        "pop_within_30min": 0,
        "pop_within_45min": 0,
        "pop_beyond_15min_or_unreachable": 0,
        "network_unreachable_origins": 0,
        "network_unreachable_population": 0,
        "invalid_snap_origins": 0,
        "invalid_snap_population": 0,
        "travel_times": [],
    }

    for o in origins:
        orig_id = o["id"]
        pop = o["population"]

        if not o["snap_valid"]:
            # Beyond maximum network snap distance
            accessibility_rows.append((
                scenario_id, orig_id, None, None, False, pop,
                "invalid_snap", False, False, False,
            ))
            stats["invalid_snap_origins"] += 1
            stats["invalid_snap_population"] += pop
            stats["pop_beyond_15min_or_unreachable"] += pop

        elif o["road_node_id"] in node_nearest:
            # Reachable
            nearest = node_nearest[o["road_node_id"]]
            tt_s = nearest["travel_time_s"]
            fac_id = nearest["facility_id"]
            t15 = tt_s <= 900.0
            t30 = tt_s <= 1800.0
            t45 = tt_s <= 2700.0

            accessibility_rows.append((
                scenario_id, orig_id, fac_id, round(tt_s, 2), True, pop,
                "reachable", t15, t30, t45,
            ))
            stats["reachable_origins"] += 1
            stats["reachable_population"] += pop
            stats["travel_times"].append(tt_s)
            if t15:
                stats["pop_within_15min"] += pop
            else:
                stats["pop_beyond_15min_or_unreachable"] += pop
            if t30:
                stats["pop_within_30min"] += pop
            if t45:
                stats["pop_within_45min"] += pop

        else:
            # Valid snap but network unreachable in directed graph
            accessibility_rows.append((
                scenario_id, orig_id, None, None, False, pop,
                "network_unreachable", False, False, False,
            ))
            stats["network_unreachable_origins"] += 1
            stats["network_unreachable_population"] += pop
            stats["pop_beyond_15min_or_unreachable"] += pop

    # Calculate travel time percentiles for reachable population
    tts = sorted(stats["travel_times"])
    stats["median_travel_time_s"] = round(tts[len(tts) // 2], 1) if tts else None
    stats["p90_travel_time_s"] = round(tts[int(len(tts) * 0.9)], 1) if tts else None

    # RECONCILIATION CHECK: Sum of mutually exclusive categories equals total population
    reconciled_sum = (
        stats["reachable_population"]
        + stats["network_unreachable_population"]
        + stats["invalid_snap_population"]
    )
    assert reconciled_sum == total_population, (
        f"Population reconciliation failed: {reconciled_sum} != {total_population}"
    )

    print(
        f"Results for '{sc['name']}':\n"
        f"  Total modeled population: {total_population:,}\n"
        f"  Reachable population:     {stats['reachable_population']:,} "
        f"({stats['reachable_population']/total_population*100:.1f}%)\n"
        f"    - within 15 min:        {stats['pop_within_15min']:,}\n"
        f"    - within 30 min:        {stats['pop_within_30min']:,}\n"
        f"    - within 45 min:        {stats['pop_within_45min']:,}\n"
        f"  Network unreachable:      {stats['network_unreachable_population']:,} "
        f"({stats['network_unreachable_origins']} origins)\n"
        f"  Invalid snap (fringe):    {stats['invalid_snap_population']:,} "
        f"({stats['invalid_snap_origins']} origins)\n"
        f"  Median travel time:       {stats['median_travel_time_s']} s\n"
        f"  Reconciliation:           {reconciled_sum:,} == {total_population:,} (EXACT MATCH)"
    )

    if dry_run:
        print("DRY RUN — no changes written.")
        return stats

    # Persist in database
    conn.execute(
        "delete from gis.scenario_accessibility where scenario_id = %s",
        (scenario_id,),
    )

    with conn.cursor().copy(
        """
        copy gis.scenario_accessibility(
            scenario_id, origin_id, facility_id, travel_time_s, reachable,
            population, status_category, threshold_15min, threshold_30min, threshold_45min
        ) from stdin
        """
    ) as cp:
        for row in accessibility_rows:
            cp.write_row(row)

    print(f"Committed {len(accessibility_rows)} accessibility records for scenario {scenario_id}.")
    return stats


def run_all_scenarios(area_id: int, dsn: str, dry_run: bool = False) -> None:
    with connect(dsn, row_factory=dict_row) as conn:
        scenarios = conn.execute(
            "select id, name, scenario_kind from gis.flood_scenarios where area_id = %s order by id",
            (area_id,),
        ).fetchall()

        if not scenarios:
            sys.exit(f"No scenarios found for area_id={area_id}")

        all_stats = {}
        for sc in scenarios:
            stats = compute_scenario_accessibility(
                scenario_id=sc["id"],
                area_id=area_id,
                conn=conn,
                dry_run=dry_run,
            )
            all_stats[sc["id"]] = stats

        # Compare baseline vs flood scenario if both exist
        base_id = next((s["id"] for s in scenarios if s["scenario_kind"] == "baseline"), None)
        flood_id = next((s["id"] for s in scenarios if s["scenario_kind"] == "hazard_polygon"), None)

        if base_id and flood_id and base_id in all_stats and flood_id in all_stats:
            b_stats = all_stats[base_id]
            f_stats = all_stats[flood_id]

            lost_15min = b_stats["pop_within_15min"] - f_stats["pop_within_15min"]
            newly_unreachable = f_stats["network_unreachable_population"] - b_stats["network_unreachable_population"]

            print("\n" + "=" * 60)
            print("BASELINE VS FLOOD ACCESSIBILITY COMPARISON")
            print("=" * 60)
            print(f"Population losing 15-min emergency access: {lost_15min:,}")
            print(f"Population becoming newly unreachable:     {newly_unreachable:,}")
            print(f"Baseline median travel time:              {b_stats['median_travel_time_s']} s")
            print(f"Flood scenario median travel time:         {f_stats['median_travel_time_s']} s")
            print("=" * 60)

        if not dry_run:
            # Log run
            conn.execute(
                "insert into gis.processing_runs(pipeline, area_id, status, finished_at, row_counts) "
                "values(%s, %s, 'success', now(), %s)",
                (
                    "compute_population_accessibility",
                    area_id,
                    json.dumps({
                        "scenarios_evaluated": len(scenarios),
                        "total_origins_per_scenario": all_stats[scenarios[0]["id"]]["total_origins"],
                        "total_modeled_population": all_stats[scenarios[0]["id"]]["total_population"],
                    }),
                ),
            )
            conn.commit()
            print("Accessibility processing run logged successfully.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--area-id", type=int, default=1)
    p.add_argument("--confirm-write", action="store_true")
    args = p.parse_args()

    dsn = os.environ.get("DATABASE_URL")
    if not dsn and args.confirm_write:
        sys.exit("DATABASE_URL is required for --confirm-write")

    run_all_scenarios(
        area_id=args.area_id,
        dsn=dsn or "",
        dry_run=not args.confirm_write,
    )


if __name__ == "__main__":
    main()
