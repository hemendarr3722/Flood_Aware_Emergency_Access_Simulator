import React, { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { Facility, CompareResult, OriginFeatureProperties } from '../types';

interface MapComponentProps {
  roadsGeoJSON: any;
  affectedRoadsGeoJSON: any;
  facilities: Facility[];
  originsGeoJSON: any;
  routeComparison: CompareResult | null;
  onSelectOrigin: (origin: OriginFeatureProperties) => void;
  layerVisibility: {
    roads: boolean;
    affectedRoads: boolean;
    facilities: boolean;
    origins: boolean;
    routes: boolean;
  };
}

const emptyFC = { type: 'FeatureCollection', features: [] };

const cartoStyle: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    'carto-positron': {
      type: 'raster',
      tiles: [
        'https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png',
        'https://b.basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png',
        'https://c.basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png',
      ],
      tileSize: 256,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
    },
  },
  layers: [
    {
      id: 'carto-positron-layer',
      type: 'raster',
      source: 'carto-positron',
      minzoom: 0,
      maxzoom: 20,
    },
  ],
};

export const MapComponent: React.FC<MapComponentProps> = ({
  roadsGeoJSON,
  affectedRoadsGeoJSON,
  facilities,
  originsGeoJSON,
  routeComparison,
  onSelectOrigin,
  layerVisibility,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const isLoadedRef = useRef(false);

  // Initialize MapLibre Map
  useEffect(() => {
    if (!containerRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: cartoStyle,
      center: [-95.365, 29.755], // Downtown Houston Pilot center
      zoom: 14,
    });

    map.addControl(new maplibregl.NavigationControl(), 'top-right');
    map.addControl(new maplibregl.ScaleControl(), 'bottom-left');

    map.on('load', () => {
      isLoadedRef.current = true;

      // 1. Normal Roads Source & Layer
      map.addSource('roads-source', {
        type: 'geojson',
        data: emptyFC as any,
      });
      map.addLayer({
        id: 'roads-layer',
        type: 'line',
        source: 'roads-source',
        paint: {
          'line-color': '#94a3b8',
          'line-width': ['interpolate', ['linear'], ['zoom'], 12, 1.5, 16, 3],
          'line-opacity': 0.8,
        },
      });

      // 2. Affected Roads Source & Layer (FEMA SFHA)
      map.addSource('affected-roads-source', {
        type: 'geojson',
        data: emptyFC as any,
      });
      map.addLayer({
        id: 'affected-roads-layer',
        type: 'line',
        source: 'affected-roads-source',
        paint: {
          'line-color': '#dc2626',
          'line-width': ['interpolate', ['linear'], ['zoom'], 12, 3.5, 16, 6],
          'line-dasharray': [2, 1],
          'line-opacity': 0.9,
        },
      });

      // 3. Census Origins Source & Layer
      map.addSource('origins-source', {
        type: 'geojson',
        data: emptyFC as any,
      });
      map.addLayer({
        id: 'origins-layer',
        type: 'circle',
        source: 'origins-source',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 11, 4, 15, 8],
          'circle-color': [
            'match',
            ['get', 'status_category'],
            'within_threshold',
            '#10b981',
            'beyond_threshold',
            '#f59e0b',
            'network_unreachable',
            '#ef4444',
            /* default / invalid_snap */ '#94a3b8',
          ],
          'circle-stroke-width': 1.5,
          'circle-stroke-color': '#ffffff',
          'circle-opacity': 0.9,
        },
      });

      // 4. Facilities Source & Layer
      map.addSource('facilities-source', {
        type: 'geojson',
        data: emptyFC as any,
      });
      map.addLayer({
        id: 'facilities-layer',
        type: 'circle',
        source: 'facilities-source',
        paint: {
          'circle-radius': ['interpolate', ['linear'], ['zoom'], 11, 6, 15, 11],
          'circle-color': [
            'match',
            ['get', 'validation_status'],
            'verified',
            '#059669',
            'candidate',
            '#0284c7',
            /* excluded */ '#6b7280',
          ],
          'circle-stroke-width': 2.5,
          'circle-stroke-color': '#ffffff',
        },
      });

      // 5. Baseline Route Source & Layer
      map.addSource('baseline-route-source', {
        type: 'geojson',
        data: emptyFC as any,
      });
      map.addLayer({
        id: 'baseline-route-layer',
        type: 'line',
        source: 'baseline-route-source',
        layout: {
          'line-join': 'round',
          'line-cap': 'round',
        },
        paint: {
          'line-color': '#16a34a',
          'line-width': 5,
          'line-opacity': 0.9,
        },
      });

      // 6. Disrupted Route Source & Layer
      map.addSource('disrupted-route-source', {
        type: 'geojson',
        data: emptyFC as any,
      });
      map.addLayer({
        id: 'disrupted-route-layer',
        type: 'line',
        source: 'disrupted-route-source',
        layout: {
          'line-join': 'round',
          'line-cap': 'round',
        },
        paint: {
          'line-color': '#d97706',
          'line-width': 6,
          'line-dasharray': [3, 2],
          'line-opacity': 0.95,
        },
      });

      // Cursors & Interactions
      map.on('mouseenter', 'origins-layer', () => {
        map.getCanvas().style.cursor = 'pointer';
      });
      map.on('mouseleave', 'origins-layer', () => {
        map.getCanvas().style.cursor = '';
      });

      map.on('click', 'origins-layer', (e) => {
        if (!e.features || !e.features[0]) return;
        const props = e.features[0].properties as OriginFeatureProperties;
        onSelectOrigin(props);
      });

      // Facility Popups
      map.on('click', 'facilities-layer', (e) => {
        if (!e.features || !e.features[0]) return;
        const props = e.features[0].properties;
        const coords = (e.features[0].geometry as any).coordinates.slice();
        new maplibregl.Popup()
          .setLngLat(coords)
          .setHTML(
            `<div style="font-family: sans-serif; font-size: 13px;">
              <strong>${props.name}</strong><br/>
              Type: <em>${props.facility_type}</em><br/>
              Status: <span style="font-weight: 600; color: ${
                props.validation_status === 'verified'
                  ? '#059669'
                  : props.validation_status === 'candidate'
                  ? '#0284c7'
                  : '#6b7280'
              }">${props.validation_status}</span><br/>
              ${props.exclusion_reason ? `<small style="color: #ef4444">${props.exclusion_reason}</small><br/>` : ''}
              Snap: ${props.snap_distance_m ? `${Number(props.snap_distance_m).toFixed(1)} m` : 'N/A'}
            </div>`
          )
          .addTo(map);
      });
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      isLoadedRef.current = false;
    };
  }, []);

  // Update Roads Source
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isLoadedRef.current) return;
    const src = map.getSource('roads-source') as maplibregl.GeoJSONSource | undefined;
    if (src) {
      src.setData(roadsGeoJSON || emptyFC);
    }
  }, [roadsGeoJSON]);

  // Update Affected Roads Source
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isLoadedRef.current) return;
    const src = map.getSource('affected-roads-source') as maplibregl.GeoJSONSource | undefined;
    if (src) {
      src.setData(affectedRoadsGeoJSON || emptyFC);
    }
  }, [affectedRoadsGeoJSON]);

  // Update Facilities Source
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isLoadedRef.current) return;
    const src = map.getSource('facilities-source') as maplibregl.GeoJSONSource | undefined;
    if (src) {
      const fc = {
        type: 'FeatureCollection',
        features: facilities.map((f) => ({
          type: 'Feature',
          properties: f,
          geometry: {
            type: 'Point',
            coordinates: [f.lon, f.lat],
          },
        })),
      };
      src.setData(fc as any);
    }
  }, [facilities]);

  // Update Origins Source
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isLoadedRef.current) return;
    const src = map.getSource('origins-source') as maplibregl.GeoJSONSource | undefined;
    if (src) {
      src.setData(originsGeoJSON || emptyFC);
    }
  }, [originsGeoJSON]);

  // Update Route Geometries
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isLoadedRef.current) return;

    const baseSrc = map.getSource('baseline-route-source') as maplibregl.GeoJSONSource | undefined;
    const floodSrc = map.getSource('disrupted-route-source') as maplibregl.GeoJSONSource | undefined;

    if (routeComparison?.baseline?.geometry && baseSrc) {
      baseSrc.setData({
        type: 'Feature',
        properties: {},
        geometry: routeComparison.baseline.geometry,
      } as any);
    } else if (baseSrc) {
      baseSrc.setData(emptyFC as any);
    }

    if (routeComparison?.disrupted?.geometry && floodSrc) {
      floodSrc.setData({
        type: 'Feature',
        properties: {},
        geometry: routeComparison.disrupted.geometry,
      } as any);
    } else if (floodSrc) {
      floodSrc.setData(emptyFC as any);
    }
  }, [routeComparison]);

  // Update Layer Visibility
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isLoadedRef.current) return;

    if (map.getLayer('roads-layer')) {
      map.setLayoutProperty('roads-layer', 'visibility', layerVisibility.roads ? 'visible' : 'none');
    }
    if (map.getLayer('affected-roads-layer')) {
      map.setLayoutProperty(
        'affected-roads-layer',
        'visibility',
        layerVisibility.affectedRoads ? 'visible' : 'none'
      );
    }
    if (map.getLayer('facilities-layer')) {
      map.setLayoutProperty(
        'facilities-layer',
        'visibility',
        layerVisibility.facilities ? 'visible' : 'none'
      );
    }
    if (map.getLayer('origins-layer')) {
      map.setLayoutProperty(
        'origins-layer',
        'visibility',
        layerVisibility.origins ? 'visible' : 'none'
      );
    }
    if (map.getLayer('baseline-route-layer')) {
      map.setLayoutProperty(
        'baseline-route-layer',
        'visibility',
        layerVisibility.routes ? 'visible' : 'none'
      );
    }
    if (map.getLayer('disrupted-route-layer')) {
      map.setLayoutProperty(
        'disrupted-route-layer',
        'visibility',
        layerVisibility.routes ? 'visible' : 'none'
      );
    }
  }, [layerVisibility]);

  return <div className="map-container" ref={containerRef} aria-label="Houston flood emergency access map" />;
};
