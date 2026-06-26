import React, { useMemo } from 'react';
import { BarChart3, Users, MapPin } from 'lucide-react';
import BOIBadge from './BOIBadge';
import LoadingSpinner from './LoadingSpinner';
import { formatNumber, formatDistance } from '../utils/formatters';

function WardCard({ ward, active, onClick }) {
  return (
    <div className={`ward-card ${active ? 'active' : ''}`} onClick={onClick}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-slate-100 truncate">{ward.name}</span>
        <BOIBadge label={ward.boi_label} score={ward.boi_score} size="sm" />
      </div>
      <div className="flex items-center gap-4 mt-2 text-xs text-slate-400">
        <span className="inline-flex items-center gap-1">
          <Users size={12} /> {formatNumber(ward.population)}
        </span>
        <span className="inline-flex items-center gap-1">
          <MapPin size={12} /> {formatDistance(ward.nearest_bank_distance_km)}
        </span>
      </div>
    </div>
  );
}

export default function Sidebar({
  states, selectedState, onStateSelect,
  lgas, selectedLGA, onLGASelect,
  lgaSummary, selectedWardId, onWardSelect,
  loading,
}) {
  const counts = useMemo(() => {
    const c = { GREEN: 0, AMBER: 0, RED: 0 };
    (lgaSummary?.wards || []).forEach(w => { if (c[w.boi_label] != null) c[w.boi_label]++; });
    return c;
  }, [lgaSummary]);

  return (
    <aside className="w-72 shrink-0 h-full bg-surface-800 border-r border-slate-700/50 flex flex-col">
      {/* Branding */}
      <div className="p-5">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center shadow-lg shadow-brand-900/40">
            <BarChart3 size={22} className="text-white" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-white leading-tight">BankMap AI</h1>
            <p className="text-xs text-slate-400">Nigeria Banking Intelligence</p>
          </div>
        </div>
      </div>
      <div className="border-t border-slate-700/50" />

      {/* Selectors + ward list */}
      <div className="flex-1 overflow-y-auto p-5 space-y-6">
        {/* State */}
        <div>
          <label className="section-title block">Select State</label>
          {loading?.states ? (
            <div className="text-xs text-slate-500">Loading states…</div>
          ) : (
            <select
              className="w-full bg-surface-500 border border-slate-600 rounded-lg text-slate-100 p-2.5 text-sm focus:outline-none focus:border-brand-500 transition-colors"
              value={selectedState?.id || ''}
              onChange={(e) => {
                const s = states.find(x => String(x.id) === e.target.value);
                onStateSelect(s || null);
              }}
            >
              <option value="" disabled>Choose a state…</option>
              {states.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          )}
        </div>

        {/* LGA */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <span className="section-title mb-0">Select LGA</span>
            {selectedState && lgas?.length > 0 && (
              <span className="text-[10px] font-semibold text-brand-100 bg-brand-700/40 px-2 py-0.5 rounded-full">
                {lgas.length}
              </span>
            )}
          </div>
          {!selectedState ? (
            <div className="w-full bg-surface-500 border border-slate-600 rounded-lg text-slate-500 p-2.5 text-sm opacity-50">
              Select a state first
            </div>
          ) : loading?.lgas ? (
            <div className="text-xs text-slate-500">Loading LGAs…</div>
          ) : (
            <select
              className="w-full bg-surface-500 border border-slate-600 rounded-lg text-slate-100 p-2.5 text-sm focus:outline-none focus:border-brand-500 transition-colors"
              value={selectedLGA?.id || ''}
              onChange={(e) => {
                const l = lgas.find(x => String(x.id) === e.target.value);
                onLGASelect(l || null);
              }}
            >
              <option value="" disabled>Choose an LGA…</option>
              {lgas.map(l => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          )}
        </div>

        {/* Ward list */}
        {selectedLGA && (
          <div>
            <label className="section-title block">Wards Ranked by Opportunity</label>
            {loading?.map ? (
              <div className="py-6"><LoadingSpinner size="sm" message="Loading wards…" /></div>
            ) : (
              <>
                <div className="text-xs text-slate-400 mb-3 flex items-center gap-2">
                  <span className="text-emerald-400">{counts.GREEN} green</span><span>·</span>
                  <span className="text-amber-400">{counts.AMBER} amber</span><span>·</span>
                  <span className="text-red-400">{counts.RED} red</span>
                </div>
                <div className="space-y-2">
                  {(lgaSummary?.wards || []).map(w => (
                    <WardCard
                      key={w.ward_id}
                      ward={w}
                      active={selectedWardId === w.ward_id}
                      onClick={() => onWardSelect(w.ward_id)}
                    />
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="border-t border-slate-700/50 p-4 space-y-2">
        <p className="text-[10px] text-slate-500">Data: GRID3 · EFInA · CBN · NBS · NCC</p>
        <span className="inline-block text-[10px] font-medium text-slate-400 bg-surface-600 border border-slate-700/50 px-2 py-1 rounded-md">
          v1.0 · 15 States · 4,044 Wards
        </span>
      </div>
    </aside>
  );
}
