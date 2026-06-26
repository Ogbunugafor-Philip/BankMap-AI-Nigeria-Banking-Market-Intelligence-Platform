import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BarChart3, Eye, EyeOff, Info, Loader2 } from 'lucide-react';
import { login, saveAuth } from '../services/api';

export default function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const data = await login(email.trim(), password);
      saveAuth(data.access_token, {
        name: data.user_name, email: data.user_email, role: data.user_role,
      });
      navigate('/dashboard');
    } catch (err) {
      setError(err.response?.data?.detail || 'Invalid credentials. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="min-h-screen w-full flex items-center justify-center bg-surface-900 p-4"
      style={{
        backgroundImage:
          'linear-gradient(rgba(148,163,184,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.04) 1px, transparent 1px)',
        backgroundSize: '40px 40px',
      }}
    >
      <div className="w-full max-w-md bg-surface-700 rounded-2xl p-10 shadow-2xl border border-slate-700/50">
        {/* Logo */}
        <div className="flex flex-col items-center text-center">
          <BarChart3 size={48} className="text-brand-500" />
          <h1 className="text-3xl font-black text-white mt-3">BankMap AI</h1>
          <p className="text-sm text-slate-400">Nigeria Banking Intelligence Platform</p>
        </div>
        <div className="border-t border-slate-700/50 mt-6 mb-8" />

        <h2 className="text-xl font-semibold text-white">Welcome back</h2>
        <p className="text-sm text-slate-400 mt-1">Sign in to access the intelligence dashboard</p>

        <form className="mt-8" onSubmit={handleSubmit}>
          <label className="text-xs font-medium text-slate-400 uppercase tracking-wider">Email Address</label>
          <input
            type="email" value={email} onChange={(e) => setEmail(e.target.value)} required
            placeholder="Enter your email" autoComplete="username"
            className="w-full mt-1 bg-surface-900 border border-slate-600 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
          />

          <label className="text-xs font-medium text-slate-400 uppercase tracking-wider block mt-4">Password</label>
          <div className="relative mt-1">
            <input
              type={showPw ? 'text' : 'password'} value={password}
              onChange={(e) => setPassword(e.target.value)} required
              placeholder="Enter your password" autoComplete="current-password"
              className="w-full bg-surface-900 border border-slate-600 rounded-xl px-4 py-3 pr-11 text-white placeholder-slate-500 focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
            <button type="button" onClick={() => setShowPw(s => !s)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300">
              {showPw ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>

          {error && (
            <div className="mt-3 bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3 text-red-400 text-sm">
              {error}
            </div>
          )}

          <button type="submit" disabled={loading}
            className="w-full mt-6 bg-brand-600 hover:bg-brand-700 disabled:opacity-60 rounded-xl py-3 font-semibold text-white transition-all duration-200 flex items-center justify-center gap-2">
            {loading && <Loader2 size={18} className="animate-spin" />}
            {loading ? 'Signing in…' : 'Sign In to Dashboard'}
          </button>
        </form>

        {/* Demo credentials */}
        <div className="mt-6 bg-surface-900 rounded-xl p-4 border border-slate-700">
          <div className="flex items-center gap-2 text-slate-400 text-xs font-medium">
            <Info size={13} /> Demo Access
          </div>
          <div className="mt-2 text-xs text-slate-500 font-mono leading-relaxed">
            <div>Email: philiposita1041@gmail.com</div>
            <div>Password: Osita@1989</div>
          </div>
        </div>

        <p className="mt-8 text-xs text-slate-600 text-center">
          Powered by Cerebras AI · Data: GRID3 · EFInA · CBN
        </p>
      </div>
    </div>
  );
}
