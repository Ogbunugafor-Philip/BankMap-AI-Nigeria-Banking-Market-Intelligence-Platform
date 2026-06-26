import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { BarChart3, LogOut } from 'lucide-react';
import Sidebar from '../components/Sidebar';
import MapPanel from '../components/MapPanel';
import IntelligencePanel from '../components/IntelligencePanel';
import {
  getStates, getLGAs, getLGASummary, getWardIntelligence, getWardROI,
  getUser, clearAuth,
} from '../services/api';

export default function Dashboard() {
  const navigate = useNavigate();
  const user = getUser();

  const [states, setStates] = useState([]);
  const [selectedState, setSelectedState] = useState(null);
  const [lgas, setLGAs] = useState([]);
  const [selectedLGA, setSelectedLGA] = useState(null);
  const [lgaSummary, setLgaSummary] = useState(null);
  const [selectedWardId, setSelectedWardId] = useState(null);
  const [selectedWard, setSelectedWard] = useState(null);
  const [fsoCount, setFsoCount] = useState(2);
  const [roiData, setRoiData] = useState(null);
  const [loading, setLoading] = useState({ states: false, lgas: false, map: false, ward: false, roi: false });

  const setFlag = (key, val) => setLoading(prev => ({ ...prev, [key]: val }));

  useEffect(() => {
    setFlag('states', true);
    getStates().then(setStates).catch(() => setStates([])).finally(() => setFlag('states', false));
  }, []);

  useEffect(() => {
    if (!selectedState) { setLGAs([]); return; }
    setFlag('lgas', true);
    setLGAs([]); setSelectedLGA(null); setLgaSummary(null);
    setSelectedWardId(null); setSelectedWard(null); setRoiData(null);
    getLGAs(selectedState.id).then(setLGAs).catch(() => setLGAs([])).finally(() => setFlag('lgas', false));
  }, [selectedState]);

  useEffect(() => {
    if (!selectedLGA) { setLgaSummary(null); return; }
    setFlag('map', true);
    setSelectedWardId(null); setSelectedWard(null); setRoiData(null);
    getLGASummary(selectedLGA.id).then(setLgaSummary).catch(() => setLgaSummary(null)).finally(() => setFlag('map', false));
  }, [selectedLGA]);

  useEffect(() => {
    if (!selectedWardId) { setRoiData(null); return; }
    setFlag('roi', true);
    getWardROI(selectedWardId, fsoCount).then(setRoiData).catch(() => {}).finally(() => setFlag('roi', false));
  }, [selectedWardId, fsoCount]);

  const handleStateSelect = useCallback((state) => { setSelectedState(state); }, []);
  const handleLGASelect = useCallback((lga) => { setSelectedLGA(lga); }, []);
  const handleWardSelect = useCallback((wardId) => {
    setSelectedWardId(wardId);
    setSelectedWard(null);
    setFsoCount(2);
    setFlag('ward', true);
    getWardIntelligence(wardId)
      .then(setSelectedWard)
      .catch(() => setSelectedWard(null))
      .finally(() => setFlag('ward', false));
  }, []);
  const handleFSOChange = useCallback((count) => { setFsoCount(count); }, []);

  const handleSignOut = () => { clearAuth(); navigate('/'); };

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-surface-900">
      {/* Header bar */}
      <header className="h-14 shrink-0 bg-surface-800 border-b border-slate-700/50 flex items-center justify-between px-5">
        <div className="flex items-center gap-2.5">
          <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center">
            <BarChart3 size={18} className="text-white" />
          </div>
          <span className="font-bold text-white">BankMap AI</span>
        </div>
        <span className="hidden md:block text-sm text-slate-400">Nigeria Banking Intelligence Platform</span>
        <div className="flex items-center gap-3">
          {user && (
            <div className="text-right leading-tight hidden sm:block">
              <div className="text-sm text-white font-medium">{user.name}</div>
              <div className="text-[11px] text-slate-500">{user.role || 'Demo'}</div>
            </div>
          )}
          <button
            onClick={handleSignOut}
            className="flex items-center gap-1.5 text-sm text-slate-300 hover:text-white bg-surface-600 hover:bg-surface-500 border border-slate-700/50 rounded-lg px-3 py-1.5 transition-colors"
          >
            <LogOut size={15} /> Sign Out
          </button>
        </div>
      </header>

      {/* Three-panel workspace */}
      <div className="flex flex-1 min-h-0">
        <Sidebar
          states={states}
          selectedState={selectedState}
          onStateSelect={handleStateSelect}
          lgas={lgas}
          selectedLGA={selectedLGA}
          onLGASelect={handleLGASelect}
          lgaSummary={lgaSummary}
          selectedWardId={selectedWardId}
          onWardSelect={handleWardSelect}
          loading={loading}
        />
        <MapPanel
          lgaSummary={lgaSummary}
          selectedWardId={selectedWardId}
          onWardSelect={handleWardSelect}
          loading={loading.map}
        />
        <IntelligencePanel
          selectedWard={selectedWard}
          lgaSummary={lgaSummary}
          loading={loading.ward}
          fsoCount={fsoCount}
          roiData={roiData}
          onFSOChange={handleFSOChange}
        />
      </div>
    </div>
  );
}
