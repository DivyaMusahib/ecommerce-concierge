import React from 'react';
import { motion } from 'framer-motion';
import { PastelBlobs, ParticleCanvas } from './Backgrounds';
import { BotFace, AgentChip } from './AgentAssets';
import { Sun, Moon } from 'lucide-react';

export function Hero({ onDemoClick, isDark, setIsDark }) {
  return (
    <section className="relative min-h-screen overflow-hidden flex flex-col bg-white dark:bg-gray-900 transition-colors">
      <ParticleCanvas dotColor="rgba(180,160,230,0.3)" lineColor="rgba(180,160,230,0.12)" count={40} />

      <PastelBlobs blobs={[
        { size: 500, top: '-8%', right: '5%', color: 'radial-gradient(circle, rgba(255,182,193,0.4) 0%, transparent 70%)', blur: 90 },
        { size: 400, top: '20%', left: '-5%', color: 'radial-gradient(circle, rgba(173,216,230,0.3) 0%, transparent 70%)', blur: 80 },
        { size: 350, bottom: '5%', right: '15%', color: 'radial-gradient(circle, rgba(200,180,255,0.3) 0%, transparent 70%)', blur: 80 },
        { size: 300, bottom: '10%', left: '10%', color: 'radial-gradient(circle, rgba(180,255,200,0.25) 0%, transparent 70%)', blur: 70 },
      ]} />

      <nav className="relative z-20 flex items-center justify-between px-8 lg:px-12 py-5 max-w-7xl mx-auto w-full">
        <div className="flex items-center gap-2.5 font-extrabold text-lg text-gray-800 dark:text-gray-100">
          <img src="/logo.png" alt="ShopMate Logo" className="w-8 h-8 rounded-xl shadow-sm object-cover" />
          <span className="tracking-tight text-gray-900 dark:text-white">
            Shop<span className="text-transparent bg-clip-text bg-gradient-to-r from-[#6366F1] via-[#3B82F6] to-[#14B8A6]">Mate</span>
          </span>
        </div>
        <div className="hidden md:flex items-center gap-8 text-[13px] font-semibold text-gray-400">
          {['How it works', 'Agents', 'Tech Stack'].map(n => (
            <a key={n} href={`#${n.toLowerCase().replace(/ /g, '-')}`} className="hover:text-gray-800 dark:hover:text-gray-200 transition-colors">{n}</a>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setIsDark(!isDark)}
            className="p-2 rounded-full text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            aria-label="Toggle Dark Mode"
          >
            {isDark ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <button onClick={onDemoClick}
            className="text-[13px] font-bold px-5 py-2.5 rounded-full text-white transition-all shadow-md hover:shadow-lg hover:scale-[1.02]"
            style={{ background: 'linear-gradient(135deg, #a78bfa, #60a5fa)' }}>
            Try Demo
          </button>
        </div>
      </nav>

      <div className="relative z-10 flex-1 flex items-center max-w-7xl mx-auto w-full px-8 lg:px-12 gap-8 pb-14">
        <div className="flex-[1.3] max-w-[580px]">
          <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
            className="inline-flex items-center gap-2 border text-[11px] font-semibold px-4 py-1.5 rounded-full mb-8"
            style={{ background: 'rgba(167,139,250,0.08)', borderColor: 'rgba(167,139,250,0.2)', color: '#7c6bc4' }}>
            <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
            Multi-Agent AI System
          </motion.div>

          <motion.h1 initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
            className="text-[50px] lg:text-[56px] font-extrabold leading-[1.08] tracking-tight text-gray-800 dark:text-gray-100 mb-5">
            Your Shopping<br />Assistant,{' '}
            <span style={{ background: 'linear-gradient(135deg, #a78bfa, #60a5fa, #34d399)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              Reimagined
            </span>
          </motion.h1>

          <motion.p initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.18 }}
            className="text-[15px] text-gray-400 dark:text-gray-400 leading-relaxed mb-9 max-w-[450px]">
            Get product recommendations, track orders, compare products,
            resolve issues and more with a team of specialized AI agents
            working together behind the scenes.
          </motion.p>

          <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.24 }}
            className="flex items-center gap-4">
            <button onClick={onDemoClick}
              className="text-[14px] font-bold px-7 py-3.5 rounded-full text-white transition-all shadow-lg hover:shadow-xl hover:scale-[1.03]"
              style={{ background: 'linear-gradient(135deg, #a78bfa, #60a5fa)' }}>
              Try Live Demo
            </button>
            <button onClick={() => document.getElementById('how-it-works')?.scrollIntoView({ behavior: 'smooth' })}
              className="text-[14px] font-bold px-7 py-3.5 rounded-full text-gray-600 dark:text-gray-300 border border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600 transition-all bg-white/60 dark:bg-gray-800/60 backdrop-blur-sm">
              Learn More
            </button>
          </motion.div>
        </div>

        <div className="flex-[0.7] relative flex items-center justify-center" style={{ height: 480 }}>
          <motion.div initial={{ opacity: 0, scale: 0.7 }} animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}>
            <BotFace size={155} />
          </motion.div>
          <AgentChip emoji="🛒" label="Product Agent" desc="Search & compare" bg="rgba(167,139,250,0.15)" style={{ top: '6%', left: '2%' }} delay={0.4} />
          <AgentChip emoji="📦" label="Order Agent" desc="Track orders" bg="rgba(96,165,250,0.15)" style={{ top: '6%', right: '0%' }} delay={0.6} />
          <AgentChip emoji="🏷" label="Deals Agent" desc="Price trends" bg="rgba(52,211,153,0.15)" style={{ top: '40%', right: '-6%' }} delay={0.8} />
          <AgentChip emoji="🛍" label="Cart Agent" desc="Cart & checkout" bg="rgba(251,146,60,0.15)" style={{ bottom: '28%', left: '0%' }} delay={1.0} />
          <AgentChip emoji="💬" label="FAQ Agent" desc="Company policies" bg="rgba(96,165,250,0.15)" style={{ bottom: '12%', right: '-2%' }} delay={1.2} />
          <AgentChip emoji="🚨" label="Complaint Agent" desc="Escalation" bg="rgba(244,114,182,0.15)" style={{ bottom: '0%', right: '14%' }} delay={1.4} />
        </div>
      </div>
    </section>
  );
}

