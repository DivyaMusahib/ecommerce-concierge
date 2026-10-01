import React from 'react';
import { motion } from 'framer-motion';

export function BotFace({ size = 160 }) {
  const s = size;
  const eyeW = s * 0.175, eyeH = s * 0.28;
  return (
    <div className="relative select-none" style={{ width: s, height: s, perspective: 800 }}>
      <div style={{ width: '100%', height: '100%', transform: 'rotateY(-20deg) rotateZ(3deg)', transformStyle: 'preserve-3d' }}>
        {[1.55, 1.32, 1.1].map((sc, i) => (
          <div key={i} className="absolute inset-0 rounded-full pointer-events-none"
            style={{ border: `1px solid rgba(180,160,240,${0.2 - i * 0.05})`, transform: `scale(${sc})` }} />
        ))}
        <div className="absolute inset-0 rounded-full" style={{ background: 'radial-gradient(circle, rgba(160,140,255,0.25) 0%, transparent 65%)', transform: 'scale(1.4)', filter: 'blur(16px)' }} />
        <div className="absolute inset-0 rounded-full" style={{
          background: `radial-gradient(circle at 33% 27%, #ffffff 0%, #f5f2ff 16%, #ddd6f8 40%, #9088d0 65%, #4838a8 100%)`,
          boxShadow: `0 ${s*0.1}px ${s*0.25}px rgba(80,60,160,0.3), inset 0 ${s*-0.08}px ${s*0.16}px rgba(20,10,60,0.3), inset 0 ${s*0.05}px ${s*0.12}px rgba(255,255,255,0.5)`,
        }} />
        <div className="absolute rounded-full" style={{ width: '40%', height: '28%', top: '10%', left: '18%', background: 'radial-gradient(ellipse at 38% 38%, rgba(255,255,255,0.88) 0%, transparent 70%)' }} />
        <div className="absolute rounded-full" style={{ width: '11%', height: '20%', top: '40%', left: '-4%', background: 'radial-gradient(circle at 60% 35%, #ece6ff, #7468c8)' }} />
        <div className="absolute rounded-full" style={{ width: '11%', height: '20%', top: '40%', right: '-4%', background: 'radial-gradient(circle at 40% 35%, #ece6ff, #7468c8)' }} />
        <div className="absolute rounded-full overflow-hidden" style={{ width: eyeW, height: eyeH, top: s*0.35, left: s*0.2, background: 'radial-gradient(circle at 38% 33%, #1c1438, #080516)', boxShadow: '0 0 8px rgba(100,80,220,0.4)' }}>
          <div className="absolute bg-white/80 rounded-full" style={{ width: '32%', height: '25%', top: '13%', left: '16%' }} />
        </div>
        <div className="absolute rounded-full overflow-hidden" style={{ width: eyeW, height: eyeH, top: s*0.35, right: s*0.2, background: 'radial-gradient(circle at 38% 33%, #1c1438, #080516)', boxShadow: '0 0 8px rgba(100,80,220,0.4)' }}>
          <div className="absolute bg-white/80 rounded-full" style={{ width: '32%', height: '25%', top: '13%', left: '16%' }} />
        </div>
      </div>
    </div>
  );
}

export function AgentChip({ emoji, label, desc, bg, style, delay }) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.7 }}
      animate={{ opacity: 1, scale: 1, y: [0, -8, 0] }}
      transition={{
        opacity: { delay, duration: 0.4 },
        scale: { delay, duration: 0.4, type: 'spring', stiffness: 180 },
        y: { delay: delay + 0.5, duration: 3.5 + delay * 0.3, repeat: Infinity, ease: 'easeInOut' },
      }}
      className="absolute flex items-center gap-2.5 rounded-2xl px-3.5 py-2 border shadow-md"
      style={{ borderColor: 'rgba(0,0,0,0.06)', background: 'rgba(255,255,255,0.92)', backdropFilter: 'blur(10px)', ...style }}
    >
      <div className="w-8 h-8 rounded-lg flex items-center justify-center text-base shrink-0" style={{ background: bg }}>{emoji}</div>
      <div>
        <div className="text-[12px] font-bold text-gray-800 whitespace-nowrap leading-tight">{label}</div>
        <div className="text-[10px] text-gray-400 whitespace-nowrap">{desc}</div>
      </div>
    </motion.div>
  );
}
