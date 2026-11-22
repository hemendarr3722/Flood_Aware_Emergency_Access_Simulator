"""Illustration of depth extraction. Assumes raster contains meters of inundation depth,
not water-surface elevation. Confirm CRS, nodata, raster semantics and roadway elevation before using.
CSV input columns: edge_id,wkt (EPSG:4326). Outputs edge_id,depth_m."""
import argparse,csv
import rasterio
from shapely import wkt
from shapely.ops import transform
from pyproj import Transformer

p=argparse.ArgumentParser()
p.add_argument('--raster',required=True)
p.add_argument('--edges-csv',required=True)
p.add_argument('--output',default='road_depths.csv')
a=p.parse_args()
with rasterio.open(a.raster) as src, open(a.edges_csv,newline='') as f, open(a.output,'w',newline='') as out:
    if not src.crs: raise ValueError('Raster must have known CRS')
    transformer=Transformer.from_crs('EPSG:4326',src.crs,always_xy=True).transform
    writer=csv.writer(out);writer.writerow(['edge_id','depth_m'])
    for item in csv.DictReader(f):
        geom=transform(transformer,wkt.loads(item['wkt']))
        distances=[geom.length*i/20 for i in range(21)]
        xy=[(geom.interpolate(d).x,geom.interpolate(d).y) for d in distances]
        samples=[float(s[0]) for s in src.sample(xy,masked=True)]
        valid=[d for d in samples if d>=0 and d<1e9 and d==d and (src.nodata is None or d!=src.nodata)]
        writer.writerow([item['edge_id'],max(valid) if valid else ''])
