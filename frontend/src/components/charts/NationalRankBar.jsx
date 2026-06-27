import React, { useState, useEffect } from 'react';
import { getBOIColor, formatNumber } from '../../utils/formatters';

// Fallback percentile estimate, only used if the server didn't supply a real rank.
function topPercentile(score) {
  if (score >= 70) return Math.max(1, Math.round((100 - score) * 3));
  if (score >= 40) return 50 + Math.round((70 - score) * 1.5);
  return 90;
}

const CONTEXT = {
  GREEN: 'Ranked in the top deployment priority tier nationally',
  AMBER: 'Ranked in the monitor and plan tier — review in 6 months',
  RED: 'Low opportunity — resources better deployed elsewhere',
};

export default function NationalRankBar({
  boi_score, boi_label, national_boi_rank, wards_with_more_unbanked, total_wards,
}) {
  const score = boi_score ?? 0;
  const color = getBOIColor(boi_label);
  const [width, setWidth] = useState(0);

  // Animate the bar from 0 to the score on mount / when the ward changes.
  useEffect(() => {
    setWidth(0);
    const t = setTimeout(() => setWidth(score), 60);
    return () => clearTimeout(t);
  }, [score]);

  const total = total_wards || 9308;
  const hasRealRank = national_boi_rank != null;
  // Prefer the exact server rank; fall back to the heuristic estimate.
  const percentile = hasRealRank
    ? Math.max(1, Math.round((national_boi_rank / total) * 100))
    : topPercentile(score);

  return (
    <div>
      <h3 className="section-title">National Opportunity Ranking</h3>

      <div className="h-3 w-full rounded-full bg-slate-700 overflow-hidden">
        <div className="h-full rounded-full transition-all duration-1000 ease-out"
          style={{ width: `${width}%`, backgroundColor: color }} />
      </div>

      {/* Zone markers: RED 0–40 · AMBER 40–70 · GREEN 70–100 */}
      <div className="flex mt-1.5 text-[9px] uppercase tracking-wide">
        <div className="text-red" style={{ width: '40%' }}>Red</div>
        <div className="text-amber text-center" style={{ width: '30%' }}>Amber</div>
        <div className="text-green text-right" style={{ width: '30%' }}>Green</div>
      </div>
      <div className="flex justify-between text-[9px] text-slate-500 mt-0.5">
        <span>0</span><span>40</span><span>70</span><span>100</span>
      </div>

      {hasRealRank ? (
        <>
          <p className="text-sm font-semibold mt-3" style={{ color }}>
            Ranked #{formatNumber(national_boi_rank)} of {formatNumber(total)} wards by banking opportunity
          </p>
          <p className="text-xs text-slate-400 mt-1">
            BOI {score}/100 · top {percentile}% nationally
            {wards_with_more_unbanked != null
              && ` · ${formatNumber(wards_with_more_unbanked)} wards have larger unbanked populations`}
          </p>
        </>
      ) : (
        <>
          <p className="text-sm font-semibold mt-3" style={{ color }}>
            BOI {score}/100 — Top {percentile}% nationally
          </p>
          <p className="text-xs text-slate-400 mt-1">{CONTEXT[boi_label] || ''}</p>
        </>
      )}
    </div>
  );
}
