import json
import os
from contextlib import contextmanager
from typing import Literal
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from psycopg import connect
from psycopg.rows import dict_row

app = FastAPI(title="Flood-Aware Emergency Access API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(",")], allow_methods=["GET"], allow_headers=["*"])

@contextmanager
def db():
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise HTTPException(503, "DATABASE_URL is not configured")
    try:
        with connect(dsn, row_factory=dict_row, connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute("set statement_timeout = '8s'")
            yield conn
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "Database unavailable") from exc

def fetch_all(query, params=()):
    with db() as conn:
        return conn.execute(query, params).fetchall()

@app.get("/api/health")
def health():
    return {"status": "ok", "database_configured": bool(os.getenv("DATABASE_URL"))}

@app.get("/api/study-areas")
def study_areas():
    return fetch_all("select id,name from gis.study_areas order by id")

@app.get("/api/facilities")
def facilities(area_id: int=Query(ge=1), facility_type: Literal["hospital", "shelter", "fire_station"] | None=None):
    rows=fetch_all("""select id,name,facility_type,is_active,road_node_id,
      extensions.st_y(geom) lat,extensions.st_x(geom) lon
      from gis.facilities where area_id=%s and (%s::text is null or facility_type=%s)
      order by name limit 500""",(area_id,facility_type,facility_type))
    return rows

@app.get("/api/scenarios")
def scenarios(area_id: int=Query(ge=1)):
    return fetch_all("select id,name,description,threshold_m,status from gis.flood_scenarios where area_id=%s order by id",(area_id,))

@app.get("/api/roads")
def roads(area_id: int=Query(ge=1), limit:int=Query(1000,ge=1,le=3000)):
    rows=fetch_all("""select id,extensions.st_asgeojson(geom) geometry from gis.road_edges
      where area_id=%s order by id limit %s""",(area_id,limit))
    return {"type":"FeatureCollection","features":[{"type":"Feature","properties":{"id":r["id"]},"geometry":json.loads(r["geometry"])} for r in rows]}

@app.get("/api/scenarios/{scenario_id}/closed-roads")
def closed_roads(scenario_id: int):
    rows=fetch_all("""select e.id,i.depth_m,extensions.st_asgeojson(e.geom) geometry
       from gis.scenario_edge_impacts i join gis.road_edges e on e.id=i.edge_id
       where i.scenario_id=%s and i.is_closed limit 3000""",(scenario_id,))
    return {"type":"FeatureCollection","features":[{"type":"Feature","properties":{"id":r["id"],"depth_m":r["depth_m"]},"geometry":json.loads(r["geometry"])} for r in rows]}

@app.get("/api/routes")
def route(origin_node_id: int=Query(ge=1), destination_node_id: int=Query(ge=1), scenario_id: int | None=Query(default=None,ge=1)):
    with db() as conn:
        rows=conn.execute("select seq,path_seq,node,edge,cost,agg_cost from gis.route_edges(%s,%s,%s)",(origin_node_id,destination_node_id,scenario_id)).fetchall()
        ids=[r["edge"] for r in rows if r["edge"]>=0]
        if not ids:
            return {"reachable": origin_node_id==destination_node_id,"travel_time_s":0 if origin_node_id==destination_node_id else None,"geometry":None}
        segments=conn.execute("select id,extensions.st_asgeojson(geom) geometry from gis.road_edges where id=any(%s)",(ids,)).fetchall()
    return {"reachable":True,"travel_time_s":sum(r["cost"] for r in rows if r["edge"]>=0),"geometry":{"type":"GeometryCollection","geometries":[json.loads(r["geometry"]) for r in segments]}}

@app.get("/api/scenarios/{scenario_id}/impact")
def impact(scenario_id:int):
    rows=fetch_all("""select count(*) origin_count,coalesce(sum(population),0) population,
        coalesce(sum(population) filter(where not reachable),0) unreachable_population,
        coalesce(sum(population) filter(where travel_time_s > 900 or not reachable),0) beyond_15min_population
        from gis.scenario_accessibility where scenario_id=%s""",(scenario_id,))
    return rows[0]
