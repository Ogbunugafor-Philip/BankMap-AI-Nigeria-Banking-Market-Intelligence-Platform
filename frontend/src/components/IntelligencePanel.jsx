import React from 'react';
import {
  MapPin, Users, UserX, Signal, CheckCircle2, Sparkles, Activity,
  Building2, Store, Landmark, Route, TrendingUp,
} from 'lucide-react';
import BOIBadge from './BOIBadge';
import LoadingSpinner from './LoadingSpinner';
import PDFExportButton from './PDFExportButton';
import Shimmer from './Shimmer';
import {
  formatNumber, formatNGN, formatPercent, formatDistance, formatConfidence,
  getBOIColor, getProgressColor,
} from '../utils/formatters';

const PANEL = 'w-96 shrink-0 h-full bg-surface-800 border-l border-slate-700/50 overflow-y-auto';
const Divider = () => <div className="border-t border-slate-700/50 my-5" />;

function MetricCard({ icon: Icon, label, value }) {
  return (
    <div className="metric-card">
      <div className="flex items-center gap-2 text-slate-400">
        <Icon size={15} />
        <span className="text-[10px] uppercase tracking-wide">{label}</span>
      </div>
      <span className="text-lg font-bold text-white tabular-nums">{value}</span>
    </div>
  );
}

function ProgressRow({ label, score }) {
  const val = score ?? 0;
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-slate-300">{label}</span>
        <span className="text-xs font-bold text-white tabular-nums">{Math.round(val)}</span>
      </div>
      <div className="progress-bar-track">
        <div className="progress-bar-fill"
             style={{ width: `${Math.max(0, Math.min(100, val))}%`, backgroundColor: getProgressColor(val) }} />
      </div>
    </div>
  );
}

// ---- STATE A: empty ----
function EmptyState({ lgaSummary }) {
  const counts = { GREEN: 0, AMBER: 0, RED: 0 };
  (lgaSummary?.wards || []).forEach(w => { if (counts[w.boi_label] != null) counts[w.boi_label]++; });
  const total = lgaSummary?.wards?.length || 0;
  return (
    <div className="h-full flex flex-col items-center justify-center text-center p-8 gap-3">
      <MapPin size={48} className="text-brand-500" />
      <h2 className="text-lg font-bold text-white">Select a Ward</h2>
      <p className="text-sm text-slate-400 max-w-xs">
        Choose a state and LGA, then click any ward on the map or select from the list to see full intelligence analysis.
      </p>
      {total > 0 && (
        <div className="grid grid-cols-2 gap-3 w-full mt-4">
          <div className="metric-card items-center"><span className="text-2xl font-black text-white">{total}</span><span className="text-[10px] uppercase tracking-wide text-slate-400">Total Wards</span></div>
          <div className="metric-card items-center"><span className="text-2xl font-black text-emerald-400">{counts.GREEN}</span><span className="text-[10px] uppercase tracking-wide text-slate-400">Green</span></div>
          <div className="metric-card items-center"><span className="text-2xl font-black text-amber-400">{counts.AMBER}</span><span className="text-[10px] uppercase tracking-wide text-slate-400">Amber</span></div>
          <div className="metric-card items-center"><span className="text-2xl font-black text-red-400">{counts.RED}</span><span className="text-[10px] uppercase tracking-wide text-slate-400">Red</span></div>
        </div>
      )}
    </div>
  );
}

