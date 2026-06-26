import React from 'react';

const Shimmer = ({ height = 'h-20', className = '' }) => (
  <div className={`${height} ${className} rounded-xl bg-surface-600 relative overflow-hidden`}>
    <div className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-slate-500/10 to-transparent" />
  </div>
);

export default Shimmer;
