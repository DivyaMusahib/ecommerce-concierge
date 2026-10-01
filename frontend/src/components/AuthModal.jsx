import React, { useState } from 'react';

const API_BASE = 'http://127.0.0.1:8000';

export function AuthModal({ onSuccess, onClose }) {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const url = isLogin ? `${API_BASE}/auth/login` : `${API_BASE}/auth/register`;
      const body = isLogin ? { email, password } : { email, password, name };
      
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Authentication failed');
      
      localStorage.setItem('shopmate_token', data.access_token);
      localStorage.setItem('shopmate_user', JSON.stringify({ id: data.user_id, name: data.name }));
      
      onSuccess({ id: data.user_id, name: data.name });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fillDemo = () => {
    setEmail('demo@gmail.com');
    setPassword('demo');
    setError('');
  };

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl w-full max-w-sm overflow-hidden shadow-2xl relative">
        {onClose && (
          <button onClick={onClose} className="absolute top-3 right-3 text-gray-400 hover:text-gray-600 p-1 text-lg leading-none">✕</button>
        )}
        <div className="p-6">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-500 flex items-center justify-center text-white font-bold text-lg">S</div>
            <h2 className="text-xl font-bold text-gray-900">{isLogin ? 'Welcome Back' : 'Create Account'}</h2>
          </div>

          {/* ── Demo credentials banner — always visible for login ─────────── */}
          {isLogin && (
            <div className="mb-5 flex items-center justify-between gap-3 bg-indigo-50 border border-indigo-200 rounded-xl px-4 py-3">
              <div>
                <p className="text-xs font-bold text-indigo-700 mb-0.5">✨ Try the demo account</p>
                <p className="text-xs text-indigo-600 font-mono">
                  demo@gmail.com&nbsp;/&nbsp;<span className="font-semibold">demo</span>
                </p>
              </div>
              <button
                type="button"
                onClick={fillDemo}
                className="text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 px-3 py-1.5 rounded-lg transition-colors whitespace-nowrap"
              >
                Use demo
              </button>
            </div>
          )}
          
          <form onSubmit={handleSubmit} className="space-y-4">
            {!isLogin && (
              <div>
                <label className="block text-xs font-semibold text-gray-600 mb-1">Name</label>
                <input required type="text" value={name} onChange={e => setName(e.target.value)} 
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 outline-none transition-all" 
                  placeholder="John Doe" />
              </div>
            )}
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1">Email</label>
              <input required type="email" value={email} onChange={e => setEmail(e.target.value)} 
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 outline-none transition-all" 
                placeholder="you@example.com" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-600 mb-1">Password</label>
              <input required type="password" value={password} onChange={e => setPassword(e.target.value)} 
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 outline-none transition-all" 
                placeholder="••••••••" />
            </div>
            
            {error && <div className="text-red-500 text-xs font-medium">{error}</div>}
            
            <button disabled={loading} type="submit" 
              className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-2.5 rounded-lg text-sm transition-colors mt-2 disabled:opacity-50">
              {loading ? 'Processing...' : (isLogin ? 'Sign In' : 'Sign Up')}
            </button>
          </form>
          
          <div className="mt-5 text-center text-xs text-gray-500">
            {isLogin ? "Don't have an account?" : "Already have an account?"}
            <button type="button" onClick={() => { setIsLogin(!isLogin); setError(''); }} 
              className="ml-1 text-indigo-600 font-semibold hover:underline">
              {isLogin ? 'Sign up' : 'Sign in'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