export default function IntelligencePanel({ selectedWard, osmData, briefData, lgaSummary, loading, fsoCount, roiData, onFSOChange }) {
  if (loading) {
    return (
      <aside className={PANEL}>
        <div className="h-full flex items-center justify-center animate-pulse-slow">
          <LoadingSpinner message="Analysing ward intelligence…" />
        </div>
      </aside>
    );
  }
  if (!selectedWard) {
    return <aside className={PANEL}><EmptyState lgaSummary={lgaSummary} /></aside>;
  }

  const { ward, boi } = selectedWard;
  const roi = roiData?.roi || selectedWard.roi;
  const unbanked = Math.round((ward.population || 0) * (ward.unbanked_rate || 0));
  const explanations = boi?.explanation
    ? ['unbanked_population', 'bank_absence', 'economic_viability', 'poverty_filter', 'osm_activity']
        .map(k => boi.explanation[k]).filter(Boolean)
    : [];
  // OSM + brief arrive progressively (null until their background fetch lands).
  const osm_data = osmData;
  const deployment_brief = briefData?.brief;
  const deployment_brief_source = briefData?.source;
  const isLiveBrief = (deployment_brief_source || '').startsWith('cerebras');
  const osmDefault = (osm_data?.source || '').includes('default');
  const br = osm_data?.breakdown || {};

  return (
    <aside className={`${PANEL} animate-fade-in`}>
      <div className="p-5">
        {/* HEADER */}
        <h2 className="text-2xl font-bold text-white leading-tight">{ward.name}</h2>
        <p className="text-sm text-slate-400">{ward.lga_name} · {ward.state_name}</p>
        <div className="flex items-center gap-2 mt-3">
          <BOIBadge label={boi.boi_label} score={boi.boi_score} size="lg" />
          <span className="text-xs text-slate-300 bg-surface-600 border border-slate-700/50 rounded-full px-3 py-1.5">
            {formatConfidence(boi.data_confidence)} confidence
          </span>
        </div>

        <Divider />

        {/* SECTION 1 — KEY METRICS */}
        <div className="grid grid-cols-2 gap-3">
          <MetricCard icon={Users} label="Population" value={formatNumber(ward.population)} />
          <MetricCard icon={UserX} label="Unbanked Adults" value={formatNumber(unbanked)} />
          <MetricCard icon={MapPin} label="Nearest Bank" value={formatDistance(ward.nearest_bank_distance_km)} />
          <MetricCard icon={Signal} label="SIM Penetration" value={formatPercent(ward.sim_penetration)} />
        </div>

        <Divider />

        {/* SECTION 2 — BOI BREAKDOWN */}
        <h3 className="section-title">Opportunity Score Breakdown</h3>
        <div className="text-center mb-5">
          <div className="text-6xl font-black tabular-nums" style={{ color: getBOIColor(boi.boi_label) }}>
            {boi.boi_score}
          </div>
          <div className="text-sm font-semibold tracking-wide" style={{ color: getBOIColor(boi.boi_label) }}>
            {boi.boi_label}
          </div>
        </div>
        <div className="space-y-3">
          <ProgressRow label="Unbanked Population" score={boi.components?.unbanked_population} />
          <ProgressRow label="Bank Absence" score={boi.components?.bank_absence} />
          <ProgressRow label="Economic Viability" score={boi.components?.economic_viability} />
          <ProgressRow label="Poverty Filter" score={boi.components?.poverty_filter} />
          <ProgressRow label="Market Activity" score={boi.components?.osm_activity} />
        </div>

        <Divider />

        {/* SECTION 3 — EXPLAINABILITY */}
        <h3 className="section-title">Why This Score</h3>
        <ul className="space-y-2">
          {explanations.map((text, i) => (
            <li key={i} className="flex items-start gap-2 animate-fade-in" style={{ animationDelay: `${i * 80}ms` }}>
              <CheckCircle2 size={15} className="text-emerald-400 mt-0.5 shrink-0" />
              <span className="text-sm text-slate-300">{text}</span>
            </li>
          ))}
        </ul>

        <Divider />

        {/* SECTION 4 — OSM MARKET DATA */}
        <h3 className="section-title">Live Market Intelligence</h3>
        {!osm_data ? (
          <div className="glass-card p-4">
            <div className="flex items-center gap-2 text-slate-400 text-sm mb-3">
              <Activity size={16} className="text-brand-500 animate-pulse" /> Querying OpenStreetMap…
            </div>
            <div className="grid grid-cols-4 gap-2">
              {[0, 1, 2, 3].map(i => <Shimmer key={i} height="h-12" />)}
            </div>
          </div>
        ) : (
          <div className="glass-card p-4 animate-fade-in">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Activity size={16} className="text-brand-500" />
                <span className="text-sm text-slate-200">OpenStreetMap Overpass API</span>
              </div>
              {osmDefault
                ? <span className="text-[10px] font-semibold text-slate-400 bg-slate-500/20 border border-slate-500/30 px-2 py-0.5 rounded-full">Limited data</span>
                : <span className="text-[10px] font-semibold text-emerald-400 bg-emerald-500/20 border border-emerald-500/30 px-2 py-0.5 rounded-full">Live</span>}
            </div>
            {osmDefault ? (
              <p className="text-xs text-slate-400">Limited data available for this ward; using a neutral activity baseline.</p>
            ) : (
              <>
                <p className="text-xs text-slate-400 mb-3">
                  <span className="font-bold text-white">{osm_data?.total_nodes ?? 0}</span> economic features within 5&nbsp;km
                </p>
                <div className="grid grid-cols-4 gap-2 text-center">
                  {[[Store, 'Shops', br.shops], [Building2, 'Markets', br.markets], [Landmark, 'Banks', br.banks], [Route, 'Roads', br.roads]].map(([Icon, lbl, val]) => (
                    <div key={lbl} className="bg-surface-700 rounded-lg p-2">
                      <Icon size={14} className="mx-auto text-slate-400 mb-1" />
                      <div className="text-sm font-bold text-white tabular-nums">{val ?? 0}</div>
                      <div className="text-[9px] uppercase text-slate-500">{lbl}</div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        <Divider />

        {/* SECTION 5 — AI DEPLOYMENT BRIEF */}
        <div className="flex items-center justify-between mb-3">
          <h3 className="section-title mb-0">AI Deployment Brief</h3>
          <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-purple-300 bg-purple-500/20 border border-purple-500/30 px-2 py-0.5 rounded-full">
            <Sparkles size={11} /> Powered by Cerebras AI
          </span>
        </div>
        {!briefData ? (
          <div className="bg-surface-900 border border-slate-700 rounded-xl p-4">
            <div className="flex items-center gap-2 text-slate-400 text-sm mb-3">
              <Sparkles size={14} className="text-purple-300 animate-pulse" /> Generating AI brief…
            </div>
            <Shimmer height="h-3" />
            <Shimmer height="h-3" className="mt-2 w-11/12" />
            <Shimmer height="h-3" className="mt-2 w-10/12" />
            <Shimmer height="h-3" className="mt-2 w-8/12" />
          </div>
        ) : (
          <div className="animate-fade-in">
            <div className="mb-2">
              {isLiveBrief
                ? <span className="text-[10px] font-semibold text-emerald-400 bg-emerald-500/20 border border-emerald-500/30 px-2 py-0.5 rounded-full">Live AI</span>
                : <span className="text-[10px] font-semibold text-slate-400 bg-slate-500/20 border border-slate-500/30 px-2 py-0.5 rounded-full">Template</span>}
            </div>
            <div className="bg-surface-900 border border-slate-700 rounded-xl p-4 text-sm text-slate-200 leading-relaxed not-italic whitespace-pre-line">
              {deployment_brief}
            </div>
          </div>
        )}

        <Divider />

        {/* SECTION 6 — FSO SIMULATOR */}
        <h3 className="section-title">FSO Deployment Simulator</h3>
        <p className="text-xs text-slate-400 -mt-2 mb-3">Adjust FSO count to model outcomes</p>
        <div className="text-center mb-3">
          <span className="text-3xl font-black text-white">{fsoCount}</span>
          <span className="text-sm text-slate-400 ml-1">FSO{fsoCount > 1 ? 's' : ''}</span>
        </div>
        <input
          type="range" min="1" max="4" step="1" value={fsoCount}
          onChange={(e) => onFSOChange(Number(e.target.value))}
          className="w-full accent-brand-500 cursor-pointer"
        />
        <div className="flex justify-between text-[10px] text-slate-500 mt-1 px-0.5">
          {[1, 2, 3, 4].map(n => <span key={n}>{n}</span>)}
        </div>
        <div className="text-center mt-4 glass-card py-3">
          <span className="text-2xl font-black text-brand-500">~{roi?.monthly_accounts ?? '—'}</span>
          <span className="text-sm text-slate-300 block">new accounts / month</span>
        </div>

        <Divider />

        {/* SECTION 7 — ROI PROJECTION */}
        <h3 className="section-title">Financial Projection</h3>
        <div className="grid grid-cols-2 gap-3 mb-4">
          <MetricCard icon={TrendingUp} label="Acquisition Cost" value={formatNGN(roi?.acquisition_cost)} />
          <MetricCard icon={TrendingUp} label="Expected Deposits" value={formatNGN(roi?.expected_deposits)} />
          <MetricCard icon={TrendingUp} label="Yearly Revenue" value={formatNGN(roi?.yearly_revenue)} />
          <MetricCard icon={TrendingUp} label="Payback Period" value={roi?.payback_months ? `${roi.payback_months} mo` : '>10 yr'} />
        </div>

        <div className="overflow-hidden rounded-lg border border-slate-700/50">
          <table className="w-full text-xs font-mono">
            <thead>
              <tr className="bg-surface-700 text-slate-400">
                <th className="text-left p-2 font-medium">FSOs</th>
                <th className="text-right p-2 font-medium">Accts</th>
                <th className="text-right p-2 font-medium">Yr Rev</th>
                <th className="text-right p-2 font-medium">Payback</th>
              </tr>
            </thead>
            <tbody>
              {(roi?.what_if || []).map(w => (
                <tr key={w.fso_count}
                    className={`border-t border-slate-700/50 ${w.fso_count === fsoCount ? 'bg-brand-700/20 ring-1 ring-inset ring-brand-500/40' : ''}`}>
                  <td className="p-2 text-slate-200">{w.fso_count}</td>
                  <td className="p-2 text-right text-slate-200">{w.monthly_accounts}</td>
                  <td className="p-2 text-right text-slate-200">{formatNGN(w.yearly_revenue)}</td>
                  <td className="p-2 text-right text-slate-200">{w.payback_months ? `${w.payback_months}mo` : '>10y'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-5">
          <PDFExportButton wardId={ward.id} wardName={ward.name} lgaName={ward.lga_name} />
        </div>
      </div>
    </aside>
  );
}
