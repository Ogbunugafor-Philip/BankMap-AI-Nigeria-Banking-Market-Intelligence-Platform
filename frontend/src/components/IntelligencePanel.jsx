import React from 'react';
import ReactMarkdown from 'react-markdown';
import {
  MapPin, Users, UserX, Signal, CheckCircle2, Sparkles, Activity,
  Building2, Store, Landmark, Route,
} from 'lucide-react';
import BOIBadge from './BOIBadge';
import LoadingSpinner from './LoadingSpinner';
import Shimmer from './Shimmer';
import PopulationDonut from './charts/PopulationDonut';
import BOIRadar from './charts/BOIRadar';
import NationalRankBar from './charts/NationalRankBar';
import {
  formatNumber, formatPercent, formatDistance, formatConfidence,
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

export default function IntelligencePanel({ selectedWard, osmData, briefData, wardScores, lgaSummary, loading }) {
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

  // Map the ward's stored component scores into the radar's key shape.
  const cs = boi?.component_scores || {};
  const wardRadar = {
    unbanked_score: cs.unbanked_population_score,
    bank_absence_score: cs.bank_absence_score,
    economic_viability_score: cs.economic_viability_score,
    poverty_filter_score: cs.poverty_filter_score,
    osm_activity_score: cs.osm_activity_score,
  };

  return (
    <aside className={`${PANEL} animate-fade-in`}>
      <div className="p-5">
        {/* SECTION 1 — HEADER */}
        <h2 className="text-2xl font-bold text-white leading-tight">{ward.name}</h2>
        <p className="text-sm text-slate-400">{ward.lga_name} · {ward.state_name}</p>
        <div className="flex items-center gap-2 mt-3">
          <BOIBadge label={boi.boi_label} score={boi.boi_score} size="lg" />
          <span className="text-xs text-slate-300 bg-surface-600 border border-slate-700/50 rounded-full px-3 py-1.5">
            {formatConfidence(boi.data_confidence)} confidence
          </span>
        </div>

        <Divider />

        {/* SECTION 2 — KEY METRICS */}
        <div className="grid grid-cols-2 gap-3">
          <MetricCard icon={Users} label="Population" value={formatNumber(ward.population)} />
          <MetricCard icon={UserX} label="Unbanked Adults" value={formatNumber(unbanked)} />
          <MetricCard icon={MapPin} label="Nearest Bank" value={formatDistance(ward.nearest_bank_distance_km)} />
          <MetricCard icon={Signal} label="SIM Penetration" value={formatPercent(ward.sim_penetration)} />
        </div>

        <Divider />

        {/* SECTION 3 — NATIONAL RANKING */}
        <div className="glass-card p-4 rounded-xl">
          <NationalRankBar
            boi_score={boi.boi_score} boi_label={boi.boi_label}
            ward_name={ward.name} state_name={ward.state_name} />
        </div>

        <Divider />

        {/* SECTION 4 — POPULATION DONUT */}
        <div className="glass-card p-4 rounded-xl">
          <PopulationDonut population={ward.population} unbankedRate={ward.unbanked_rate} />
        </div>

        <Divider />

        {/* SECTION 5 — BOI COMPONENT RADAR */}
        <div className="glass-card p-4 rounded-xl">
          {!wardScores ? (
            <>
              <h3 className="section-title mb-0">BOI Component Analysis</h3>
              <p className="text-xs text-slate-500 mb-2">vs LGA average</p>
              <Shimmer height="h-44" />
            </>
          ) : (
            <BOIRadar wardScores={wardRadar} lgaAverages={wardScores.lga_averages} wardName={ward.name} />
          )}
        </div>

        <Divider />

        {/* SECTION 7 — EXPLAINABILITY */}
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

        {/* SECTION 8 — OSM MARKET DATA */}
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

        {/* SECTION 9 — AI DEPLOYMENT BRIEF */}
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
            <div className="bg-surface-900 border border-slate-700 rounded-xl p-4 prose prose-invert prose-sm max-w-none
              prose-headings:text-white prose-headings:font-semibold
              prose-headings:text-sm prose-headings:mt-3 prose-headings:mb-1
              prose-p:text-slate-300 prose-p:leading-relaxed prose-p:my-1
              prose-li:text-slate-300 prose-li:my-0.5
              prose-ul:my-1 prose-ul:pl-4
              prose-strong:text-white prose-strong:font-semibold
              [&>*:first-child]:mt-0">
              <ReactMarkdown>{deployment_brief}</ReactMarkdown>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}
