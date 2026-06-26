import React from 'react';
import {
  RadarChart, PolarGrid, PolarAngleAxis, Radar,
  ResponsiveContainer, Legend, Tooltip,
} from 'recharts';

// Each entry maps a component to its key in the ward / lga score objects.
const AXES = [
  ['Unbanked', 'unbanked_score'],
  ['Bank Gap', 'bank_absence_score'],
  ['Economy', 'economic_viability_score'],
  ['Poverty', 'poverty_filter_score'],
  ['Market', 'osm_activity_score'],
];

export default function BOIRadar({ wardScores, lgaAverages, wardName }) {
  if (!wardScores) return null;
  const data = AXES.map(([label, key]) => ({
    component: label,
    ward: Math.round(wardScores[key] ?? 0),
    lga: Math.round(lgaAverages?.[key] ?? 0),
  }));

  return (
    <div>
      <h3 className="section-title mb-0">BOI Component Analysis</h3>
      <p className="text-xs text-slate-500 mb-2">vs LGA average</p>
      <div style={{ height: 220 }}>
        <ResponsiveContainer width="100%" height="100%">
          <RadarChart data={data} outerRadius="72%">
            <PolarGrid stroke="#334155" />
            <PolarAngleAxis dataKey="component" tick={{ fill: '#94a3b8', fontSize: 10 }} />
            <Radar name={wardName || 'Ward'} dataKey="ward"
              stroke="#0ea5e9" fill="#0ea5e9" fillOpacity={0.2} />
            <Radar name="LGA Average" dataKey="lga"
              stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.1} strokeDasharray="3 3" />
            <Tooltip
              contentStyle={{ background: '#1a2236', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }}
              labelStyle={{ color: '#e2e8f0' }} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
