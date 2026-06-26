import React from 'react';
import { Link } from 'react-router-dom';
import { BarChart3, MapPin, Users, Database } from 'lucide-react';

const STATS = [
  ['9,308', 'Wards Mapped'],
  ['774', 'LGAs Covered'],
  ['37', 'States'],
  ['100%', 'Real Data'],
];

const STEPS = [
  { icon: MapPin, n: 1, title: 'Select State & LGA',
    body: "Choose any of Nigeria's 774 LGAs. The system loads all wards instantly." },
  { icon: BarChart3, n: 2, title: 'Receive Intelligence',
    body: 'Every ward gets a Banking Opportunity Index score — GREEN, AMBER, or RED — with full explainability.' },
  { icon: Users, n: 3, title: 'Deploy Your FSOs',
    body: 'Cerebras AI generates a plain-English brief telling you exactly where to send field officers and why.' },
];

const SOURCES = [
  ['GRID3', 'Ward Boundaries', '9,308 ward boundary polygons'],
  ['EFInA', 'Financial Inclusion', 'A2F Survey — banked vs unbanked rates'],
  ['CBN', 'Bank Branches', '891 licensed branch locations'],
  ['NBS', 'Poverty Index', 'Multidimensional Poverty Index by LGA'],
  ['NCC', 'SIM Penetration', 'Mobile subscriber data by state'],
  ['OpenStreetMap', 'Live Markets', 'Real-time economic activity data'],
];

function Logo() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="h-9 w-9 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center">
        <BarChart3 size={20} className="text-white" />
      </div>
      <span className="font-bold text-white text-lg">BankMap AI</span>
    </div>
  );
}

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-surface-900 text-slate-100 overflow-y-auto" style={{ overflow: 'auto' }}>
      {/* ---------- HERO ---------- */}
      <section className="relative min-h-screen flex flex-col">
        {/* animated blob */}
        <div className="pointer-events-none absolute -top-40 left-1/2 -translate-x-1/2 h-[500px] w-[500px] rounded-full bg-brand-500/10 blur-3xl animate-pulse-slow" />

        <nav className="relative flex items-center justify-between px-6 md:px-12 py-6">
          <Logo />
          <Link to="/login" className="border border-brand-500 text-brand-400 hover:bg-brand-500/10 rounded-lg px-5 py-2 text-sm font-semibold transition-colors">
            Sign In
          </Link>
        </nav>

        <div className="relative flex-1 flex flex-col items-center justify-center text-center px-6 max-w-4xl mx-auto pb-16">
          <span className="bg-brand-500/10 text-brand-400 border border-brand-500/20 text-xs rounded-full px-4 py-1.5">
            Nigeria · 9,308 Wards · 37 States
          </span>
          <h1 className="text-4xl md:text-6xl font-black text-white leading-tight mt-6">
            Deploy FSOs Where the<br />Opportunity Is <span className="text-brand-400">Real</span>
          </h1>
          <p className="text-lg md:text-xl text-slate-400 max-w-2xl mx-auto mt-4">
            BankMap AI gives Nigerian bank managers instant ward-level market intelligence —
            unbanked population, competitor gaps, and AI-generated deployment briefs — across all 774 LGAs.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center mt-10">
            <Link to="/dashboard" className="bg-brand-600 hover:bg-brand-700 rounded-xl px-8 py-4 font-semibold text-white transition-colors">
              Access Dashboard
            </Link>
            <a href="/api/docs" target="_blank" rel="noreferrer" className="border border-slate-600 hover:border-slate-400 rounded-xl px-8 py-4 text-slate-300 transition-colors">
              View API Docs
            </a>
          </div>
          <div className="flex flex-wrap gap-10 md:gap-12 justify-center mt-16">
            {STATS.map(([num, label]) => (
              <div key={label} className="text-center">
                <div className="text-3xl md:text-4xl font-black text-white">{num}</div>
                <div className="text-sm text-slate-400 mt-1">{label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------- HOW IT WORKS ---------- */}
      <section className="py-24 bg-surface-800 px-6">
        <div className="text-center max-w-2xl mx-auto">
          <h2 className="text-3xl font-bold text-white">How BankMap AI Works</h2>
          <p className="text-slate-400 mt-2">Zero manual input. Select a location. Get intelligence.</p>
        </div>
        <div className="flex flex-col md:flex-row gap-8 max-w-5xl mx-auto mt-12">
          {STEPS.map(({ icon: Icon, n, title, body }) => (
            <div key={n} className="glass-card p-8 rounded-2xl flex-1 relative">
              <div className="absolute -top-3 -left-3 h-8 w-8 rounded-full bg-brand-600 flex items-center justify-center text-white text-sm font-bold">{n}</div>
              <Icon size={32} className="text-brand-500" />
              <h3 className="text-lg font-semibold text-white mt-4">{title}</h3>
              <p className="text-slate-400 text-sm mt-2 leading-relaxed">{body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ---------- DATA SOURCES ---------- */}
      <section className="py-24 bg-surface-900 px-6">
        <div className="text-center max-w-2xl mx-auto">
          <h2 className="text-3xl font-bold text-white">Built on Real Nigerian Data</h2>
          <p className="text-slate-400 mt-2">Every data point is sourced from official public datasets</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 max-w-5xl mx-auto mt-12">
          {SOURCES.map(([name, dataset, desc]) => (
            <div key={name} className="glass-card p-6">
              <Database size={22} className="text-brand-500" />
              <div className="font-bold text-white mt-3">{name}</div>
              <div className="text-sm text-brand-400">{dataset}</div>
              <p className="text-slate-400 text-sm mt-2">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ---------- CTA FOOTER ---------- */}
      <section className="py-20 bg-surface-800 text-center px-6">
        <h2 className="text-3xl font-bold text-white">Ready to deploy smarter?</h2>
        <p className="text-slate-400 max-w-xl mx-auto mt-3">
          Access the BankMap AI dashboard and start identifying your highest-opportunity wards today.
        </p>
        <Link to="/login" className="inline-block bg-brand-600 hover:bg-brand-700 rounded-xl px-10 py-4 font-semibold text-white mt-8 transition-colors">
          Sign In to Dashboard
        </Link>
        <p className="text-xs text-slate-600 mt-6">9,308 wards · 37 states · Powered by Cerebras AI</p>
      </section>
    </div>
  );
}
