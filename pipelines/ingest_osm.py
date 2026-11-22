"""Offline ETL. Requires a dedicated migrated database. Does not touch existing Supabase projects."""
import argparse
import os
import osmnx as ox
from psycopg import connect
from shapely.geometry import LineString, Point
from shapely import wkb

# Deliberately small Houston pilot; coordinates are [west,south,east,north].
BBOX = (-95.399, 29.746, -95.369, 29.774)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--area', default='Houston Downtown Pilot')
    parser.add_argument('--confirm-write', action='store_true')
    args = parser.parse_args()
    G = ox.graph_from_bbox(bbox=(BBOX[0],BBOX[1],BBOX[2],BBOX[3]), network_type='drive', simplify=True)
    G = ox.routing.add_edge_speeds(G)
    G = ox.routing.add_edge_travel_times(G)
    print(f'Downloaded {len(G.nodes)} nodes / {len(G.edges)} directed edges')
    if not args.confirm_write:
        print('Dry run. Pass --confirm-write with a dedicated DATABASE_URL to load.'); return
    dsn = os.environ['DATABASE_URL']
    with connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute('insert into gis.study_areas(name) values (%s) returning id', (args.area,))
            area_id=cur.fetchone()[0]
            node_rows=[]
            for n,attrib in G.nodes(data=True):
                node_rows.append((int(n),area_id,float(attrib['x']),float(attrib['y'])))
            with cur.copy('copy gis.road_nodes(id,area_id,geom) from stdin') as cp:
                for node_id,area_id,x,y in node_rows:
                    cp.write_row((node_id,area_id,f'SRID=4326;POINT({x} {y})'))
            edge_rows=[]
            for u,v,k,d in G.edges(keys=True,data=True):
                geom=d.get('geometry') or LineString([(G.nodes[u]['x'],G.nodes[u]['y']),(G.nodes[v]['x'],G.nodes[v]['y'])])
                # Each directed OSMnx arc is stored separately. Reverse travel is prohibited for that arc.
                edge_rows.append((area_id,str(d.get('osmid','')),int(u),int(v),float(d['length']),max(0.01,float(d['travel_time'])),-1,geom.wkt))
            with cur.copy('copy gis.road_edges(area_id,osm_way_id,source,target,length_m,cost_s,reverse_cost_s,geom) from stdin') as cp:
                for area_id,osm,u,v,length,cost,reverse,wkt in edge_rows:
                    cp.write_row((area_id,osm,u,v,length,cost,reverse,f'SRID=4326;{wkt}'))
            print(f'Loaded area {area_id}; {len(edge_rows)} directed arcs')

if __name__=='__main__': main()
