export interface StudyArea {
  id: number;
  name: string;
  created_at?: string;
}

export interface StudyAreaSummary {
  id: number;
  name: string;
  description: string;
  created_at: string;
  bounds: {
    min_lon: number;
    min_lat: number;
    max_lon: number;
    max_lat: number;
  };
  metrics: {
    total_road_nodes: number;
    total_road_edges: number;
    total_road_length_km: number;
    total_facilities: number;
    verified_facilities: number;
    candidate_facilities: number;
    excluded_facilities: number;
    total_population_origins: number;
    modeled_population: number;
    snapped_pilot_population: number;
    available_scenarios: number;
  };
  disclaimer: string;
}

export interface Facility {
  id: number;
  name: string;
  facility_type: 'hospital' | 'shelter' | 'fire_station';
  is_active: boolean;
  validation_status: 'candidate' | 'verified' | 'excluded';
  exclusion_reason?: string | null;
  snap_distance_m?: number | null;
  road_node_id?: number | null;
  lat: number;
  lon: number;
}

export interface Scenario {
  id: number;
  area_id: number;
  name: string;
  description?: string;
  scenario_kind: 'baseline' | 'hazard_polygon' | 'depth_grid';
  threshold_m?: number | null;
  status: string;
  affected_road_count?: number;
  modeling_rule?: string;
  disclaimer?: string;
}

export interface ScenarioImpact {
  scenario_id: number;
  threshold_minutes: number;
  total_modeled_population: number;
  total_origins: number;
  reachable_population: number;
  within_threshold_population: number;
  beyond_threshold_population: number;
  network_unreachable_population: number;
  invalid_snap_population: number;
  population_losing_threshold_access: number;
  median_travel_time_s: number | null;
  p90_travel_time_s: number | null;
  reconciliation: {
    sum_categories: number;
    matches_total: boolean;
  };
  modeling_disclaimer: string;
}

export interface RouteEdgeItem {
  edge_id: number;
  source: number;
  target: number;
  length_m: number;
  cost_s: number;
  highway?: string | null;
}

export interface RouteResult {
  reachable: boolean;
  travel_time_s: number | null;
  edge_count: number;
  edges: RouteEdgeItem[];
  geometry: {
    type: 'LineString';
    coordinates: [number, number][];
  } | null;
  facility?: {
    id: number;
    name: string;
    type: string;
    node_id: number;
  } | null;
  algorithm_version?: string;
}

export interface CompareResult {
  status: 'unaffected' | 'detoured' | 'isolated';
  delay_s: number | null;
  delay_pct: number | null;
  baseline: RouteResult;
  disrupted: RouteResult;
  modeling_disclaimer: string;
}

export interface OriginFeatureProperties {
  origin_id: number;
  geoid: string;
  population: number;
  reachable: boolean;
  travel_time_s: number | null;
  status_category: 'within_threshold' | 'beyond_threshold' | 'network_unreachable' | 'invalid_snap';
  within_threshold: boolean;
  facility_name?: string | null;
  facility_type?: string | null;
}
