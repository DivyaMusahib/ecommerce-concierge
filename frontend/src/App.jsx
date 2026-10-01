import { useState, useEffect } from 'react';
import { Hero, HowItWorks, AgentsShowcase, GradientBanner, TechStack, RecruiterInfo, Footer } from './components/LandingSections';
import { LiveChat } from './components/LiveChat';
import { Moon, Sun } from 'lucide-react';

export default function App() {
  const [chatPrefill, setChatPrefill] = useState('');
  const [isDark, setIsDark] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('theme') === 'dark';
    }
    return false;
  });

  useEffect(() => {
    if (isDark) {
      document.documentElement.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('theme', 'light');
    }
  }, [isDark]);

  const scrollToDemo = () => document.getElementById('demo')?.scrollIntoView({ behavior: 'smooth' });
  const handleTry = (q) => {
    setChatPrefill(q);
    setTimeout(() => document.getElementById('demo')?.scrollIntoView({ behavior: 'smooth' }), 50);
  };

  return (
    <div className="overflow-x-hidden relative bg-white dark:bg-gray-900 transition-colors duration-300">
      <Hero onDemoClick={scrollToDemo} isDark={isDark} setIsDark={setIsDark} />
      <HowItWorks />
      <AgentsShowcase onTry={handleTry} />
      <GradientBanner />
      <LiveChat prefill={chatPrefill} setPrefill={setChatPrefill} />
      <TechStack />
      <RecruiterInfo />
      <Footer />
    </div>
  );
}
