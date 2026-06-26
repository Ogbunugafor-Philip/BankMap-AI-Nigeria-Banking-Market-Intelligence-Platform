import React, { useState } from 'react';
import { Download, Loader2, AlertCircle } from 'lucide-react';

export default function PDFExportButton({ wardId, wardName, lgaName }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleExport = async () => {
    if (!wardId || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/wards/${wardId}/export-pdf`, { method: 'POST' });
      if (!res.ok) throw new Error(`Server responded ${res.status}`);
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      const safe = (s) => (s || 'ward').replace(/[^A-Za-z0-9]+/g, '_');
      a.href = url;
      a.download = `bankmap_${safe(wardName)}_${safe(lgaName)}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      setError('Export failed. Please try again.');
      setTimeout(() => setError(null), 3000);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-2">
      <button
        onClick={handleExport}
        disabled={loading}
        className="w-full flex items-center justify-center gap-2 bg-brand-600 hover:bg-brand-700 disabled:opacity-60 disabled:cursor-not-allowed text-white font-semibold rounded-xl py-3 transition-colors"
      >
        {loading ? <Loader2 size={18} className="animate-spin" /> : <Download size={18} />}
        {loading ? 'Generating PDF…' : 'Export Ward Report PDF'}
      </button>
      {error && (
        <div className="flex items-center gap-2 text-xs text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
          <AlertCircle size={14} /> {error}
        </div>
      )}
    </div>
  );
}