const STEPS = [
  { emoji: '💬', n: '01', title: 'You Ask', desc: 'Type a natural language query like "Track order #123" or "Compare iPhone vs Samsung"', color: '#a78bfa' },
  { emoji: '🧠', n: '02', title: 'Intent Classification', desc: 'Hybrid routing: 0-latency Regex for common intents, falling back to Pydantic structured LLMs.', color: '#60a5fa' },
  { emoji: '⚡', n: '03', title: 'LangGraph Supervisor', desc: 'StateGraph orchestrator routes to agents concurrently via asyncio.gather', color: '#f472b6' },
  { emoji: '🔧', n: '04', title: 'ReAct Agents', desc: 'LangGraph ReAct agents execute tool calls against SQLite-backed APIs (Product, Order, Cart, FAQ, Deals, Complaint)', color: '#34d399' },
  { emoji: '🛡', n: '05', title: 'Guardrails + QA', desc: 'PII masking, prompt-injection detection, then a second LLM evaluator critiques the response', color: '#fb923c' },
];

export function HowItWorks() {
  return (
    <section id="how-it-works" className="relative py-28 px-6 bg-white dark:bg-gray-900 transition-colors overflow-hidden">
      <PastelBlobs blobs={[
        { size: 400, top: '-5%', left: '60%', color: 'radial-gradient(circle, rgba(96,165,250,0.2) 0%, transparent 70%)', blur: 80 },
        { size: 350, bottom: '0%', left: '-5%', color: 'radial-gradient(circle, rgba(244,114,182,0.15) 0%, transparent 70%)', blur: 70 },
      ]} />

      <div className="max-w-6xl mx-auto relative z-10">
        <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="text-center mb-20">
          <div className="text-[11px] font-bold tracking-widest uppercase mb-3" style={{ color: '#a78bfa' }}>Pipeline Architecture</div>
          <h2 className="text-4xl lg:text-[44px] font-extrabold text-gray-800 dark:text-gray-100 mb-4">How It Works</h2>
          <p className="text-gray-400 max-w-lg mx-auto text-[15px] leading-relaxed">
            A production-grade 5-step pipeline with async routing, tool calling, memory, guardrails & self-critique.
          </p>
        </motion.div>

        <div className="grid md:grid-cols-5 gap-6">
          {STEPS.map(({ emoji, n, title, desc, color }, i) => (
            <motion.div key={title}
              initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }} transition={{ delay: i * 0.1 }}
              className="flex flex-col items-center text-center group">
              <div className="relative w-16 h-16 rounded-2xl flex items-center justify-center text-2xl mb-5 border transition-all group-hover:scale-105 group-hover:shadow-lg"
                style={{ background: `${color}12`, borderColor: `${color}25` }}>
                {emoji}
                <div className="absolute -top-2 -right-2 w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-black text-white" style={{ background: color }}>{n}</div>
              </div>
              <h4 className="font-bold text-gray-700 dark:text-gray-200 mb-2 text-sm">{title}</h4>
              <p className="text-gray-400 text-[12px] leading-relaxed">{desc}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

const AGENTS = [
  {
    emoji: '🛒', name: 'Product Agent', intent: 'PRODUCT_INQUIRY',
    color: '#a78bfa', bgLight: 'rgba(167,139,250,0.08)',
    desc: 'LangGraph ReAct agent with tool calling. Searches product catalog for pricing, stock, ratings, specs, and offers.',
    capabilities: ['Price lookup', 'Stock status', 'Typo-Tolerant Search', 'Category filter'],
    try: 'Tell me about the iPhone 18 Pro',
  },
  {
    emoji: '📦', name: 'Order Agent', intent: 'ORDER_TRACKING',
    color: '#60a5fa', bgLight: 'rgba(96,165,250,0.08)',
    desc: 'LangGraph ReAct agent connected to mock OMS API. Returns real-time status, carrier, tracking ID, and delivery timeline.',
    capabilities: ['Live status', 'Carrier & tracking', 'Delivery timeline', 'ETA prediction'],
    try: 'Where is my order #123?',
  },
  {
    emoji: '💬', name: 'FAQ Agent', intent: 'FAQ',
    color: '#34d399', bgLight: 'rgba(52,211,153,0.08)',
    desc: 'RAG-pattern agent. Retrieves policy documents from knowledge base, then generates grounded answers.',
    capabilities: ['Return policy', 'Shipping policy', 'Payment methods', 'Warranty info'],
    try: 'What is your return policy?',
  },
  {
    emoji: '🏷', name: 'Deals Agent', intent: 'PRICE_INQUIRY',
    color: '#fb923c', bgLight: 'rgba(251,146,60,0.08)',
    desc: 'Pricing intelligence agent. Checks price history trends, validates coupons, and advises on buy timing.',
    capabilities: ['Price history', 'Buy timing', 'Coupon validation', 'Deal finding'],
    try: 'Is this a good time to buy a laptop?',
  },
  {
    emoji: '🛍', name: 'Cart Agent', intent: 'CART_ACTION',
    color: '#8b5cf6', bgLight: 'rgba(139,92,246,0.08)',
    desc: 'Write-action agent with idempotency. Manages cart: add/remove items, apply coupons, generate checkout summaries.',
    capabilities: ['Add to cart', 'Apply coupon', 'View cart', 'Checkout'],
    try: 'Add iPhone 18 Pro to my cart',
  },
  {
    emoji: '🚨', name: 'Complaint Agent', intent: 'COMPLAINT',
    color: '#f472b6', bgLight: 'rgba(244,114,182,0.08)',
    desc: 'Escalation agent with auto-resolution limits. Checks complaint history, issues refunds under ₹5000, or escalates to human support.',
    capabilities: ['Complaint history', 'Auto-refund', 'Human escalation', 'Sentiment handling'],
    try: 'My order is late again and nobody is helping!',
  },
];

export function AgentsShowcase({ onTry }) {
  return (
    <section id="agents" className="relative py-24 px-6 bg-white dark:bg-gray-900 transition-colors overflow-hidden">
      <PastelBlobs blobs={[
        { size: 450, top: '10%', right: '-5%', color: 'radial-gradient(circle, rgba(167,139,250,0.15) 0%, transparent 70%)', blur: 80 },
        { size: 350, bottom: '5%', left: '5%', color: 'radial-gradient(circle, rgba(52,211,153,0.12) 0%, transparent 70%)', blur: 70 },
      ]} />

      <div className="max-w-6xl mx-auto relative z-10">
        <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="text-center mb-16">
          <div className="text-[11px] font-bold tracking-widest uppercase mb-3" style={{ color: '#34d399' }}>Meet the Team</div>
          <h2 className="text-4xl font-extrabold text-gray-800 dark:text-gray-100 mb-3">Specialized AI Agents</h2>
          <p className="text-gray-400 max-w-xl mx-auto text-[15px]">
            Each agent is an independent LLM-powered module with its own system prompt, tools, and API connections.
          </p>
        </motion.div>

        <div className="grid md:grid-cols-2 gap-5">
          {AGENTS.map((agent, i) => (
            <motion.div key={agent.name}
              initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }} transition={{ delay: i * 0.08 }}
              className="bg-white dark:bg-gray-800 rounded-2xl p-6 border border-gray-100 dark:border-gray-700 hover:shadow-lg hover:-translate-y-0.5 transition-all duration-200">
              <div className="flex items-start gap-4 mb-5">
                <div className="w-11 h-11 rounded-xl flex items-center justify-center text-xl shrink-0" style={{ background: agent.bgLight }}>
                  {agent.emoji}
                </div>
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <h3 className="font-bold text-gray-800 dark:text-gray-100 text-[15px]">{agent.name}</h3>
                    <span className="text-[9px] font-bold px-2 py-0.5 rounded-full text-white" style={{ background: agent.color }}>{agent.intent}</span>
                  </div>
                  <p className="text-[13px] text-gray-400 leading-relaxed">{agent.desc}</p>
                </div>
              </div>
              <div className="flex flex-wrap gap-2 mb-5">
                {agent.capabilities.map(c => (
                  <span key={c} className="text-[11px] font-medium px-3 py-1 rounded-full border"
                    style={{ background: agent.bgLight, borderColor: `${agent.color}30`, color: agent.color }}>{c}</span>
                ))}
              </div>
              <button onClick={() => onTry(agent.try)}
                className="w-full text-[13px] font-semibold py-2.5 rounded-xl border transition-all hover:text-white"
                style={{ borderColor: `${agent.color}50`, color: agent.color }}
                onMouseEnter={e => { e.currentTarget.style.background = agent.color; e.currentTarget.style.color = 'white'; }}
                onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = agent.color; }}>
                Try: "{agent.try}"
              </button>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

const STATS = [
  { value: '6', label: 'AI Agents', sub: 'Product, Order, FAQ, Deals, Cart, Complaint' },
  { value: '7', label: 'Pipeline Nodes', sub: 'LangGraph StateGraph' },
  { value: '2x', label: 'Memory Layers', sub: 'Session + Long-term (SQLite)' },
  { value: '18', label: 'Tools', sub: 'LangChain @tool functions' },
];

export function GradientBanner() {
  return (
    <section className="py-20 px-6 relative overflow-hidden"
      style={{ background: 'linear-gradient(135deg, #c084fc 0%, #818cf8 25%, #60a5fa 50%, #34d399 75%, #a3e635 100%)' }}>
      <div className="absolute inset-0 opacity-20"
        style={{ backgroundImage: 'radial-gradient(circle, rgba(255,255,255,0.3) 1px, transparent 1px)', backgroundSize: '20px 20px' }} />
      <div className="max-w-5xl mx-auto relative z-10">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
          {STATS.map((s, i) => (
            <motion.div key={s.label}
              initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }} transition={{ delay: i * 0.1 }}>
              <div className="text-5xl font-extrabold text-white mb-2">{s.value}</div>
              <div className="text-white/90 font-semibold text-sm mb-1">{s.label}</div>
              <div className="text-white/60 text-[12px]">{s.sub}</div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

const TECH = [
  { label: 'LangChain + LangGraph', desc: 'Core AI framework: LangChain for LLM abstraction, tools, structured output. LangGraph for stateful workflow orchestration.', category: 'AI Framework', color: '#a78bfa' },
  { label: 'Gemini 3.5 Flash Lite', desc: 'Google Gemini as the core LLM via langchain-google-genai. Used for all agents, classification, and evaluation.', category: 'AI / LLM', color: '#818cf8' },
  { label: 'LangGraph StateGraph', desc: 'Supervisor built as a compiled StateGraph with 7 nodes: guardrails -> memory -> classify -> dispatch -> aggregate -> evaluate -> output.', category: 'Orchestration', color: '#60a5fa' },
  { label: 'LangGraph ReAct Agents', desc: '6 agents built with create_react_agent() - autonomous tool-calling loop with LLM reasoning.', category: 'Agent Pattern', color: '#38bdf8' },
  { label: 'LangChain @tool Decorator', desc: '15+ tools defined with @tool. LLM autonomously decides which tools to call and with what arguments.', category: 'Tool Calling', color: '#f472b6' },
  { label: 'Structured Output (Pydantic)', desc: 'with_structured_output() ensures IntentResult and EvaluationResult conform to Pydantic schemas.', category: 'AI Engineering', color: '#fb923c' },
  { label: 'RAG Pattern (FAQ Agent)', desc: 'Retrieval-Augmented Generation: query -> knowledge base search -> context injection -> grounded LLM answer.', category: 'AI Pattern', color: '#f87171' },
  { label: 'Self-Critique Eval Loop', desc: 'Second LLM pass evaluates groundedness, relevance, format. Triggers retry with critique feedback if quality fails.', category: 'AI Safety', color: '#ef4444' },
  { label: 'Session + Long-term Memory', desc: 'Dual memory: SQLite-backed session history (last 6 turns) + SQLite user profiles with preferences injected into context.', category: 'Memory', color: '#34d399' },
  { label: 'Guardrails (Input + Output)', desc: 'PII masking (email, credit card), prompt-injection detection, output safety checks, auto-refund limits (₹5000 cap).', category: 'AI Safety', color: '#fbbf24' },
  { label: 'Async Parallel Execution', desc: 'asyncio.gather dispatches multiple agents concurrently. Exception handling per-agent prevents cascade failures.', category: 'Backend', color: '#4ade80' },
  { label: 'FastAPI + React 19', desc: 'Async FastAPI backend with CORS. React 19 frontend with Framer Motion, ReactMarkdown, Canvas particles.', category: 'Stack', color: '#94a3b8' },
];

export function TechStack() {
  return (
    <section id="tech-stack" className="relative py-28 px-6 bg-white dark:bg-gray-900 transition-colors overflow-hidden">
      <PastelBlobs blobs={[
        { size: 500, top: '-8%', right: '5%', color: 'radial-gradient(circle, rgba(167,139,250,0.12) 0%, transparent 70%)', blur: 90 },
        { size: 400, bottom: '5%', left: '-3%', color: 'radial-gradient(circle, rgba(52,211,153,0.1) 0%, transparent 70%)', blur: 80 },
      ]} />

      <div className="max-w-6xl mx-auto relative z-10">
        <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} className="text-center mb-16">
          <div className="text-[11px] font-bold tracking-widest uppercase mb-3" style={{ color: '#f472b6' }}>AI Engineering</div>
          <h2 className="text-4xl font-extrabold text-gray-800 dark:text-gray-100 mb-3">Technology Stack</h2>
          <p className="text-gray-400 mt-2 max-w-2xl mx-auto text-[15px] leading-relaxed">
            Production-grade AI engineering: multi-agent orchestration, structured LLM outputs, tool calling, RAG, memory layers, guardrails, and self-critique evaluation.
          </p>
        </motion.div>

        <div className="grid md:grid-cols-3 gap-4">
          {TECH.map((t, i) => (
            <motion.div key={t.label}
              initial={{ opacity: 0, y: 20 }} whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }} transition={{ delay: i * 0.04 }}
              className="bg-white dark:bg-gray-800 rounded-2xl p-5 border border-gray-100 dark:border-gray-700 hover:shadow-md hover:-translate-y-0.5 transition-all group">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-2 h-2 rounded-full shrink-0" style={{ background: t.color }} />
                <span className="text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full"
                  style={{ background: `${t.color}12`, color: t.color }}>{t.category}</span>
              </div>
              <div className="font-bold text-gray-700 dark:text-gray-200 text-[13px] mb-2 group-hover:text-gray-900 dark:group-hover:text-white transition-colors">{t.label}</div>
              <div className="text-gray-400 text-[12px] leading-relaxed">{t.desc}</div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

export function RecruiterInfo() {
  return (
    <section id="recruiter-info" className="py-20 px-6 border-t border-gray-100 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-800/50">
      <div className="max-w-4xl mx-auto">
        <motion.div initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }}>
          <div className="text-[11px] font-bold tracking-widest uppercase mb-3 text-indigo-500">For Recruiters & Evaluators</div>
          <h2 className="text-3xl font-extrabold text-gray-800 dark:text-gray-100 mb-6">Agent Workflow Architecture</h2>
          <div className="bg-white dark:bg-gray-800 rounded-2xl p-6 border border-gray-100 dark:border-gray-700 shadow-sm text-gray-600 dark:text-gray-300 text-sm leading-relaxed space-y-4">
            <p>
              ShopMate represents a production-ready approach to multi-agent LLM systems. When a user submits a query:
            </p>
            <ol className="list-decimal pl-5 space-y-2 text-gray-700 dark:text-gray-300">
              <li><strong>Context Enrichment:</strong> Long-term user preferences are fetched from SQLite and injected into the prompt.</li>
              <li><strong>Intent Routing:</strong> A LangChain classifier using <code className="bg-gray-100 px-1 rounded">with_structured_output</code> categorizes the message and evaluates urgency.</li>
              <li><strong>Parallel Dispatch:</strong> A Supervisor (LangGraph StateGraph) uses <code className="bg-gray-100 px-1 rounded">asyncio.gather</code> to spin up relevant ReAct agents concurrently.</li>
              <li><strong>Tool Execution:</strong> Each agent autonomously interacts with SQLite-backed APIs (Cart, Deals, Catalog) to gather ground truth.</li>
              <li><strong>Self-Critique & Safety:</strong> Before the final answer is shown to the user, an evaluator LLM critiques the response for hallucinations, tone, and safety constraints (like the ₹5000 refund cap).</li>
            </ol>
            <p className="mt-4">
              This architecture prevents monolith-prompt degradation, handles multi-intent queries efficiently, and ensures strict guardrails are enforced natively in the orchestrator pipeline.
            </p>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

export function Footer() {
  return (
    <footer className="bg-white dark:bg-gray-900 border-t border-gray-100 dark:border-gray-800 py-10 px-6">
      <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4 text-[13px] text-gray-400">
        <div className="flex items-center gap-2 font-bold text-gray-700 dark:text-gray-200 text-base">
          <img src="/logo.png" alt="ShopMate Logo" className="w-7 h-7 rounded-xl object-cover" />
          <span className="tracking-tight text-gray-900 dark:text-white">
            Shop<span className="text-transparent bg-clip-text bg-gradient-to-r from-[#6366F1] via-[#3B82F6] to-[#14B8A6]">Mate</span>
          </span>
        </div>
        <div className="text-center">E-Commerce Multi-Agent AI Concierge</div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5 text-green-500 text-[11px] font-bold">
            <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" /> Guardrails Active
          </div>
        </div>
      </div>
    </footer>
  );
}
