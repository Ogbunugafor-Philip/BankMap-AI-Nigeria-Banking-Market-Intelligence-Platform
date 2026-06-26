import React from 'react';
import { getBOIBg, getBOIColor } from '../utils/formatters';

const SIZE_CLASSES = {
  sm: 'text-xs px-2 py-0.5 gap-1.5',
  md: 'text-sm px-3 py-1 gap-2',
  lg: 'text-base px-4 py-1.5 gap-2',
};
const DOT = { sm: 'h-1.5 w-1.5', md: 'h-2 w-2', lg: 'h-2.5 w-2.5' };

export default function BOIBadge({ label, score, size = 'md' }) {
  if (!label) return null;
  return (
    <span
      className={`inline-flex items-center rounded-full border font-semibold ${getBOIBg(label)} ${SIZE_CLASSES[size] || SIZE_CLASSES.md}`}
    >
      <span
        className={`rounded-full ${DOT[size] || DOT.md}`}
        style={{ backgroundColor: getBOIColor(label) }}
      />
      <span>{label}</span>
      {score != null && <span className="font-bold tabular-nums">{score}</span>}
    </span>
  );
}
