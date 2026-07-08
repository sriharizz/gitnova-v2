import React, { useState, useEffect } from 'react';
import { useIssues } from './hooks/useIssues';
import {
  ArrowRight, ArrowLeft, Check, Database, Brain, Monitor, Wrench, Smartphone,
  GitCommit, GitPullRequest, GitMerge, AlertCircle, Command,
  Code2, TerminalSquare, Search, Zap, Filter, X, ExternalLink
} from 'lucide-react';
import GitNovaLogo from './components/GitNovaLogo';
import IssueCard from './components/IssueCard';
import LoadingScreen from './components/LoadingScreen';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// --- VISUAL: Background ---
const BackgroundCosmos = () => (
  <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden bg-[#0f172a]">
    <div className="absolute top-[-20%] left-[20%] w-[600px] h-[600px] bg-violet-900/10 rounded-full blur-[120px]"></div>
    <div className="absolute bottom-[-20%] right-[20%] w-[600px] h-[600px] bg-indigo-900/10 rounded-full blur-[120px]"></div>
    <div className="absolute inset-0 bg-[linear-gradient(to_right,#80808012_1px,transparent_1px),linear-gradient(to_bottom,#80808012_1px,transparent_1px)] bg-[size:32px_32px]"></div>
  </div>
);

// --- COMPONENT: Terminal Hero ---
const TerminalHero = () => {
  const [lines, setLines] = useState([
    { text: "git-nova connect --github", color: "text-white" },
    { text: "Authenticated as user...", color: "text-slate-400" },
  ]);

  useEffect(() => {
    const sequence = [
      { text: "git-nova scan --difficulty=novice", color: "text-white", delay: 800 },
      { text: "Analyzing 1,240 repositories...", color: "text-violet-400", delay: 1600 },
      { text: "Filtering with Llama-3 AI...", color: "text-indigo-400", delay: 2400 },
      { text: "✓ Found 3 'Golden Ticket' issues", color: "text-emerald-400", delay: 3200 },
    ];
    let timeouts = [];
    sequence.forEach(({ text, color, delay }) => {
      const timeout = setTimeout(() => {
        setLines(prev => [...prev, { text, color }]);
      }, delay);
      timeouts.push(timeout);
    });
    return () => timeouts.forEach(clearTimeout);
  }, []);

  return (
    <div className="w-full bg-[#1e293b]/80 backdrop-blur-md border border-slate-700/50 rounded-xl shadow-2xl overflow-hidden font-mono text-xs md:text-sm relative z-20 ring-1 ring-white/5">
      <div className="bg-[#0f172a]/90 px-4 py-3 border-b border-slate-700/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-red-500/80"></div>
          <div className="w-3 h-3 rounded-full bg-yellow-500/80"></div>
          <div className="w-3 h-3 rounded-full bg-emerald-500/80"></div>
        </div>
        <div className="text-slate-500 text-[10px] font-bold tracking-widest uppercase">GitNova CLI v1.0</div>
      </div>
      <div className="p-6 h-64 flex flex-col gap-3 font-medium">
        {lines.map((line, i) => (
          <div key={i} className={`${line.color} flex items-center gap-2`}>
            {line.color === "text-white" && <span className="text-violet-400">$</span>}
            {line.text}
          </div>
        ))}
        <div className="flex items-center gap-2 mt-1">
          <span className="text-violet-400">$</span>
          <div className="w-2.5 h-5 bg-slate-400 animate-pulse"></div>
        </div>
      </div>
    </div>
  );
};



// --- COMPONENT: Inspector Panel ---
const InspectorPanel = ({ issue, onClose }) => {
  if (!issue) return null;

  // Dynamic Button Colors matching cards (Amber for Apprentice)
  const getButtonStyles = (diff) => {
    switch (diff) {
      case 'Novice': return 'bg-emerald-600 hover:bg-emerald-500 shadow-emerald-900/20';
      case 'Apprentice': return 'bg-indigo-600 hover:bg-indigo-500 shadow-indigo-900/20'; // Indigo
      case 'Contributor': return 'bg-rose-600 hover:bg-rose-500 shadow-rose-900/20';
      default: return 'bg-slate-700 hover:bg-slate-600';
    }
  };

  return (
    <div className="fixed right-0 top-0 h-screen w-full md:w-[45%] bg-[#0f172a]/95 backdrop-blur-xl border-l border-slate-700 shadow-2xl z-50 flex flex-col animate-in slide-in-from-right duration-300">
      <div className="p-6 border-b border-slate-700 flex justify-between items-start bg-[#162032]">
        <div className="flex gap-4">
          <img src={issue.avatar_url} className="w-12 h-12 rounded-lg border border-slate-600" />
          <div>
            <h2 className="text-lg font-bold text-white leading-tight mb-1">{issue.repo_name}</h2>
            <div className="flex gap-2">
              <span className="text-xs text-slate-400 font-mono">Issue #{Math.floor(Math.random() * 1000)}</span>
              <span className={`text-xs px-2 py-0.5 rounded-full font-bold uppercase border bg-opacity-10 
                            ${issue.difficulty === 'Novice' ? 'bg-emerald-500 text-emerald-400 border-emerald-500/20' :
                  issue.difficulty === 'Apprentice' ? 'bg-indigo-500 text-indigo-100 border-indigo-500/20' :
                    'bg-rose-500 text-rose-400 border-rose-500/20'}`}>
                {issue.difficulty === 'Apprentice' ? 'Medium' : issue.difficulty}
              </span>
            </div>
          </div>
        </div>
        <button onClick={onClose} className="p-2 hover:bg-slate-700 rounded-lg text-slate-400 hover:text-white transition-colors">
          <X className="w-5 h-5" />
        </button>
      </div>

      <div className="flex-grow overflow-y-auto p-6 space-y-6 custom-scrollbar">
        <div className="p-4 bg-[#1e293b] rounded-xl border border-slate-700">
          <h1 className="text-xl font-bold text-white mb-2">{issue.title}</h1>
          <p className="text-slate-400 text-sm">Opened on {new Date(issue.created_at).toLocaleDateString()}</p>
        </div>

        <div className="bg-[#0b0f19] rounded-xl border border-slate-700 overflow-hidden">
          <div className="px-4 py-2 bg-[#162032] border-b border-slate-700 flex items-center gap-2">
            <Zap className="w-4 h-4 text-violet-500" />
            <span className="text-xs font-bold text-violet-400 uppercase tracking-widest">AI Tactical Plan</span>
          </div>
          <div className="p-5 prose prose-invert prose-sm max-w-none">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code: ({ node, ...props }) => <code className="bg-[#1e293b] text-emerald-300 px-1.5 py-0.5 rounded border border-slate-700 font-mono text-xs" {...props} />,
                h3: ({ node, ...props }) => <h3 className="text-violet-300 font-mono text-sm uppercase mt-4 mb-2" {...props} />,
                li: ({ node, ...props }) => <li className="text-slate-300 my-1" {...props} />
              }}
            >
              {issue.summary}
            </ReactMarkdown>
          </div>
        </div>
      </div>

      {/* Footer Action - Added pb-10 to nudge it up significantly */}
      <div className="p-6 pb-10 border-t border-slate-700 bg-[#162032]">
        <a
          href={issue.html_url}
          target="_blank"
          rel="noopener noreferrer"
          className={`flex items-center justify-center w-full gap-2 py-4 text-white font-bold rounded-xl transition-all shadow-lg hover:scale-[1.02] ${getButtonStyles(issue.difficulty)}`}
        >
          <ExternalLink className="w-5 h-5" />
          View & Claim on GitHub
        </a>
      </div>
    </div>
  );
};

