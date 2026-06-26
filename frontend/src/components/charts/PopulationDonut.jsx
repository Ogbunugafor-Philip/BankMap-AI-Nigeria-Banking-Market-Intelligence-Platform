import React from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts';
import { formatNumber } from '../../utils/formatters';

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const p = payload[0];
  return (
    <div className="bg-surface-700 border border-slate-600 rounded-lg px-3 py-1.5 text-xs text-slate-100">
      {p.name}: <span className="font-bold">{formatNumber(p.value)}</span>
    </div>
  );
}

export default function PopulationDonut({ population, unbankedRate }) {
  const pop = population || 0;
  const unbanked = Math.round(pop * (unbankedRate || 0));
  const banked = Math.max(0, pop - unbanked);
  const unbankedPct = pop ? Math.round((unbanked / pop) * 100) : 0;

  const data = [
    { name: 'Unbanked Adults', value: unbanked, color: '#ef4444' },
    { name: 'Banked Adults', value: banked, color: '#10b981' },
  ];

  return (
    <div>
      <h3 className="section-title">Population Breakdown</h3>
      <div className="relative" style={{ height: 200 }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data} dataKey="value" nameKey="name"
              cx="50%" cy="50%" innerRadius={55} outerRadius={80}
              startAngle={90} endAngle={-270} stroke="none"
            >
              {data.map((d) => <Cell key={d.name} fill={d.color} />)}
            </Pie>
            <Tooltip content={<CustomTooltip />} />
          </PieChart>
        </ResponsiveContainer>
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <span className="text-2xl font-bold text-red">{unbankedPct}%</span>
          <span className="text-xs text-slate-400">unbanked</span>
        </div>
      </div>
      <div className="flex items-center justify-center gap-5 mt-2 text-xs">
        <span className="inline-flex items-center gap-1.5 text-slate-300">
          <span className="h-2 w-2 rounded-full bg-red" /> Unbanked: {formatNumber(unbanked)}
        </span>
        <span className="inline-flex items-center gap-1.5 text-slate-300">
          <span className="h-2 w-2 rounded-full bg-green" /> Banked: {formatNumber(banked)}
        </span>
      </div>
    </div>
  );
}
