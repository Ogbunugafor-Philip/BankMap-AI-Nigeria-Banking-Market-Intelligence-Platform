export const formatNGN = (amount) => {
  if (!amount && amount !== 0) return '—';
  if (amount >= 1_000_000_000) return `₦${(amount/1_000_000_000).toFixed(1)}B`;
  if (amount >= 1_000_000)     return `₦${(amount/1_000_000).toFixed(1)}M`;
  if (amount >= 1_000)         return `₦${(amount/1_000).toFixed(0)}K`;
  return `₦${amount.toLocaleString()}`;
};
export const formatNumber = (n) => n ? Math.round(n).toLocaleString() : '—';
export const formatPercent = (rate) => rate != null ? `${Math.round(rate * 100)}%` : '—';
export const formatDistance = (km) => km != null ? `${km.toFixed(1)} km` : '—';
export const formatConfidence = (c) => c != null ? `${Math.round(c * 100)}%` : '—';

export const getBOIColor = (label) =>
  ({ GREEN: '#10b981', AMBER: '#f59e0b', RED: '#ef4444' }[label] ?? '#64748b');

export const getBOIBg = (label) =>
  ({ GREEN: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30',
     AMBER: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
     RED:   'bg-red-500/20 text-red-400 border-red-500/30' }[label] ?? '');

export const getProgressColor = (score) => {
  if (score >= 70) return '#10b981';
  if (score >= 40) return '#f59e0b';
  return '#ef4444';
};