// --- PAGES ---

const LandingPage = ({ onNavigate }) => (
  <div className="relative w-full min-h-screen md:h-screen bg-[#0f172a] text-slate-300 font-sans flex flex-col overflow-y-auto md:overflow-hidden">
    <BackgroundCosmos />
    <div className="relative z-20 w-full max-w-7xl mx-auto px-6 py-6 flex justify-between items-center shrink-0">
      <div className="flex items-center gap-4 font-mono font-bold text-white tracking-tight cursor-pointer hover:opacity-80 transition-opacity">
        <GitNovaLogo className="w-12 h-12" />
        <span className="text-3xl">GitNova<span className="text-violet-500">_</span></span>
      </div>
      <div className="hidden md:flex items-center gap-3 text-[10px] font-bold text-slate-400 bg-slate-800/50 px-3 py-1.5 rounded-full border border-slate-700/50">
        <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></div>
        <span>SYSTEM ONLINE</span>
      </div>
    </div>

    <div className="relative z-10 w-full max-w-7xl mx-auto px-6 flex-grow flex flex-col justify-start md:justify-center h-full pt-8 md:pt-0 pb-10">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-10 lg:gap-16 items-center mb-12">
        <div className="text-left">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-violet-500/10 border border-violet-500/20 text-violet-300 text-[10px] font-bold tracking-wider uppercase mb-6">
            <Zap className="w-3 h-3" />
            <span>AI-Powered Contribution Engine</span>
          </div>
          <h1 className="text-4xl md:text-5xl lg:text-7xl font-extrabold text-white mb-6 leading-[1.1] tracking-tight">
            Push code. <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-violet-400 to-indigo-400">
              Not confusion.
            </span>
          </h1>
          <p className="text-slate-400 text-lg mb-8 max-w-lg leading-relaxed">
            Stop scrolling. We scan <strong>live</strong> GitHub issues, filter the noise, and hand-deliver <span className="text-slate-200 font-medium">Golden Ticket</span> tasks matching your exact skill level.
          </p>
          <button
            onClick={onNavigate}
            className="group relative inline-flex items-center gap-3 px-8 py-3.5 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white rounded-lg font-bold text-sm shadow-[0_0_20px_-5px_rgba(139,92,246,0.4)] transition-all hover:scale-[1.02]"
          >
            <span className="font-mono uppercase tracking-wide">Initialize Mission</span>
            <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
          </button>
        </div>
        <div className="w-full flex justify-center lg:justify-end">
          <TerminalHero />
        </div>
      </div>

      <div className="w-full shrink-0">
        <div className="flex items-center gap-4 mb-6">
          <div className="h-px flex-1 bg-gradient-to-r from-transparent via-slate-700 to-transparent"></div>
          <span className="font-mono text-[10px] text-slate-500 uppercase tracking-[0.2em]">Choose Your Path</span>
          <div className="h-px flex-1 bg-gradient-to-r from-transparent via-slate-700 to-transparent"></div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {/* Novice - Green */}
          <div className="bg-[#1e293b]/50 backdrop-blur-sm border border-slate-700/50 p-6 rounded-xl hover:border-emerald-500/30 transition-colors group flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <div className="p-2.5 bg-emerald-500/10 rounded-lg text-emerald-400"><GitPullRequest className="w-6 h-6" /></div>
              <span className="text-xs font-bold text-emerald-400 border border-emerald-500/20 px-2 py-0.5 rounded">EASY</span>
            </div>
            <h3 className="text-white font-bold text-xl mb-2">1. Novice</h3>
            <p className="text-slate-400 text-sm leading-relaxed">Fix typos and docs. Low pressure tasks to earn your first green square.</p>
          </div>
          {/* Medium - INDIGO (Structure/Logic) */}
          <div className="bg-[#1e293b] border border-indigo-500/30 p-6 rounded-xl shadow-[0_0_30px_-10px_rgba(99,102,241,0.25)] relative overflow-hidden group flex flex-col hover:border-indigo-400 transition-colors">
            <div className="flex items-center justify-between mb-4 relative z-10">
              <div className="p-2.5 bg-indigo-500/10 rounded-lg text-indigo-400"><Code2 className="w-6 h-6" /></div>
              <span className="text-xs font-bold text-indigo-200 bg-indigo-600 px-2 py-0.5 rounded">TARGET</span>
            </div>
            <h3 className="text-white font-bold text-xl mb-2 relative z-10">2. Medium</h3>
            <p className="text-slate-300 text-sm leading-relaxed relative z-10">Real bugs, real logic. AI guides you through the exact file structure.</p>
          </div>
          {/* Contributor - Rose */}
          <div className="bg-[#1e293b]/50 backdrop-blur-sm border border-slate-700/50 p-6 rounded-xl hover:border-rose-500/30 transition-colors group flex flex-col">
            <div className="flex items-center justify-between mb-4">
              <div className="p-2.5 bg-rose-500/10 rounded-lg text-rose-400"><GitMerge className="w-6 h-6" /></div>
              <span className="text-xs font-bold text-rose-400 border border-rose-500/20 px-2 py-0.5 rounded">HARD</span>
            </div>
            <h3 className="text-white font-bold text-xl mb-2">3. Contributor</h3>
            <p className="text-slate-400 text-sm leading-relaxed">Optimization & refactoring. Architect solutions for major repositories.</p>
          </div>
        </div>
      </div>
    </div>
  </div>
);

