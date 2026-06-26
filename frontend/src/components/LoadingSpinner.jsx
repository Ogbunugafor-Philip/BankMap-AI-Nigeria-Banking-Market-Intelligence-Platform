import React from 'react';

const SIZES = { sm: 'h-4 w-4', md: 'h-8 w-8', lg: 'h-12 w-12' };

export default function LoadingSpinner({ message, size = 'md' }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 text-center">
      <div
        className={`${SIZES[size] || SIZES.md} rounded-full border-2 border-brand-500 border-t-transparent animate-spin`}
        role="status"
        aria-label="Loading"
      />
      {message && <p className="text-sm text-slate-400">{message}</p>}
    </div>
  );
}
