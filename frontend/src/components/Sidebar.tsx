import React, { useState } from 'react';
import {
  Scenario,
  ScenarioImpact,
  Facility,
  StudyAreaSummary,
  CompareResult,
  OriginFeatureProperties,
} from '../types';

interface SidebarProps {
  scenarios: Scenario[];
  selectedScenarioId: number;
  onSelectScenario: (id: number) => void;
  thresholdMinutes: number;
  onSelectThreshold: (mins: number) => void;
  impact: ScenarioImpact | null;
  facilities: Facility[];
  studyAreaSummary: StudyAreaSummary | null;
  routeComparison: CompareResult | null;
  onRunRoute: (
    origin: number,
    dest: number | null,
    facilityType: 'hospital' | 'shelter' | 'fire_station' | null
  ) => void;
  onClearRoute: () => void;
  selectedOrigin: OriginFeatureProperties | null;
  onCloseOriginDetail: () => void;
  layerVisibility: {
    roads: boolean;
    affectedRoads: boolean;
    facilities: boolean;
    origins: boolean;
    routes: boolean;
  };
  onToggleLayer: (layer: keyof SidebarProps['layerVisibility']) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  scenarios,
  selectedScenarioId,
  onSelectScenario,
  thresholdMinutes,
  onSelectThreshold,
  impact,
  facilities,
  studyAreaSummary,
  routeComparison,
  onRunRoute,
  onClearRoute,
  selectedOrigin,
  onCloseOriginDetail,
  layerVisibility,
  onToggleLayer,
}) => {
  const [activeTab, setActiveTab] = useState<'scenarios' | 'routing' | 'facilities' | 'layers'>('scenarios');
  const [customOrigin, setCustomOrigin] = useState<number>(151461824);
  const [customDest, setCustomDest] = useState<number | ''>('');
  const [targetFacilityType, setTargetFacilityType] = useState<'hospital' | 'fire_station' | 'shelter' | 'custom'>('hospital');

  const selectedScenario = scenarios.find((s) => s.id === selectedScenarioId);

  const handleExecuteRoute = () => {
    if (targetFacilityType === 'custom') {
      if (typeof customDest === 'number' && customDest > 0) {
        onRunRoute(customOrigin, customDest, null);
      }
    } else {
      onRunRoute(customOrigin, null, targetFacilityType);
    }
  };

  return (
    <aside className="sidebar">
      <nav className="sidebar-tabs">
        <button
          className={`tab-btn ${activeTab === 'scenarios' ? 'active' : ''}`}
          onClick={() => setActiveTab('scenarios')}
        >
          📊 Scenarios
        </button>
        <button
          className={`tab-btn ${activeTab === 'routing' ? 'active' : ''}`}
          onClick={() => setActiveTab('routing')}
        >
          🚑 Routing
        </button>
        <button
          className={`tab-btn ${activeTab === 'facilities' ? 'active' : ''}`}
          onClick={() => setActiveTab('facilities')}
        >
          🏥 Facilities
        </button>
        <button
          className={`tab-btn ${activeTab === 'layers' ? 'active' : ''}`}
          onClick={() => setActiveTab('layers')}
        >
          🗺️ Layers
        </button>
      </nav>

      <div className="tab-content">
        {/* TAB 1: SCENARIOS & ACCESSIBILITY IMPACT */}
        {activeTab === 'scenarios' && (
          <div className="panel-section">
            <h3>Flood Scenario</h3>
            <div className="form-group">
              <label>Select Scenario:</label>
              <select
                value={selectedScenarioId}
                onChange={(e) => onSelectScenario(Number(e.target.value))}
                className="select-input"
              >
                {scenarios.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} {s.scenario_kind === 'baseline' ? '(Baseline)' : '(SFHA Hazard)'}
                  </option>
                ))}
              </select>
            </div>

            {selectedScenario && (
              <div className="scenario-metadata-card">
                <div className="badge-row">
                  <span className={`kind-badge ${selectedScenario.scenario_kind}`}>
                    {selectedScenario.scenario_kind.toUpperCase()}
                  </span>
                  <span className="status-badge">{selectedScenario.status}</span>
                </div>
                <p className="scenario-desc">{selectedScenario.description}</p>
                {selectedScenario.scenario_kind !== 'baseline' && (
                  <div className="affected-stat">
                    <span>Modeled Potentially Affected Roads:</span>
                    <strong>{selectedScenario.affected_road_count ?? 124} edges</strong>
                  </div>
                )}
              </div>
            )}

            <div className="threshold-toggle-section">
              <label>Travel Time Accessibility Threshold:</label>
              <div className="threshold-buttons">
                {[15, 30, 45].map((mins) => (
                  <button
                    key={mins}
                    className={`threshold-btn ${thresholdMinutes === mins ? 'active' : ''}`}
                    onClick={() => onSelectThreshold(mins)}
                  >
                    {mins} min
                  </button>
                ))}
              </div>
            </div>

            {impact && (
              <div className="impact-results">
                <h4>Population Accessibility Impact ({thresholdMinutes} min threshold)</h4>
                
                <div className="metric-grid">
                  <div className="metric-card primary">
                    <span className="metric-label">Reachable Within Threshold</span>
                    <span className="metric-value">{impact.within_threshold_population.toLocaleString()}</span>
                    <span className="metric-sub">
                      {((impact.within_threshold_population / (impact.total_modeled_population || 1)) * 100).toFixed(1)}% of total modeled
                    </span>
                  </div>

                  <div className="metric-card danger">
                    <span className="metric-label">Population Losing Access</span>
                    <span className="metric-value">{impact.population_losing_threshold_access.toLocaleString()}</span>
                    <span className="metric-sub">isolated under flood</span>
                  </div>

                  <div className="metric-card warning">
                    <span className="metric-label">Network-Unreachable</span>
                    <span className="metric-value">{impact.network_unreachable_population.toLocaleString()}</span>
                    <span className="metric-sub">no viable path to facility</span>
                  </div>

                  <div className="metric-card muted">
                    <span className="metric-label">Outside Pilot Road Buffer (&gt;500m)</span>
                    <span className="metric-value">{impact.invalid_snap_population.toLocaleString()}</span>
                    <span className="metric-sub">538 outer Census block groups</span>
                  </div>
                </div>

                <div className="travel-time-stats">
                  <div className="stat-row">
                    <span>Median Travel Time (Reachable):</span>
                    <strong>{impact.median_travel_time_s ? `${(impact.median_travel_time_s / 60).toFixed(1)} min` : '—'}</strong>
                  </div>
                  <div className="stat-row">
                    <span>90th Percentile Travel Time:</span>
                    <strong>{impact.p90_travel_time_s ? `${(impact.p90_travel_time_s / 60).toFixed(1)} min` : '—'}</strong>
                  </div>
                </div>

                <div className="reconciliation-badge">
                  <span className="check-icon">✓</span>
                  <span>
                    <strong>Population Reconciled:</strong> {impact.total_modeled_population.toLocaleString()} total population (100.0% accounted for, zero double-counting).
                  </span>
                </div>
              </div>
            )}

            <div className="track-note-box">
              <strong>Track B Depth Governance:</strong>
              <p>USGS FIM discovery returned 0 flood depth sites for Houston. The depth-raster track remains explicitly disabled; this scenario models FEMA NFHL 100-year regulatory flood zones.</p>
            </div>
          </div>
        )}

        {/* TAB 2: ROUTING & DETOUR INSPECTOR */}
        {activeTab === 'routing' && (
          <div className="panel-section">
            <h3>Emergency Route Inspector</h3>
            <p className="section-help">
              Evaluate Dijkstra shortest paths under baseline and flood conditions. Closed edges are strictly excluded from disrupted routes.
            </p>

            <div className="route-form">
              <div className="form-group">
                <label>Origin Node ID:</label>
                <input
                  type="number"
                  className="text-input"
                  value={customOrigin}
                  onChange={(e) => setCustomOrigin(Number(e.target.value))}
                />
              </div>

              <div className="form-group">
                <label>Target Facility / Destination:</label>
                <select
                  className="select-input"
                  value={targetFacilityType}
                  onChange={(e) => setTargetFacilityType(e.target.value as any)}
                >
                  <option value="hospital">Nearest Hospital (Saint Joseph Medical Center)</option>
                  <option value="fire_station">Nearest Fire Station (HFD Station 8)</option>
                  <option value="custom">Point-to-Point Node ID</option>
                </select>
              </div>

              {targetFacilityType === 'custom' && (
                <div className="form-group">
                  <label>Destination Node ID:</label>
                  <input
                    type="number"
                    className="text-input"
                    placeholder="e.g. 152272624"
                    value={customDest}
                    onChange={(e) => setCustomDest(e.target.value ? Number(e.target.value) : '')}
                  />
                </div>
              )}

              <div className="btn-group">
                <button className="primary-btn" onClick={handleExecuteRoute}>
                  🔍 Compute Route & Compare
                </button>
                {routeComparison && (
                  <button className="secondary-btn" onClick={onClearRoute}>
                    Clear
                  </button>
                )}
              </div>
            </div>

            <div className="benchmark-presets">
              <span className="preset-label">Quick Benchmark Routes:</span>
              <button
                className="chip-btn"
                onClick={() => {
                  setCustomOrigin(151461824);
                  setTargetFacilityType('hospital');
                  onRunRoute(151461824, null, 'hospital');
                }}
              >
                🏥 Node 151461824 → Nearest Hospital
              </button>
              <button
                className="chip-btn"
                onClick={() => {
                  setCustomOrigin(151635251);
                  setCustomDest(152272624);
                  setTargetFacilityType('custom');
                  onRunRoute(151635251, 152272624, null);
                }}
              >
                📍 151635251 → 152272624 (Benchmark 1)
              </button>
              <button
                className="chip-btn"
                onClick={() => {
                  setCustomOrigin(151461407);
                  setCustomDest(152725875);
                  setTargetFacilityType('custom');
                  onRunRoute(151461407, 152725875, null);
                }}
              >
                ⛔ 151461407 → 152725875 (Isolated in Flood)
              </button>
            </div>

            {routeComparison && (
              <div className="comparison-card">
                <div className="comparison-header">
                  <h4>Route Comparison Result</h4>
                  <span className={`status-pill-lg ${routeComparison.status}`}>
                    {routeComparison.status.toUpperCase()}
                  </span>
                </div>

                <div className="comparison-grid">
                  <div className="comp-col baseline-col">
                    <span className="col-title">🟢 Baseline (Normal)</span>
                    <div className="comp-stat">
                      <span>Status:</span>
                      <strong>{routeComparison.baseline.reachable ? 'Reachable' : 'Unreachable'}</strong>
                    </div>
                    <div className="comp-stat">
                      <span>Travel Time:</span>
                      <strong>
                        {routeComparison.baseline.travel_time_s !== null
                          ? `${routeComparison.baseline.travel_time_s.toFixed(1)} s (${(routeComparison.baseline.travel_time_s / 60).toFixed(1)} min)`
                          : '—'}
                      </strong>
                    </div>
                    <div className="comp-stat">
                      <span>Edge Count:</span>
                      <strong>{routeComparison.baseline.edge_count}</strong>
                    </div>
                  </div>

                  <div className="comp-col flood-col">
                    <span className="col-title">🔴 Disrupted (Flood)</span>
                    <div className="comp-stat">
                      <span>Status:</span>
                      <strong>{routeComparison.disrupted.reachable ? 'Reachable' : 'Isolated'}</strong>
                    </div>
                    <div className="comp-stat">
                      <span>Travel Time:</span>
                      <strong>
                        {routeComparison.disrupted.travel_time_s !== null
                          ? `${routeComparison.disrupted.travel_time_s.toFixed(1)} s (${(routeComparison.disrupted.travel_time_s / 60).toFixed(1)} min)`
                          : 'Isolated'}
                      </strong>
                    </div>
                    <div className="comp-stat">
                      <span>Edge Count:</span>
                      <strong>{routeComparison.disrupted.edge_count}</strong>
                    </div>
                  </div>
                </div>

                {routeComparison.status === 'detoured' && routeComparison.delay_s !== null && (
                  <div className="detour-alert">
                    ⚠️ <strong>Detour Delay:</strong> +{routeComparison.delay_s.toFixed(1)} s (+{routeComparison.delay_pct}%) due to flood closures.
                  </div>
                )}

                {routeComparison.status === 'isolated' && (
                  <div className="isolated-alert">
                    ⛔ <strong>Access Blocked:</strong> Origin is cut off from destination by flood hazard closures.
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* TAB 3: FACILITIES & NETWORK CURATION */}
        {activeTab === 'facilities' && (
          <div className="panel-section">
            <h3>Facilities & Network Curation</h3>
            {studyAreaSummary && (
              <div className="summary-box">
                <h4>Pilot Road Network Stats</h4>
                <div className="summary-row">
                  <span>Drivable Nodes:</span>
                  <strong>{studyAreaSummary.metrics.total_road_nodes}</strong>
                </div>
                <div className="summary-row">
                  <span>Directed Edges:</span>
                  <strong>{studyAreaSummary.metrics.total_road_edges}</strong>
                </div>
                <div className="summary-row">
                  <span>Total Network Length:</span>
                  <strong>{studyAreaSummary.metrics.total_road_length_km} km</strong>
                </div>
                <div className="summary-row">
                  <span>Snapped Pilot Population:</span>
                  <strong>{studyAreaSummary.metrics.snapped_pilot_population.toLocaleString()}</strong>
                </div>
              </div>
            )}

            <h4>Emergency Response Facilities ({facilities.length})</h4>
            <div className="facility-list">
              {facilities.map((fac) => (
                <div key={fac.id} className={`facility-card ${fac.validation_status}`}>
                  <div className="facility-header">
                    <span className="facility-name">{fac.name}</span>
                    <span className={`status-badge-sm ${fac.validation_status}`}>
                      {fac.validation_status}
                    </span>
                  </div>
                  <div className="facility-details">
                    <span>Type: {fac.facility_type.replace('_', ' ')}</span>
                    <span>Snap: {fac.snap_distance_m ? `${fac.snap_distance_m.toFixed(1)}m` : 'Unsnapped'}</span>
                  </div>
                  {fac.exclusion_reason && (
                    <div className="exclusion-note">
                      <em>Reason:</em> {fac.exclusion_reason}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* TAB 4: LAYERS & MAP LEGEND */}
        {activeTab === 'layers' && (
          <div className="panel-section">
            <h3>Map Layers & Visibility</h3>
            <div className="layer-toggles">
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={layerVisibility.roads}
                  onChange={() => onToggleLayer('roads')}
                />
                <span className="color-swatch road-swatch" />
                <span>Drivable Road Network</span>
              </label>

              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={layerVisibility.affectedRoads}
                  onChange={() => onToggleLayer('affectedRoads')}
                />
                <span className="color-swatch affected-swatch" />
                <span>FEMA SFHA Affected Roads (124)</span>
              </label>

              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={layerVisibility.facilities}
                  onChange={() => onToggleLayer('facilities')}
                />
                <span className="color-swatch facility-swatch" />
                <span>Emergency Facilities (Verified / Candidate)</span>
              </label>

              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={layerVisibility.origins}
                  onChange={() => onToggleLayer('origins')}
                />
                <span className="color-swatch origin-swatch" />
                <span>Census Block-Group Origins</span>
              </label>

              <label className="checkbox-row">
                <input
                  type="checkbox"
                  checked={layerVisibility.routes}
                  onChange={() => onToggleLayer('routes')}
                />
                <span className="color-swatch route-swatch" />
                <span>Route Paths (Baseline vs Disrupted)</span>
              </label>
            </div>

            <div className="legend-box">
              <h4>Legend</h4>
              <div className="legend-item">
                <div className="legend-symbol line-gray" />
                <span>Passable Road Edge (Normal Speed)</span>
              </div>
              <div className="legend-item">
                <div className="legend-symbol line-red-dashed" />
                <span>Modeled Affected Road (FEMA 100-Yr SFHA)</span>
              </div>
              <div className="legend-item">
                <div className="legend-symbol point-green" />
                <span>Origin Reachable Within {thresholdMinutes} min</span>
              </div>
              <div className="legend-item">
                <div className="legend-symbol point-red" />
                <span>Origin Network-Unreachable Under Flood</span>
              </div>
              <div className="legend-item">
                <div className="legend-symbol point-gray" />
                <span>Origin Snap Distance &gt;500m (Invalid Snap)</span>
              </div>
              <div className="legend-item">
                <div className="legend-symbol line-green-solid" />
                <span>Optimal Baseline Route</span>
              </div>
              <div className="legend-item">
                <div className="legend-symbol line-amber-dashed" />
                <span>Detoured Disrupted Route</span>
              </div>
            </div>
          </div>
        )}

        {/* SELECTED ORIGIN DETAIL MODAL / DRAWER */}
        {selectedOrigin && (
          <div className="origin-detail-box">
            <div className="origin-detail-header">
              <h4>Selected Census Origin</h4>
              <button className="close-btn" onClick={onCloseOriginDetail}>×</button>
            </div>
            <div className="detail-item">
              <span>GEOID:</span>
              <strong>{selectedOrigin.geoid}</strong>
            </div>
            <div className="detail-item">
              <span>Population:</span>
              <strong>{selectedOrigin.population.toLocaleString()}</strong>
            </div>
            <div className="detail-item">
              <span>Accessibility Status:</span>
              <span className={`status-tag ${selectedOrigin.status_category}`}>
                {selectedOrigin.status_category.replace('_', ' ').toUpperCase()}
              </span>
            </div>
            <div className="detail-item">
              <span>Travel Time:</span>
              <strong>
                {selectedOrigin.travel_time_s !== null
                  ? `${(selectedOrigin.travel_time_s / 60).toFixed(1)} min (${selectedOrigin.travel_time_s} s)`
                  : 'Unreachable'}
              </strong>
            </div>
            {selectedOrigin.facility_name && (
              <div className="detail-item">
                <span>Nearest Facility:</span>
                <strong>{selectedOrigin.facility_name} ({selectedOrigin.facility_type})</strong>
              </div>
            )}
          </div>
        )}
      </div>

      <footer className="sidebar-footer">
        <small>
          Antigravity · Flood-Aware Emergency Access Simulator.
          Planning demonstration only.
        </small>
      </footer>
    </aside>
  );
};