const InterestsPage = ({ interests, selectedInterests, toggleInterest, handleFetchRecommendations, hookLoading, isScanning, onNavigateHome, hookError }) => (
  <div className="relative w-full min-h-screen md:h-screen bg-[#0f172a] text-white flex flex-col overflow-y-auto md:overflow-hidden">
    <BackgroundCosmos />
    <div className="relative z-10 max-w-7xl mx-auto px-8 w-full h-full flex flex-col justify-start md:justify-center pt-20 md:pt-0 pb-10">
      <div onClick={onNavigateHome} className="absolute top-8 left-8 flex items-center gap-4 cursor-pointer opacity-80 hover:opacity-100 transition-opacity">
        <GitNovaLogo className="w-12 h-12" />
        <span className="font-mono font-bold text-3xl">GitNova_</span>
      </div>
      <div className="text-center mb-16">
        <h2 className="text-4xl md:text-6xl font-bold mb-4 text-white tracking-tight">Choose Your Stack.</h2>
        <p className="text-slate-400 font-medium text-lg">Scanning 10,000+ active Open Source issues.</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-12 max-w-6xl mx-auto w-full">
        {interests.map(interest => {
          const Icon = interest.icon;
          const isSelected = selectedInterests.includes(interest.id);
          return (
            <button
              key={interest.id}
              onClick={() => toggleInterest(interest.id)}
              className={`p-8 rounded-2xl border text-left transition-all duration-300 group relative flex flex-col justify-between h-44
                ${isSelected
                  ? 'bg-[#1e293b] border-violet-500 shadow-[0_0_40px_-5px_rgba(139,92,246,0.5)] scale-[1.03] ring-1 ring-violet-500/50'
                  : 'bg-[#1e293b] border-slate-700 hover:border-violet-500/50 hover:shadow-xl hover:bg-[#1e293b] hover:-translate-y-1'
                }`}
            >
              <div className={`flex items-center justify-between ${isSelected ? 'text-violet-400' : 'text-slate-500 group-hover:text-slate-400'}`}>
                <Icon className="w-8 h-8" />
                {isSelected && <div className="w-3 h-3 rounded-full bg-violet-500 shadow-[0_0_15px_#8b5cf6]"></div>}
              </div>
              <div>
                <div className={`font-bold text-2xl mb-2 ${isSelected ? 'text-white' : 'text-slate-300'}`}>{interest.title}</div>
                <div className="text-sm font-mono text-slate-500">{interest.subtitle}</div>
              </div>
            </button>
          );
        })}
      </div>

      {hookError && (
        <div className="max-w-md mx-auto mb-8 p-3 bg-red-950/30 border border-red-900/50 rounded text-red-400 text-center font-mono text-xs flex items-center justify-center gap-2">
          <AlertCircle className="w-4 h-4" /> {hookError}
        </div>
      )}

      <div className="flex justify-center">
        <button
          onClick={handleFetchRecommendations}
          disabled={hookLoading || isScanning || selectedInterests.length < 1}
          className={`px-12 py-5 rounded-xl font-bold font-mono text-base transition-all flex items-center gap-3 shadow-xl ${hookLoading || isScanning || selectedInterests.length < 1
            ? 'bg-slate-800 text-slate-600 cursor-not-allowed border border-slate-700'
            : 'bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white hover:scale-[1.02] shadow-[0_0_30px_-5px_rgba(139,92,246,0.6)] ring-1 ring-white/20'
            }`}
        >
          {hookLoading || isScanning ? "SCANNING GITHUB..." : "START SCAN"}
        </button>
      </div>
    </div>

  </div>
);

