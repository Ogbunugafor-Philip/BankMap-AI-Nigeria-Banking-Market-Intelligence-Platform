import React, { useEffect, useRef } from 'react';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import LoadingSpinner from './LoadingSpinner';
import { getBOIColor } from '../utils/formatters';

// Fix Leaflet's default marker icon paths (known CRA/webpack bug).
delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: require('leaflet/dist/images/marker-icon-2x.png'),
  iconUrl: require('leaflet/dist/images/marker-icon.png'),
  shadowUrl: require('leaflet/dist/images/marker-shadow.png'),
});

const NIGERIA_CENTER = [9.0820, 8.6753];
const NIGERIA_ZOOM = 6;

const baseStyle = (label) => ({
  fillColor: getBOIColor(label),
  fillOpacity: 0.65,
  weight: 1.5,
  color: 'rgba(255,255,255,0.3)',
});
const hoverStyle = (label) => ({
  fillColor: getBOIColor(label),
  fillOpacity: 0.85,
  weight: 2,
  color: '#ffffff',
});
const selectedStyle = (label) => ({
  fillColor: getBOIColor(label),
  fillOpacity: 0.8,
  weight: 3,
  color: '#0ea5e9',
});

export default function MapPanel({ lgaSummary, selectedWardId, onWardSelect, loading }) {
  const mapRef = useRef(null);
  const containerRef = useRef(null);
  const wardLayerRef = useRef(null);
  const layersByWard = useRef({});
  const selectRef = useRef(onWardSelect);
  const tileRef = useRef(null);
  selectRef.current = onWardSelect;

  // Init the map once.
  useEffect(() => {
    if (mapRef.current || !containerRef.current) return;
    const map = L.map(containerRef.current, {
      center: NIGERIA_CENTER,
      zoom: NIGERIA_ZOOM,
      zoomControl: true,
      attributionControl: true,
    });
    tileRef.current = L.tileLayer(
      'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
      { attribution: '© OpenStreetMap, © CARTO', maxZoom: 19, subdomains: 'abcd' }
    ).addTo(map);

    // Legend control (bottom-left).
    const legend = L.control({ position: 'bottomleft' });
    legend.onAdd = () => {
      const div = L.DomUtil.create('div');
      div.style.cssText =
        'background:#111827;border:1px solid #334155;border-radius:10px;padding:10px 12px;' +
        'font-size:11px;color:#e2e8f0;box-shadow:0 10px 30px rgba(0,0,0,.5);line-height:1.6;';
      div.innerHTML =
        '<div style="font-weight:700;text-transform:uppercase;letter-spacing:1px;font-size:10px;color:#94a3b8;margin-bottom:6px;">Opportunity Score</div>' +
        '<div><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#10b981;margin-right:6px;"></span>Deploy Immediately (70–100)</div>' +
        '<div><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#f59e0b;margin-right:6px;"></span>Monitor &amp; Plan (40–69)</div>' +
        '<div><span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#ef4444;margin-right:6px;"></span>Low Viability (0–39)</div>';
      return div;
    };
    legend.addTo(map);

    mapRef.current = map;
    // Ensure correct sizing after mount.
    setTimeout(() => map.invalidateSize(), 100);
    return () => { map.remove(); mapRef.current = null; };
  }, []);

  // Render ward polygons whenever the LGA summary changes.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (wardLayerRef.current) {
      wardLayerRef.current.remove();
      wardLayerRef.current = null;
      layersByWard.current = {};
    }
    const wards = (lgaSummary?.wards || []).filter(w => w.geometry);
    if (wards.length === 0) {
      map.setView(NIGERIA_CENTER, NIGERIA_ZOOM);
      return;
    }

    const features = wards.map(w => ({
      type: 'Feature',
      geometry: w.geometry,
      properties: {
        ward_id: w.ward_id, name: w.name,
        boi_label: w.boi_label, boi_score: w.boi_score, population: w.population,
      },
    }));

    const layer = L.geoJSON(features, {
      style: (f) => baseStyle(f.properties.boi_label),
      onEachFeature: (feature, lyr) => {
        const p = feature.properties;
        layersByWard.current[p.ward_id] = lyr;
        lyr.bindPopup(
          `<div style="font-family:Inter,sans-serif">
             <div style="font-weight:700;font-size:13px;margin-bottom:2px">${p.name}</div>
             <div style="font-size:12px;color:#94a3b8">BOI ${p.boi_score ?? '—'} · ${p.boi_label ?? '—'}</div>
             <div style="font-size:12px;color:#94a3b8">Population: ${p.population ? p.population.toLocaleString() : '—'}</div>
           </div>`,
          { closeButton: false }
        );
        lyr.on('mouseover', (e) => {
          if (p.ward_id !== selectedWardId) e.target.setStyle(hoverStyle(p.boi_label));
          e.target.openPopup(e.latlng);
        });
        lyr.on('mouseout', (e) => {
          if (p.ward_id !== selectedWardId) e.target.setStyle(baseStyle(p.boi_label));
          e.target.closePopup();
        });
        lyr.on('click', () => selectRef.current && selectRef.current(p.ward_id));
      },
    }).addTo(map);

    wardLayerRef.current = layer;
    try { map.fitBounds(layer.getBounds(), { padding: [30, 30] }); } catch (_) {}
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lgaSummary]);

  // Re-style on selection change.
  useEffect(() => {
    Object.entries(layersByWard.current).forEach(([id, lyr]) => {
      const label = lyr.feature?.properties?.boi_label;
      lyr.setStyle(Number(id) === selectedWardId ? selectedStyle(label) : baseStyle(label));
      if (Number(id) === selectedWardId) lyr.bringToFront();
    });
  }, [selectedWardId, lgaSummary]);

  const showOverview = !lgaSummary || (lgaSummary.wards || []).length === 0;

  return (
    <div className="relative flex-1 h-full">
      <div ref={containerRef} className="absolute inset-0" />

      {showOverview && !loading && (
        <div className="absolute top-6 left-1/2 -translate-x-1/2 z-[500] pointer-events-none">
          <div className="glass-card px-5 py-3 text-center">
            <p className="text-sm text-slate-300 font-medium">Nigeria Banking Opportunity Map</p>
            <p className="text-xs text-slate-500 mt-0.5">Select a state and LGA to explore ward-level intelligence</p>
          </div>
        </div>
      )}

      {loading && (
        <div className="absolute inset-0 z-[600] bg-surface-900/60 backdrop-blur-sm flex items-center justify-center">
          <LoadingSpinner message="Loading ward boundaries…" />
        </div>
      )}
    </div>
  );
}
