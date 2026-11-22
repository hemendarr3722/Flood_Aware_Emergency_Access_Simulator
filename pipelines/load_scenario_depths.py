"""Load previously reviewed road-level inundation depths as scenario impacts.
Depth is a raster-derived *model output*, not a verified real-time road closure.
Input CSV: edge_id,depth_m. Blank depth is unknown, not zero.
"""
import argparse,csv,os
from psycopg import connect
p=argparse.ArgumentParser()
p.add_argument('--area-id',type=int,required=True)
p.add_argument('--csv',required=True)
p.add_argument('--name',required=True)
p.add_argument('--threshold-m',type=float,required=True)
p.add_argument('--source',required=True,help='source title and vintage')
p.add_argument('--raster-uri',default=None)
p.add_argument('--confirm-write',action='store_true')
a=p.parse_args()
if a.threshold_m<0:raise ValueError('threshold-m must be nonnegative')
records=[]
with open(a.csv,newline='') as f:
    for row in csv.DictReader(f):
        depth=float(row['depth_m']) if row['depth_m'].strip() else None
        if depth is not None and depth<0:raise ValueError('Negative depth invalid')
        records.append((int(row['edge_id']),depth))
print(f'{len(records)} depth samples, {sum(d is None for _,d in records)} unknown')
if not a.confirm_write:print('Dry run; no database changes');raise SystemExit
with connect(os.environ['DATABASE_URL']) as conn:
    with conn.cursor() as cur:
        cur.execute('''insert into gis.flood_scenarios(area_id,name,raster_uri,raster_source,threshold_m,status)
          values(%s,%s,%s,%s,%s,'ready') returning id''',(a.area_id,a.name,a.raster_uri,a.source,a.threshold_m))
        scenario_id=cur.fetchone()[0]
        for edge_id,depth in records:
            # unknown depth stays open in routing; coverage uncertainty must be displayed separately
            cur.execute('''insert into gis.scenario_edge_impacts(scenario_id,edge_id,depth_m,is_closed)
              select %s,e.id,%s,%s from gis.road_edges e where e.id=%s and e.area_id=%s''',
              (scenario_id,depth, bool(depth is not None and depth>=a.threshold_m),edge_id,a.area_id))
print('Scenario',scenario_id,'loaded (not validated as real-world closures)')