const RecommendationsPage = ({
  activeInterest, allIssues, visibleIssues, handleLoadMore,
  selectedIssue, setSelectedIssue, onNavigateHome, onNavigateBack, isExpanded, interests,
  difficultyFilter, setDifficultyFilter, setVisibleCount
}) => {
  const currentInterest = interests.find(i => i.id === activeInterest);
  const title = currentInterest ? currentInterest.title : activeInterest;

  return (
    <div className="w-full min-h-screen text-slate-300 bg-[#0f172a] overflow-hidden flex flex-col font-sans">
      <BackgroundCosmos />

      {selectedIssue && (
        <InspectorPanel
          issue={selectedIssue}
          onClose={() => setSelectedIssue(null)}
        />
      )}

      <div className={`relative z-10 h-full flex flex-col transition-all duration-300 ${selectedIssue ? 'w-full md:w-[55%] pr-4 pl-6' : 'max-w-6xl mx-auto px-6 w-full'}`}>

        <div className="pt-8 pb-6">
          <div className="flex items-center justify-between mb-8">
            <div onClick={onNavigateHome} className="flex items-center gap-4 cursor-pointer w-fit opacity-80 hover:opacity-100 transition-opacity">
              <GitNovaLogo className="w-12 h-12" />
              <span className="font-mono font-bold text-3xl text-slate-100">GitNova_</span>
            </div>
            <button onClick={onNavigateBack} className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-800/80 border border-slate-700 hover:border-violet-500/50 text-slate-400 hover:text-white transition-all text-sm font-mono">
              <ArrowLeft className="w-4 h-4" />
              Back
            </button>
          </div>

          <div className="bg-[#1e293b]/60 backdrop-blur-md border border-slate-700/50 p-6 rounded-2xl mb-6 shadow-xl flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <span className="w-2 h-2 rounded-full bg-violet-500 animate-pulse"></span>
                <span className="text-[10px] font-bold text-violet-400 uppercase tracking-widest">Live Feed</span>
              </div>
              <h2 className="text-3xl md:text-4xl font-extrabold text-white leading-none">
                {title}
              </h2>
            </div>

            <div className="flex items-center gap-3">
              <div className="flex flex-col items-end">
                <span className="text-2xl font-bold text-white">{allIssues.length}</span>
                <span className="text-[10px] text-slate-400 uppercase tracking-widest font-bold">Issues Found</span>
              </div>
              <div className="h-8 w-px bg-slate-700 mx-2"></div>
              <span className="px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 text-xs font-mono font-bold uppercase tracking-wider flex items-center gap-2">
                <Filter className="w-3 h-3" /> {title.toUpperCase()}
              </span>
            </div>
          </div>

          {/* Difficulty Filter */}
          <div className="flex gap-3 mb-1 overflow-x-auto pb-3 pt-1 pl-1 pr-1 custom-scrollbar w-full">
            {['All', 'Novice', 'Apprentice', 'Contributor'].map(level => {
              const isActive = difficultyFilter === level;
              let activeColor = '';
              if (level === 'All') activeColor = 'bg-violet-600 text-white border-violet-400 shadow-[0_0_15px_-3px_rgba(139,92,246,0.6)]';
              else if (level === 'Novice') activeColor = 'bg-emerald-600 text-white border-emerald-400 shadow-[0_0_15px_-3px_rgba(16,185,129,0.5)]';
              else if (level === 'Apprentice') activeColor = 'bg-indigo-600 text-white border-indigo-400 shadow-[0_0_15px_-3px_rgba(99,102,241,0.6)]';
              else if (level === 'Contributor') activeColor = 'bg-rose-600 text-white border-rose-400 shadow-[0_0_15px_-3px_rgba(244,63,94,0.6)]';

              return (
                <button
                  key={level}
                  onClick={() => { setDifficultyFilter(level); setVisibleCount(9); }}
                  className={`px-5 py-2 rounded-full text-xs font-bold font-mono transition-all shrink-0 border ${isActive
                      ? activeColor
                      : 'bg-[#1e293b] text-slate-400 border-slate-700 shadow-sm hover:border-slate-500 hover:bg-slate-800 hover:text-slate-200'
                    }`}
                >
                  {level === 'All' ? 'ALL LEVELS' : level === 'Novice' ? 'EASY (NOVICE)' : level === 'Apprentice' ? 'MEDIUM (APPRENTICE)' : 'HARD (CONTRIBUTOR)'}
                </button>
              );
            })}
          </div>
        </div>

        <div className="flex-grow overflow-y-auto pb-20 pt-1 pr-2 custom-scrollbar">
          <div className={`grid gap-4 transition-all duration-300 ${selectedIssue ? 'grid-cols-1 md:grid-cols-2' : 'grid-cols-1 md:grid-cols-3'}`}>
            {visibleIssues.length === 0 ? (
              <div className="col-span-full text-center py-24 border border-dashed border-slate-800 rounded-xl bg-slate-900/30">
                <TerminalSquare className="w-12 h-12 text-slate-700 mx-auto mb-4" />
                <h3 className="text-xl font-bold text-slate-400 mb-2">No Golden Tickets Found</h3>
                <p className="text-slate-500 font-mono text-sm">We couldn't find any issues matching this difficulty right now.<br />Try another filter or check back later.</p>
              </div>
            ) : (
              visibleIssues.map((issue, idx) => (
                <IssueCard
                  key={issue.id || idx}
                  issue={issue}
                  onSelect={setSelectedIssue}
                  isActive={selectedIssue?.id === issue.id}
                />
              ))
            )}
          </div>

          {!isExpanded && allIssues.length > visibleIssues.length && (
            <div className="flex justify-center mt-8">
              <button
                onClick={handleLoadMore}
                className="px-6 py-2.5 bg-slate-800 border border-slate-600 hover:border-violet-500 text-slate-300 hover:text-white rounded-lg font-mono text-xs transition-all flex items-center gap-2 shadow-lg"
              >
                <Command className="w-3.5 h-3.5 text-violet-400" />
                Load More Issues
              </button>
            </div>
          )}
        </div>
      </div>

    </div >
  );
};

