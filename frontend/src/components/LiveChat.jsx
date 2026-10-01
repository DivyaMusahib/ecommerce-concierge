import React, { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import { PastelBlobs } from './Backgrounds';
import { AuthModal } from './AuthModal';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'https://shopmate-ecommerce-concierge.onrender.com';

const QUICK = [
  { label: '📦 Track order #123', q: 'Where is my order #123?' },
  { label: '📱 iPhone 17 Pro specs', q: 'Tell me about the iPhone 17 Pro' },
  { label: '↩️ Return policy', q: 'What is your return policy?' },
  { label: '🏷️ Price trends', q: 'Is this a good time to buy a laptop?' },
  { label: '🛍️ Add to cart', q: 'Add iPhone to my cart' },
  { label: '🚨 File complaint', q: 'My order #999 is delayed and I am frustrated' },
  { label: '🎟️ Apply SAVE10', q: 'Apply coupon SAVE10 to my cart' },
  { label: '💳 Checkout', q: 'Checkout my cart' },
];

/* ── Markdown renderer ─────────────────────────────────────────────────── */
function MdMessage({ content }) {
  return (
    <ReactMarkdown components={{
      p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
      strong: ({ children }) => <strong className="font-bold text-gray-800 dark:text-gray-100">{children}</strong>,
      em: ({ children }) => <em className="italic">{children}</em>,
      ul: ({ children }) => <ul className="list-disc pl-4 mb-2 space-y-1">{children}</ul>,
      ol: ({ children }) => <ol className="list-decimal pl-4 mb-2 space-y-1">{children}</ol>,
      li: ({ children }) => <li className="text-sm">{children}</li>,
      code: ({ children }) => <code className="bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 px-1.5 py-0.5 rounded text-xs font-mono">{children}</code>,
      h3: ({ children }) => <h3 className="font-bold text-gray-800 dark:text-gray-100 mb-1">{children}</h3>,
    }}>{content}</ReactMarkdown>
  );
}

/* ── Memory panel (only shown when logged in) ──────────────────────────── */
function MemoryPanel({ userId, refreshKey }) {
  const [profile, setProfile] = useState(null);
  const [flash, setFlash] = useState(false);
  const [showAll, setShowAll] = useState(false);

  const fetchMemory = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/memory/${userId}`);
      if (!res.ok) return;
      setProfile(await res.json());
    } catch { /* backend offline */ }
  }, [userId]);

  useEffect(() => { fetchMemory(); }, [fetchMemory, refreshKey]);
  useEffect(() => {
    if (refreshKey > 0) { setFlash(true); setTimeout(() => setFlash(false), 1800); }
  }, [refreshKey]);

  const forgetKey = async (key) => {
    try { await fetch(`${API_BASE}/memory/${userId}/preference/${key}`, { method: 'DELETE' }); fetchMemory(); } catch { }
  };
  const clearAll = async () => {
    try { await fetch(`${API_BASE}/memory/${userId}/all`, { method: 'DELETE' }); fetchMemory(); } catch { }
  };

  if (!profile) return (
    <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
      <div className="text-[9px] font-bold text-gray-300 uppercase tracking-wider mb-1">Memory</div>
      <div className="text-[10px] text-gray-300 italic">Loading...</div>
    </div>
  );

  const prefs = Object.entries(profile.preferences || {});
  const visiblePrefs = showAll ? prefs : prefs.slice(0, 3);

  return (
    <div className={`mt-3 pt-3 border-t border-gray-100 dark:border-gray-700 transition-all duration-500 rounded-lg ${flash ? 'bg-green-50 ring-1 ring-green-200' : ''}`}>
      <div className="flex items-center justify-between mb-2">
        <div className="text-[9px] font-bold text-gray-300 uppercase tracking-wider flex items-center gap-1">
          <span>Memory</span>
          {flash && <span className="text-green-500 animate-pulse">✦</span>}
        </div>
        {prefs.length > 0 && (
          <button onClick={clearAll} className="text-[8px] text-red-300 hover:text-red-500 transition-colors font-medium" title="Clear all">
            Clear
          </button>
        )}
      </div>

      <div className="flex items-center gap-2 mb-2">
        <div className="w-5 h-5 rounded-full flex items-center justify-center text-white text-[8px] font-bold shrink-0"
          style={{ background: 'linear-gradient(135deg,#a78bfa,#60a5fa)' }}>
          {(profile.name || 'U')[0]}
        </div>
        <div className="text-[10px] font-bold text-gray-700 dark:text-gray-200 truncate">{profile.name || 'Guest'}</div>
      </div>

      {prefs.length === 0 ? (
        <div className="text-[9px] text-gray-300 italic leading-relaxed">
          Chat and I'll remember your preferences!
        </div>
      ) : (
        <>
          {visiblePrefs.map(([k, v]) => (
            <div key={k} className="group flex items-start justify-between gap-1 mb-1">
              <div className="min-w-0">
                <div className="text-[8px] font-bold text-gray-400 uppercase tracking-wide truncate">{k.replace(/_/g, ' ')}</div>
                <div className="text-[9px] text-gray-600 dark:text-gray-300 font-medium truncate">{v}</div>
              </div>
              <button onClick={() => forgetKey(k)}
                className="opacity-0 group-hover:opacity-100 text-[9px] text-red-300 hover:text-red-500 transition-all shrink-0 mt-0.5"
                title={`Forget "${k}"`}>✕</button>
            </div>
          ))}
          {prefs.length > 3 && (
            <button onClick={() => setShowAll(s => !s)} className="text-[9px] text-indigo-400 hover:text-indigo-600 transition-colors mt-1">
              {showAll ? 'Show less' : `+${prefs.length - 3} more`}
            </button>
          )}
        </>
      )}
      <div className="text-[8px] text-gray-200 mt-2">SQLite · Persistent</div>
    </div>
  );
}

/* ── Main LiveChat component ───────────────────────────────────────────── */
export function LiveChat({ prefill, setPrefill }) {
  const [sessionId] = useState(() => {
    const stored = sessionStorage.getItem('shopmate_session_id');
    if (stored) return stored;
    const id = `session_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
    sessionStorage.setItem('shopmate_session_id', id);
    return id;
  });

  const [authUser, setAuthUser] = useState(() => {
    try { const u = localStorage.getItem('shopmate_user'); return u ? JSON.parse(u) : null; }
    catch { return null; }
  });

  // Auth modal is NEVER shown automatically — only when user explicitly tries to chat without account
  const [showAuthModal, setShowAuthModal] = useState(false);
  // Prompt shown inline when guest tries to send
  const [showLoginPrompt, setShowLoginPrompt] = useState(false);

  const [msgs, setMsgs] = useState([
    { role: 'assistant', content: "Hi! I'm ShopMate 👋\n\nI'm powered by **6 specialized AI agents** built with LangChain & LangGraph:\n- 🛒 **Product Agent** — search, specs & pricing\n- 📦 **Order Agent** — track orders (#123, #456, #999)\n- 💬 **FAQ Agent** — policies & returns\n- 🏷️ **Deals Agent** — price trends & coupons\n- 🛍️ **Cart Agent** — add items, apply coupons, checkout\n- 🚨 **Complaint Agent** — escalation & refunds\n\n**Sign in** to save your preferences across sessions, or just start chatting as a guest!" }
  ]);
  const [input, setInput] = useState('');
  const [agentSteps, setAgentSteps] = useState([]);
  const [loading, setLoading] = useState(false);
  const [lastLatency, setLastLatency] = useState(null);
  const [pendingConfirm, setPendingConfirm] = useState(null);
  const [memoryRefreshKey, setMemoryRefreshKey] = useState(0);
  const [memoryToast, setMemoryToast] = useState(false);
  const [myOrders, setMyOrders] = useState([]);
  const msgsRef = useRef(null);

  useEffect(() => {
    if (msgsRef.current) msgsRef.current.scrollTop = msgsRef.current.scrollHeight;
  }, [msgs, agentSteps]);

  useEffect(() => {
    if (prefill) { setInput(prefill); setPrefill(''); }
  }, [prefill, setPrefill]);

  /* ── Send message ─────────────────────────────────────────────────── */
  const send = useCallback(async (override) => {
    const text = (override ?? input).trim();
    if (!text || loading) return;

    // Guest can still chat — just no memory persistence
    setShowLoginPrompt(false);
    setInput('');
    setMsgs(p => [...p, { role: 'user', content: text }]);
    setLoading(true);
    setAgentSteps([{ name: 'Intent Classifier', desc: 'LangChain structured output...', color: '#a78bfa' }]);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          session_id: sessionId,
          user_id: authUser?.id || 'guest',
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Server error ${res.status}`);
      }

      const data = await res.json();
      const intent = data.intent || 'PRODUCT_INQUIRY';
      const agents = data.agents_used || [];
      const urgency = data.urgency || 'LOW';
      const latencyMs = data.latency_ms || null;

      const agentColors = {
        ProductAgent: '#a78bfa', OrderAgent: '#60a5fa', FaqAgent: '#34d399',
        DealsAgent: '#fb923c', CartAgent: '#8b5cf6', ComplaintAgent: '#f472b6',
      };
      const steps = [
        { name: 'Intent Classifier', desc: `Intent: ${intent} | Urgency: ${urgency}`, color: '#a78bfa' },
        ...agents.map(a => ({ name: a, desc: 'LangGraph ReAct agent + tool calling...', color: agentColors[a] || '#60a5fa' })),
        { name: 'Self-Critique Evaluator', desc: 'QA check via second LLM pass...', color: '#34d399' },
      ];
      setAgentSteps(steps);
      if (latencyMs) setLastLatency(latencyMs);

      if (data.memory_updated) {
        setMemoryRefreshKey(k => k + 1);
        setMemoryToast(true);
        setTimeout(() => setMemoryToast(false), 3000);
      }

      if (data.confirmation_required && data.checkout_summary) {
        setMsgs(p => [...p, { role: 'assistant', content: data.response, urgency }]);
        setPendingConfirm({ summary: data.checkout_summary, message: data.response });
      } else {
        setMsgs(p => [...p, { role: 'assistant', content: data.response, urgency }]);
      }
      setAgentSteps([]);
      setLoading(false);

    } catch (err) {
      const isOffline = err.message.includes('fetch') || err.message.includes('Failed');
      setMsgs(p => [...p, {
        role: 'assistant',
        content: isOffline
          ? '⚠️ **Backend offline.**\n\nStart it with:\n```\ncd ecommerce_assistant\nuvicorn app.main:app --reload\n```'
          : `⚠️ **Error:** ${err.message}`,
      }]);
      setAgentSteps([]);
      setLoading(false);
    }
  }, [input, loading, sessionId, authUser]);

  /* ── Orders ───────────────────────────────────────────────────────── */
  const fetchMyOrders = useCallback(async () => {
    if (!authUser) return;
    try {
      const res = await fetch(`${API_BASE}/orders/confirmed/${authUser.id}`);
      if (res.ok) { const d = await res.json(); setMyOrders(d.orders || []); }
    } catch { }
  }, [authUser]);

  useEffect(() => { fetchMyOrders(); }, [fetchMyOrders]);

  /* ── Checkout ─────────────────────────────────────────────────────── */
  const confirmCheckout = useCallback(async (deliveryFee = 0) => {
    if (!pendingConfirm) return;
    setLoading(true);
    try {
      // Modify the summary to include the selected delivery fee
      const updatedSummary = {
        ...pendingConfirm.summary,
        delivery_fee: deliveryFee,
        total: pendingConfirm.summary.total + deliveryFee
      };

      const res = await fetch(`${API_BASE}/checkout/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          user_id: authUser?.id || 'guest',
          draft_summary: updatedSummary,
        }),
      });
      const data = await res.json();
      if (res.ok && data.status === 'confirmed') {
        const receipt = `✅ **Order Confirmed!** Your order **${data.order_id}** has been placed.\n\n**Total charged:** ₹${data.total}\n**Items:** ${(data.items || []).map(i => i.name).join(', ')}\n\nYou can track it by asking me about order ${data.order_id}.`;
        setMsgs(p => [...p, { role: 'assistant', content: receipt }]);
        fetchMyOrders();
      } else {
        setMsgs(p => [...p, { role: 'assistant', content: `❌ Checkout failed: ${data.detail || 'Unknown error'}. Please try again.` }]);
      }
    } catch {
      setMsgs(p => [...p, { role: 'assistant', content: '⚠️ Could not confirm checkout — backend offline.' }]);
    } finally {
      setPendingConfirm(null);
      setLoading(false);
    }
  }, [pendingConfirm, sessionId, authUser, fetchMyOrders]);

  const cancelCheckout = useCallback(() => {
    setMsgs(p => [...p, { role: 'assistant', content: '❌ Checkout cancelled. Your cart is still saved.' }]);
    setPendingConfirm(null);
  }, []);

  /* ── Sign out ─────────────────────────────────────────────────────── */
  const signOut = () => {
    localStorage.removeItem('shopmate_user');
    localStorage.removeItem('shopmate_token');
    setAuthUser(null);
    setMyOrders([]);
    setShowLoginPrompt(false);
  };

  /* ── Render ───────────────────────────────────────────────────────── */
  return (
    <section id="demo" className="py-24 px-6 bg-white dark:bg-gray-800 relative overflow-hidden">
      <PastelBlobs blobs={[
        { size: 400, top: '5%', left: '-5%', color: 'radial-gradient(circle, rgba(96,165,250,0.12) 0%, transparent 70%)', blur: 80 },
        { size: 350, bottom: '5%', right: '-3%', color: 'radial-gradient(circle, rgba(244,114,182,0.1) 0%, transparent 70%)', blur: 70 },
      ]} />

      <div className="max-w-5xl mx-auto relative z-10">
        {/* Header */}
        <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="text-center mb-12">
          <div className="text-[11px] font-bold tracking-widest uppercase mb-3" style={{ color: '#60a5fa' }}>Live Demo</div>
          <h2 className="text-4xl font-extrabold text-gray-800 dark:text-gray-100 mb-2">Chat with ShopMate</h2>
          <p className="text-gray-400 text-[15px]">Fully connected to your FastAPI multi-agent backend. Try it — no login required!</p>
        </motion.div>

        {/* Chat window */}
        <motion.div initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}
          className="rounded-2xl overflow-hidden border border-gray-100 dark:border-gray-700 shadow-xl flex flex-col bg-white dark:bg-gray-800" style={{ height: 640 }}>

          {/* Title bar */}
          <div className="flex items-center justify-between px-5 h-12 border-b border-gray-100 dark:border-gray-700 shrink-0 bg-gray-50 dark:bg-gray-900">
            <div className="flex gap-1.5">
              <div className="w-2.5 h-2.5 rounded-full bg-red-300" />
              <div className="w-2.5 h-2.5 rounded-full bg-yellow-300" />
              <div className="w-2.5 h-2.5 rounded-full bg-green-300" />
            </div>
            <div className="text-[11px] font-semibold text-gray-400">
              <span className="tracking-tight text-gray-900 dark:text-white">Shop</span><span className="text-transparent bg-clip-text bg-gradient-to-r from-[#6366F1] via-[#3B82F6] to-[#14B8A6]">Mate</span> AI Concierge
            </div>
            <div className="flex items-center gap-3">
              {lastLatency && (
                <div className="text-[10px] font-mono text-gray-400 bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded">{lastLatency}ms</div>
              )}
              <div className="flex items-center gap-1.5 text-[11px] text-green-500 font-semibold">
                <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" /> Live
              </div>
              {authUser ? (
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-gray-500 dark:text-gray-400 font-medium hidden sm:block">
                    👤 {authUser.name}
                  </span>
                  <button onClick={signOut}
                    className="text-[10px] font-bold px-2.5 py-1 bg-red-50 text-red-500 rounded-md hover:bg-red-100 transition-colors">
                    Sign Out
                  </button>
                </div>
              ) : (
                <button onClick={() => setShowAuthModal(true)}
                  className="text-[10px] font-bold px-3 py-1.5 text-white rounded-lg shadow-sm transition-all hover:opacity-90"
                  style={{ background: 'linear-gradient(135deg, #a78bfa, #60a5fa)' }}>
                  Sign In
                </button>
              )}
            </div>
          </div>

          <div className="flex flex-1 overflow-hidden">
            {/* ── Sidebar ─────────────────────────────────────────── */}
            <div className="w-48 border-r border-gray-100 dark:border-gray-700 flex flex-col shrink-0 bg-gray-50 dark:bg-gray-900">
              {/* Logo + New Chat */}
              <div className="p-3 pb-2">
                <div className="flex items-center gap-2 font-bold text-sm mb-3 text-gray-700 dark:text-gray-200">
                  <img src="/logo.png" alt="ShopMate Logo" className="w-5 h-5 rounded-md object-cover shrink-0" />
                  <span className="truncate tracking-tight text-gray-900 dark:text-white">
                    Shop<span className="text-transparent bg-clip-text bg-gradient-to-r from-[#6366F1] via-[#3B82F6] to-[#14B8A6]">Mate</span>
                  </span>
                </div>
                <button onClick={async () => {
                  setMsgs([{ role: 'assistant', content: '👋 New chat started! I still remember your preferences.' }]);
                  setInput('');
                  setPendingConfirm(null);
                  setAgentSteps([]);
                  setShowLoginPrompt(false);
                  try { await fetch(`${API_BASE}/session/${sessionId}`, { method: 'DELETE' }); } catch { }
                  try { await fetch(`${API_BASE}/cart/${sessionId}`, { method: 'DELETE' }); } catch { }
                }}
                  className="w-full text-white text-[11px] font-bold py-1.5 rounded-lg flex items-center justify-center gap-1 transition-all hover:opacity-90"
                  style={{ background: 'linear-gradient(135deg, #a78bfa, #60a5fa)' }}>
                  + New Chat
                </button>
              </div>

              {/* Memory / auth callout + Quick actions */}
              <div className="flex-1 overflow-y-auto px-3 pb-3">
                {/* Quick actions — properly laid out with wrapping labels */}
                <div className="pb-3 border-b border-gray-100 dark:border-gray-700 mb-3">
                  <div className="text-[9px] font-bold text-gray-300 uppercase tracking-wider mb-1.5">Try These</div>
                  <div className="space-y-0.5">
                    {QUICK.map(({ label, q }) => (
                      <button
                        key={label}
                        onClick={() => send(q)}
                        title={q}
                        className="w-full text-left px-2 py-1.5 rounded-lg hover:bg-white dark:hover:bg-gray-800 hover:shadow-sm cursor-pointer transition-all leading-tight group"
                      >
                        <div className="text-[10.5px] font-medium text-gray-600 dark:text-gray-300 group-hover:text-gray-900 dark:group-hover:text-white transition-colors">{label}</div>
                        <div className="text-[9px] font-normal text-gray-400 dark:text-gray-500 mt-0.5 line-clamp-1 italic">"{q}"</div>
                      </button>
                    ))}
                  </div>
                </div>
                {authUser ? (
                  <>
                    <MemoryPanel userId={authUser.id} refreshKey={memoryRefreshKey} />
                    <AnimatePresence>
                      {memoryToast && (
                        <motion.div
                          initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                          className="mt-1.5 text-[9px] font-semibold text-green-600 bg-green-50 border border-green-200 rounded-lg px-2 py-1 flex items-center gap-1">
                          <span>✦</span> Memory updated!
                        </motion.div>
                      )}
                    </AnimatePresence>
                    {myOrders.length > 0 && (
                      <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
                        <div className="text-[9px] font-bold text-gray-300 uppercase tracking-wider mb-1.5">My Orders</div>
                        {myOrders.slice(0, 3).map(o => (
                          <div key={o.order_id} className="text-[9px] text-gray-500 dark:text-gray-400 mb-1.5 bg-white dark:bg-gray-800 border border-gray-100 dark:border-gray-700 rounded-lg p-1.5">
                            <div className="font-bold text-gray-700 dark:text-gray-200 truncate text-[10px]">{o.order_id}</div>
                            <div className="text-green-600 font-semibold">₹{o.total}</div>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                ) : (
                  <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700">
                    <button
                      onClick={() => setShowAuthModal(true)}
                      className="w-full text-[10px] text-indigo-500 font-semibold bg-indigo-50 hover:bg-indigo-100 p-2.5 rounded-lg transition-colors text-center leading-snug">
                      🔐 Sign in to save<br />your preferences
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* ── Chat area ───────────────────────────────────────── */}
            <div className="flex-1 flex flex-col overflow-hidden">
              {/* Messages */}
              <div ref={msgsRef} className="flex-1 overflow-y-auto p-5 flex flex-col gap-4">
                {msgs.map((m, i) => (
                  <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'flex-row-reverse' : ''}`}>
                    {m.role === 'user' ? (
                      <div className="w-7 h-7 rounded-full shrink-0 flex items-center justify-center text-white text-[10px] font-bold shadow-sm"
                        style={{ background: 'linear-gradient(135deg, #a78bfa, #818cf8)' }}>
                        {authUser ? authUser.name[0].toUpperCase() : 'G'}
                      </div>
                    ) : (
                      <img src="/logo.png" alt="ShopMate" className="w-7 h-7 rounded-full object-cover shrink-0 shadow-sm" />
                    )}
                    <div className={`max-w-sm px-4 py-3 rounded-2xl text-[13px] leading-relaxed
                      ${m.role === 'user' ? 'text-white rounded-tr-sm' : 'rounded-tl-sm'}
                      ${m.role === 'assistant' && m.urgency === 'HIGH' ? 'bg-red-50 border border-red-200 text-gray-700 dark:text-gray-200' : ''}
                      ${m.role === 'assistant' && m.urgency !== 'HIGH' ? 'bg-gray-50 dark:bg-gray-900 border border-gray-100 dark:border-gray-700 text-gray-600 dark:text-gray-300' : ''}`}
                      style={m.role === 'user' ? { background: 'linear-gradient(135deg, #a78bfa, #818cf8)' } : {}}>
                      {m.role === 'assistant' && m.urgency === 'HIGH' && (
                        <div className="text-[9px] font-bold text-red-500 uppercase tracking-wider mb-1">🚨 High Priority</div>
                      )}
                      {m.role === 'assistant' ? <MdMessage content={m.content} /> : m.content}
                    </div>
                  </div>
                ))}

                {/* Login nudge — shown inline, not a blocking modal */}
                <AnimatePresence>
                  {showLoginPrompt && !authUser && (
                    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
                      className="flex gap-3">
                      <div className="w-7 h-7 rounded-full flex items-center justify-center text-white text-[10px] shrink-0 font-bold"
                        style={{ background: 'linear-gradient(135deg, #60a5fa, #34d399)' }}>S</div>
                      <div className="bg-indigo-50 border border-indigo-200 rounded-2xl rounded-tl-sm px-4 py-3 max-w-xs">
                        <div className="text-[12px] font-semibold text-indigo-800 mb-2">
                          Sign in to save your preferences & order history — or just keep chatting as a guest!
                        </div>
                        <div className="flex gap-2">
                          <button onClick={() => setShowAuthModal(true)}
                            className="text-[11px] font-bold px-3 py-1.5 rounded-lg text-white"
                            style={{ background: 'linear-gradient(135deg, #a78bfa, #60a5fa)' }}>
                            Sign In
                          </button>
                          <button onClick={() => setShowLoginPrompt(false)}
                            className="text-[11px] font-bold px-3 py-1.5 rounded-lg border border-gray-200 dark:border-gray-600 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:bg-gray-900">
                            Continue as Guest
                          </button>
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Checkout confirm card */}
                <AnimatePresence>
                  {pendingConfirm && (
                    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="flex gap-3">
                      <div className="w-7 h-7 rounded-full flex items-center justify-center text-white text-[10px] shrink-0 font-bold"
                        style={{ background: 'linear-gradient(135deg, #8b5cf6, #f472b6)' }}>S</div>
                      <div className="bg-purple-50 border border-purple-200 rounded-2xl rounded-tl-sm px-5 py-4 max-w-sm">
                        <div className="text-[11px] font-bold mb-3 text-purple-700">Confirm your order?</div>
                        {pendingConfirm.summary && (
                          <div className="text-[12px] text-gray-600 dark:text-gray-300 mb-3 space-y-1">
                            {(pendingConfirm.summary.items || []).map((item, idx2) => (
                              <div key={idx2} className="flex justify-between">
                                <span>{item.name} ×{item.qty}</span><span>₹{item.price}</span>
                              </div>
                            ))}
                            {pendingConfirm.summary.discount > 0 && (
                              <div className="flex justify-between text-green-600">
                                <span>Discount</span><span>-₹{pendingConfirm.summary.discount}</span>
                              </div>
                            )}
                            <div className="flex justify-between text-gray-500 dark:text-gray-400">
                              <span>Tax (8%)</span><span>₹{pendingConfirm.summary.tax}</span>
                            </div>
                            <div className="border-t border-purple-100 mt-2 pt-2 font-bold flex justify-between text-purple-700">
                              <span>Total</span><span>₹{pendingConfirm.summary.total}</span>
                            </div>
                          </div>
                        )}
                        <div className="flex gap-2 flex-col">
                          <div className="flex gap-2">
                            <button onClick={() => confirmCheckout(0)} disabled={loading}
                              className="flex-1 text-[11px] font-bold py-2 rounded-xl text-white disabled:opacity-60 flex items-center justify-center gap-1.5"
                              style={{ background: 'linear-gradient(135deg, #8b5cf6, #60a5fa)' }}>
                              {loading ? 'Placing...' : 'Standard (Free)'}
                            </button>
                            <button onClick={() => confirmCheckout(100)} disabled={loading}
                              className="flex-1 text-[11px] font-bold py-2 rounded-xl text-white disabled:opacity-60 flex items-center justify-center gap-1.5"
                              style={{ background: 'linear-gradient(135deg, #f59e0b, #d97706)' }}>
                              {loading ? 'Placing...' : '1-Day (+₹100)'}
                            </button>
                          </div>
                          <button onClick={cancelCheckout} disabled={loading}
                            className="w-full text-[11px] font-bold py-2 rounded-xl border border-gray-200 dark:border-gray-600 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:bg-gray-900 disabled:opacity-40">
                            Cancel Checkout
                          </button>
                        </div>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Agent working indicator */}
                <AnimatePresence>
                  {agentSteps.length > 0 && (
                    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="flex gap-3">
                      <div className="w-7 h-7 rounded-full flex items-center justify-center text-white text-[10px] shrink-0 font-bold"
                        style={{ background: 'linear-gradient(135deg, #60a5fa, #34d399)' }}>S</div>
                      <div className="bg-gray-50 dark:bg-gray-900 border border-gray-100 dark:border-gray-700 rounded-2xl rounded-tl-sm px-5 py-4 max-w-sm">
                        <div className="text-[11px] font-bold mb-3 flex items-center gap-2" style={{ color: '#a78bfa' }}>
                          <span className="w-1.5 h-1.5 rounded-full animate-ping inline-block" style={{ background: '#a78bfa' }} />
                          Agents Working...
                        </div>
                        {agentSteps.map((s, idx) => (
                          <motion.div key={idx} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }}
                            transition={{ delay: idx * 0.22 }} className="flex items-center gap-3 mb-2.5">
                            <div className="rounded-full flex items-center justify-center shrink-0" style={{ background: s.color, width: 18, height: 18 }}>
                              <svg width="8" height="8" fill="none" viewBox="0 0 24 24">
                                <path d="M5 13l4 4L19 7" stroke="white" strokeWidth="2.5" strokeLinecap="round" />
                              </svg>
                            </div>
                            <div>
                              <div className="text-[11px] font-bold text-gray-700 dark:text-gray-200">{s.name}</div>
                              <div className="text-[10px] text-gray-400">{s.desc}</div>
                            </div>
                          </motion.div>
                        ))}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* Input bar */}
              <div className="p-4 border-t border-gray-100 dark:border-gray-700 shrink-0">
                {!authUser && (
                  <div className="text-[10px] text-gray-400 text-center mb-2">
                    Chatting as <span className="font-semibold">guest</span> ·{' '}
                    <button onClick={() => setShowAuthModal(true)} className="text-indigo-500 hover:underline font-semibold">
                      Sign in
                    </button>{' '}to save preferences
                  </div>
                )}
                <div className="flex items-center gap-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-600 rounded-xl px-4 py-2.5
                  focus-within:border-indigo-300 focus-within:ring-2 focus-within:ring-indigo-50 transition-all">
                  <input
                    type="text"
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && !loading && send()}
                    placeholder="Ask about products, orders, returns, deals..."
                    className="flex-1 bg-transparent outline-none text-[13px] text-gray-700 dark:text-gray-200 placeholder:text-gray-300"
                  />
                  <button
                    onClick={() => send()}
                    disabled={loading || !input.trim()}
                    className="w-8 h-8 rounded-lg flex items-center justify-center text-white transition-all hover:scale-105 active:scale-95 disabled:opacity-30 shrink-0"
                    style={{ background: 'linear-gradient(135deg, #a78bfa, #60a5fa)' }}>
                    {loading ? (
                      <span className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    ) : (
                      <svg width="14" height="14" fill="none" viewBox="0 0 24 24">
                        <path d="M22 2L11 13M22 2L15 22 11 13 2 9l20-7z" stroke="white" strokeWidth="1.8" strokeLinecap="round" />
                      </svg>
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </motion.div>
      </div>

      {/* Auth modal — only shown when user explicitly requests it */}
      {showAuthModal && (
        <AuthModal
          onSuccess={(u) => {
            localStorage.setItem('shopmate_user', JSON.stringify(u));
            setAuthUser(u);
            setShowAuthModal(false);
            setShowLoginPrompt(false);
          }}
          onClose={() => setShowAuthModal(false)}
        />
      )}
    </section>
  );
}

