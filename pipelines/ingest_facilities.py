"""Offline OSM hospital/fire-station ETL. Shelters need an authoritative dataset; not invented here."""
import argparse
import os
import osmnx as ox
from psycopg import connect
from ingest_osm import BBOX

p=argparse.ArgumentParser()
p.add_argument('--area-id',type=int,required=True)
p.add_argument('--confirm-write',action='store_true')
a=p.parse_args()
tags={'amenity':['hospital','fire_station']}
features=ox.features_from_bbox(BBOX,tags)
facilities=[]
for idx,row in features.iterrows():
    kind=row.get('amenity')
    if kind not in ('hospital','fire_station'):continue
    geom=row.geometry
    if geom is None or geom.is_empty:continue
    point=geom if geom.geom_type=='Point' else geom.representative_point()
    name=row.get('name')
    if not isinstance(name,str) or not name.strip():name=f'Unnamed {kind.replace("_"," ")}'
    facilities.append((f'{idx[0]}/{idx[1]}',name,kind,point.x,point.y))
print(f'Extracted {len(facilities)} OSM facility features; no emergency-service verification performed')
if a.confirm_write:
    with connect(os.environ['DATABASE_URL']) as conn:
        # snap to graph nodes loaded in the specified study area; nearest by geographic distance
        with conn.cursor() as cur:
            for osm_id,name,kind,x,y in facilities:
                cur.execute('''select id from gis.road_nodes where area_id=%s
                    order by geom operator(extensions.<->) extensions.st_setsrid(extensions.st_makepoint(%s,%s),4326)
                    limit 1''',(a.area_id,x,y))
                found=cur.fetchone()
                if found is None:raise RuntimeError('No road nodes for chosen study area')
                cur.execute('''insert into gis.facilities(area_id,osm_id,name,facility_type,geom,road_node_id)
                  values(%s,%s,%s,%s,extensions.st_setsrid(extensions.st_makepoint(%s,%s),4326),%s)''',
                  (a.area_id,osm_id,name,kind,x,y,found[0]))
    print('Stored facilities. Verify hospitals provide emergency service before using for access analysis.')
else:
    print('Dry run only. Pass --confirm-write to load into a new dedicated database.')
