import React from 'react';
import { NavPage } from '../types';

interface SidebarProps {
  activePage: NavPage;
  onNavigate: (page: NavPage) => void;
  chunksCount?: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activePage,
  onNavigate,
  chunksCount = 14820,
}) => {
  const navItems: { id: NavPage; label: string; icon: string }[] = [
    { id: 'query-workbench', label: 'Query Workbench', icon: 'terminal' },
    { id: 'knowledge-nodes', label: 'Knowledge Nodes', icon: 'hub' },
    { id: 'vector-explorer', label: 'Vector Explorer', icon: 'scatter_plot' },
    { id: 'pipeline-telemetry', label: 'Pipeline Telemetry', icon: 'monitoring' },
    { id: 'evaluations', label: 'Evaluations', icon: 'rule' },
    { id: 'settings', label: 'Settings', icon: 'settings' },
  ];

  return (
    <aside className="fixed left-0 top-0 h-full w-64 bg-[#0a0e18] z-50 flex flex-col justify-between border-r border-[#1c1f2a] shadow-[0_1px_8px_rgba(0,0,0,0.04)] select-none">
      <div className="flex flex-col">
        {/* App Brand Header */}
        <div className="h-16 px-4 flex items-center justify-between border-b border-[#171b26]">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#262a35] flex items-center justify-center shadow-inner">
              <span className="material-symbols-outlined text-[#4cd7f6] text-[20px]">hub</span>
            </div>
            <div className="flex flex-col">
              <span className="text-[15px] font-semibold text-[#dfe2f1] tracking-tight leading-tight">
                Nexus RAG
              </span>
              <span className="font-mono text-[10px] text-[#bcc9cd] tracking-wide">
                v2.4 Telemetry
              </span>
            </div>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 rounded-full bg-[#4cd7f6] animate-pulse shadow-[0_0_8px_rgba(76,215,246,0.8)]" />
          </div>
        </div>

        {/* Global Index Metric Chip */}
        <div className="px-4 py-3">
          <div className="bg-[#171b26] rounded-lg p-3 border border-[#262a35]/40 transition-colors">
            <div className="flex items-center justify-between text-[#bcc9cd] font-mono text-[10px] uppercase tracking-wider mb-1">
              <span>GLOBAL INDEX</span>
              <span className="material-symbols-outlined text-[14px]">database</span>
            </div>
            <div className="font-mono text-[14px] text-[#4cd7f6] font-semibold">
              {chunksCount.toLocaleString()}{' '}
              <span className="text-[11px] text-[#bcc9cd] font-normal">chunks</span>
            </div>
          </div>
        </div>

        {/* Navigation Menu */}
        <nav className="flex flex-col gap-1 px-3 mt-1">
          {navItems.map((item) => {
            const isActive = activePage === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onNavigate(item.id)}
                className={`flex items-center justify-between px-3.5 py-2.5 rounded-lg text-[13px] font-medium transition-all text-left ${
                  isActive
                    ? 'bg-[#06b6d4] text-[#00424f] font-semibold shadow-[0_0_16px_-4px_rgba(6,182,212,0.4)]'
                    : 'text-[#bcc9cd] hover:bg-[#262a35]/60 hover:text-[#dfe2f1]'
                }`}
              >
                <span>{item.label}</span>
                <span className={`material-symbols-outlined text-[16px] opacity-70 ${isActive ? 'text-[#00424f]' : 'text-[#869397]'}`}>
                  {item.icon}
                </span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Bottom Telemetry Card */}
      <div className="p-4 flex flex-col gap-2.5 border-t border-[#171b26]">
        <div className="bg-[#171b26] rounded-lg p-3 flex flex-col gap-1 border border-[#262a35]/40">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] text-[#bcc9cd] tracking-wider uppercase">
              ACTIVE MODEL
            </span>
            <span className="font-mono text-[10px] text-[#d0bcff] px-1.5 py-0.5 rounded bg-[#3131c0]/30 border border-[#3131c0]/50">
              dense+bm25
            </span>
          </div>
          <div className="font-mono text-[12px] text-[#dfe2f1] font-medium truncate">
            mistral-embed:7b
          </div>
        </div>
        <div className="flex items-center justify-between px-1 text-[#bcc9cd]">
          <span className="font-mono text-[10px] tracking-wider uppercase">LATENCY</span>
          <span className="font-mono text-[11px] text-[#4cd7f6] font-semibold">
            24.8ms avg
          </span>
        </div>
      </div>
    </aside>
  );
};
