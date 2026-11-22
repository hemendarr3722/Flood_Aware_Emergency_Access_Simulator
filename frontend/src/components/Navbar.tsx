import React from 'react';
import { StudyArea } from '../types';

interface NavbarProps {
  areas: StudyArea[];
  selectedAreaId: number;
  onSelectArea: (id: number) => void;
  apiStatus: 'checking' | 'healthy' | 'error';
}

export const Navbar: React.FC<NavbarProps> = ({
  areas,
  selectedAreaId,
  onSelectArea,
  apiStatus,
}) => {
  return (
    <header className="navbar">
      <div className="navbar-brand">
        <div className="brand-icon">🌊</div>
        <div className="brand-text">
          <span className="brand-title">Flood-Aware Emergency Access</span>
          <span className="brand-subtitle">Houston Urban Core · GIS Simulation & Accessibility Engine</span>
        </div>
      </div>

      <div className="navbar-controls">
        <div className="study-area-picker">
          <label htmlFor="area-select">Study Area:</label>
          <select
            id="area-select"
            value={selectedAreaId}
            onChange={(e) => onSelectArea(Number(e.target.value))}
          >
            {areas.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </div>

        <div className={`status-pill ${apiStatus}`}>
          <span className="status-dot" />
          <span>
            {apiStatus === 'healthy' ? 'API Online' : apiStatus === 'checking' ? 'Connecting...' : 'API Offline'}
          </span>
        </div>

        <div className="planning-disclaimer-badge" title="Modeled regulatory flood zones. Not for live emergency response.">
          ⚠️ PLANNING DEMO ONLY
        </div>
      </div>
    </header>
  );
};