// --- MAIN APP ---
const GitNavApp = () => {
  const [currentPage, setCurrentPage] = useState('landing');
  const [selectedInterests, setSelectedInterests] = useState(() => {
    const saved = localStorage.getItem('gitnav_interests');
    let parsed = saved ? JSON.parse(saved) : ['Frontend'];
    // Hot-fix: Migrate legacy 'Tools' to 'Data Science'
    if (parsed.includes('Tools')) {
      parsed = parsed.map(p => p === 'Tools' ? 'Data Science' : p);
    }
    return parsed;
  });

  const [queryCategory, setQueryCategory] = useState(null);
  const { issues: rawIssues, loading: hookLoading, error: hookError, fetchForCategory } = useIssues(queryCategory);

  const [allIssues, setAllIssues] = useState([]);
  const [difficultyFilter, setDifficultyFilter] = useState('All');
  const [visibleCount, setVisibleCount] = useState(9);
  const [selectedIssue, setSelectedIssue] = useState(null);
  const [isScanning, setIsScanning] = useState(false);

  const filteredIssues = allIssues.filter(i => difficultyFilter === 'All' || i.difficulty === difficultyFilter);
  const visibleIssues = filteredIssues.slice(0, visibleCount);
  const isExpanded = visibleCount >= filteredIssues.length;

  useEffect(() => {
    if (rawIssues) {
      const mappedIssues = rawIssues.map(issue => ({
        ...issue,
        html_url: issue.url,
        summary: issue.ai_hint,
        avatar_url: `https://github.com/${issue.repo_name.split('/')[0]}.png`
      }));
      const goodIssues = mappedIssues.filter(i => i.difficulty !== 'Master');
      const shuffled = goodIssues.sort(() => 0.5 - Math.random());
      setAllIssues(shuffled);
      setVisibleCount(9);
    }
  }, [rawIssues]);

  const interests = [
    { id: 'Frontend', title: 'Web / Frontend', icon: Code2, subtitle: 'React, Vue, CSS' },
    { id: 'Backend', title: 'Backend / APIs', icon: Database, subtitle: 'Node, Python, Go' },
    { id: 'AI', title: 'AI / ML Tools', icon: Brain, subtitle: 'PyTorch, TensorFlow' },
    { id: 'DevOps', title: 'Systems / DevOps', icon: Monitor, subtitle: 'Docker, K8s' },
    { id: 'Data Science', title: 'Data Science', icon: Wrench, subtitle: 'Pandas, Spark, Plotly' },
    { id: 'Mobile', title: 'Mobile Apps', icon: Smartphone, subtitle: 'React Native, Flutter' }
  ];

  const toggleInterest = (id) => {
    setSelectedInterests(prev =>
      prev.includes(id) ? [] : [id]
    );
  };

  const handleLoadMore = () => {
    setVisibleCount(prev => prev + 9);
  };

  const handleFetchRecommendations = async (e) => {
    e?.preventDefault();
    if (selectedInterests.length < 1) {
      alert("Please select at least one interest.");
      return;
    }
    localStorage.setItem('gitnav_interests', JSON.stringify(selectedInterests));

    setAllIssues([]);
    setIsScanning(true);

    // Await the data directly — no race condition possible
    const data = await fetchForCategory(selectedInterests[0]);

    // Process data inline before navigating
    const mappedIssues = (data || []).map(issue => ({
      ...issue,
      html_url: issue.url,
      summary: issue.ai_hint,
      avatar_url: `https://github.com/${issue.repo_name.split('/')[0]}.png`
    }));
    const goodIssues = mappedIssues.filter(i => i.difficulty !== 'Master');
    const shuffled = goodIssues.sort(() => 0.5 - Math.random());
    setAllIssues(shuffled);
    setVisibleCount(9);
    setDifficultyFilter('All');

    setQueryCategory(selectedInterests[0]);
    setIsScanning(false);
    setCurrentPage('recommendations');
  };

  return (
    <div className="bg-[#0f172a] min-h-screen text-slate-300 selection:bg-violet-500/30">
      {(hookLoading || isScanning) && <LoadingScreen />}

      {currentPage === 'landing' && (
        <LandingPage
          onNavigate={() => setCurrentPage('interests')}
        />
      )}

      {currentPage === 'interests' && (
        <InterestsPage
          interests={interests}
          selectedInterests={selectedInterests}
          toggleInterest={toggleInterest}
          handleFetchRecommendations={handleFetchRecommendations}
          hookLoading={hookLoading}
          isScanning={isScanning}
          hookError={hookError}
          onNavigateHome={() => setCurrentPage('landing')}
        />
      )}

      {currentPage === 'recommendations' && (
        <RecommendationsPage
          activeInterest={selectedInterests[0] || "General"}
          allIssues={filteredIssues}
          visibleIssues={visibleIssues}
          handleLoadMore={handleLoadMore}
          selectedIssue={selectedIssue}
          setSelectedIssue={setSelectedIssue}
          onNavigateHome={() => setCurrentPage('landing')}
          onNavigateBack={() => setCurrentPage('interests')}
          isExpanded={isExpanded}
          interests={interests}
          difficultyFilter={difficultyFilter}
          setDifficultyFilter={setDifficultyFilter}
          setVisibleCount={setVisibleCount}
        />
      )}
    </div>
  );
};

export default GitNavApp;