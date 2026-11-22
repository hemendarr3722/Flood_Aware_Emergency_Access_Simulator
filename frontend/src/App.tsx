import React, { useEffect, useState } from 'react';
import { Navbar } from './components/Navbar';
import { Sidebar } from './components/Sidebar';
import { MapComponent } from './components/MapComponent';
import {
  StudyArea,
  StudyAreaSummary,
  Scenario,
  ScenarioImpact,
  Facility,
  CompareResult,
  OriginFeatureProperties,
} from './types';

const API_BASE = import.meta.env.VITE_API_URL ?? (import.meta.env.DEV ? 'http://localhost:8000' : '');

export const App: React.FC = () => {
  const [areas, setAreas] = useState<StudyArea[]>([]);
  const [selectedAreaId, setSelectedAreaId] = useState<number>(1);
  const [studyAreaSummary, setStudyAreaSummary] = useState<StudyAreaSummary | null>(null);

  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedScenarioId, setSelectedScenarioId] = useState<number>(2); // Default to flood scenario
  const [thresholdMinutes, setThresholdMinutes] = useState<number>(15);
  const [impact, setImpact] = useState<ScenarioImpact | null>(null);

  const [facilities, setFacilities] = useState<Facility[]>([]);
  const [roadsGeoJSON, setRoadsGeoJSON] = useState<any>(null);
  const [affectedRoadsGeoJSON, setAffectedRoadsGeoJSON] = useState<any>(null);
  const [originsGeoJSON, setOriginsGeoJSON] = useState<any>(null);

  const [routeComparison, setRouteComparison] = useState<CompareResult | null>(null);
  const [selectedOrigin, setSelectedOrigin] = useState<OriginFeatureProperties | null>(null);
  const [apiStatus, setApiStatus] = useState<'checking' | 'healthy' | 'error'>('checking');

  const [layerVisibility, setLayerVisibility] = useState({
    roads: true,
    affectedRoads: true,
    facilities: true,
    origins: true,
    routes: true,
  });

  const handleToggleLayer = (layer: keyof typeof layerVisibility) => {
    setLayerVisibility((prev) => ({
      ...prev,
      [layer]: !prev[layer],
    }));
  };

  // 1. Initial Load: Check Health & Fetch Study Areas
  useEffect(() => {
    fetch(`${API_BASE}/api/health`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(() => setApiStatus('healthy'))
      .catch(() => setApiStatus('error'));

    fetch(`${API_BASE}/api/study-areas`)
      .then((r) => r.json())
      .then((data: StudyArea[]) => {
        if (data && data.length > 0) {
          setAreas(data);
          setSelectedAreaId(data[0].id);
        }
      })
      .catch((err) => console.error('Failed to load study areas:', err));
  }, []);

  // 2. Load Study Area Summary & Facilities & Base Roads
  useEffect(() => {
    if (!selectedAreaId) return;

    fetch(`${API_BASE}/api/study-areas/${selectedAreaId}/summary`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setStudyAreaSummary(data))
      .catch((err) => console.error('Failed to load study area summary:', err));

    fetch(`${API_BASE}/api/facilities?area_id=${selectedAreaId}&status=all`)
      .then((r) => (r.ok ? r.json() : []))
      .then((data: Facility[]) => setFacilities(data))
      .catch((err) => console.error('Failed to load facilities:', err));

    fetch(`${API_BASE}/api/roads?area_id=${selectedAreaId}&limit=3000`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setRoadsGeoJSON(data))
      .catch((err) => console.error('Failed to load roads:', err));

    fetch(`${API_BASE}/api/scenarios?area_id=${selectedAreaId}`)
      .then((r) => (r.ok ? r.json() : []))
      .then((data: Scenario[]) => {
        setScenarios(data);
        if (data.length > 1) {
          setSelectedScenarioId(data[1].id); // Flood scenario 2
        } else if (data.length > 0) {
          setSelectedScenarioId(data[0].id);
        }
      })
      .catch((err) => console.error('Failed to load scenarios:', err));
  }, [selectedAreaId]);

  // 3. Load Scenario Impact & Affected Roads & Origins
  useEffect(() => {
    if (!selectedScenarioId) return;

    fetch(`${API_BASE}/api/scenarios/${selectedScenarioId}/impact?threshold_minutes=${thresholdMinutes}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setImpact(data))
      .catch((err) => console.error('Failed to load scenario impact:', err));

    fetch(`${API_BASE}/api/scenarios/${selectedScenarioId}/affected-roads`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setAffectedRoadsGeoJSON(data))
      .catch((err) => console.error('Failed to load affected roads:', err));

    fetch(`${API_BASE}/api/scenarios/${selectedScenarioId}/accessibility-origins?threshold_minutes=${thresholdMinutes}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => setOriginsGeoJSON(data))
      .catch((err) => console.error('Failed to load accessibility origins:', err));
  }, [selectedScenarioId, thresholdMinutes]);

  // 4. Compute Route Comparison
  const handleRunRoute = (
    origin: number,
    dest: number | null,
    facilityType: 'hospital' | 'shelter' | 'fire_station' | null
  ) => {
    const params = new URLSearchParams({
      origin_node_id: origin.toString(),
      scenario_id: selectedScenarioId.toString(),
    });

    if (dest !== null) {
      params.append('destination_node_id', dest.toString());
    } else if (facilityType !== null) {
      params.append('facility_type', facilityType);
    }

    fetch(`${API_BASE}/api/compare/routes?${params.toString()}`)
      .then((r) => (r.ok ? r.json() : Promise.reject('Route comparison failed')))
      .then((data: CompareResult) => setRouteComparison(data))
      .catch((err) => {
        console.error('Route evaluation error:', err);
        alert('Could not compute route between chosen nodes in this scenario.');
      });
  };

  const handleClearRoute = () => {
    setRouteComparison(null);
  };

  return (
    <div className="app-layout">
      <Navbar
        areas={areas}
        selectedAreaId={selectedAreaId}
        onSelectArea={setSelectedAreaId}
        apiStatus={apiStatus}
      />
      <div className="main-viewport">
        <Sidebar
          scenarios={scenarios}
          selectedScenarioId={selectedScenarioId}
          onSelectScenario={setSelectedScenarioId}
          thresholdMinutes={thresholdMinutes}
          onSelectThreshold={setThresholdMinutes}
          impact={impact}
          facilities={facilities}
          studyAreaSummary={studyAreaSummary}
          routeComparison={routeComparison}
          onRunRoute={handleRunRoute}
          onClearRoute={handleClearRoute}
          selectedOrigin={selectedOrigin}
          onCloseOriginDetail={() => setSelectedOrigin(null)}
          layerVisibility={layerVisibility}
          onToggleLayer={handleToggleLayer}
        />
        <MapComponent
          roadsGeoJSON={roadsGeoJSON}
          affectedRoadsGeoJSON={affectedRoadsGeoJSON}
          facilities={facilities}
          originsGeoJSON={originsGeoJSON}
          routeComparison={routeComparison}
          onSelectOrigin={(origin) => setSelectedOrigin(origin)}
          layerVisibility={layerVisibility}
        />
      </div>
    </div>
  );
};
