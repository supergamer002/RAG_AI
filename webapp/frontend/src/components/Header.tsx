import { apiFetch, formatApiError } from '../api';
import React, { useState, useEffect } from 'react';
import { ThemeMode } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

interface HeaderProps {
  themeMode: ThemeMode;
  onToggleTheme: () => void;
  onOpenIngest: () => void;
  onOpenTerminal: () => void;
  onOpenDatabaseManager?: () => void;
  searchFilter: string;
  onSearchChange: (value: string) => void;
}

export const Header: React.FC<HeaderProps> = ({
  themeMode,
  onToggleTheme,
  onOpenIngest,
  onOpenTerminal,
  onOpenDatabaseManager,
  searchFilter,
  onSearchChange,
}) => {
  const [healthError, setHealthError] = useState<string | null>(null);
  const [health, setHealth] = useState<{ fastapi: boolean; lancedb: boolean; ollama: boolean }>({
    fastapi: true,
    lancedb: true,
    ollama: false,
  });

  useEffect(() => {
    const checkHealth = () => {
      apiFetch(`/api/health`)
        .then((res) => res.ok ? res.json() : null)
        .then((data) => {
          if (data) {
            setHealthError(null);
            setHealth({
              fastapi: !!data.fastapi,
              lancedb: !!data.lancedb,
              ollama: !!data.ollama,
            });
          }
        })
        .catch((err) => {
          setHealthError(formatApiError(err, 'Health check'));
          setHealth({ fastapi: false, lancedb: false, ollama: false });
        });
    };

    checkHealth();
    const interval = setInterval(checkHealth, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="fixed top-0 left-64 right-0 h-16 bg-[#0f131d]/85 backdrop-blur-xl z-40 border-b border-[#262a35]/60">
      <div className="h-16 w-full px-6 flex items-center justify-between gap-4">
        {/* Left Server Status Indicators */}
        <div className="flex items-center gap-2 overflow-x-auto py-1 scrollbar-none">
          {/* FastAPI */}
          <div className="flex items-center gap-1.5 bg-[#171b26] px-2.5 py-1.5 rounded-lg border border-[#06b6d4]/30 shadow-[0_0_12px_-4px_rgba(6,182,212,0.25)] shrink-0">
            <span className={`w-1.5 h-1.5 rounded-full ${health.fastapi ? 'bg-[#4cd7f6] animate-ping' : 'bg-[#ffb4ab]'}`} />
            <span className="font-mono text-[11px] text-[#bcc9cd]">FastAPI:</span>
            <span className={`font-mono text-[11px] font-semibold ${health.fastapi ? 'text-[#4cd7f6]' : 'text-[#ffb4ab]'}`}>
              {health.fastapi ? 'Online' : 'Offline'}
            </span>
          </div>

          {/* LanceDB */}
          <div className="flex items-center gap-1.5 bg-[#171b26] px-2.5 py-1.5 rounded-lg border border-[#262a35] shrink-0">
            <span className={`w-1.5 h-1.5 rounded-full ${health.lancedb ? 'bg-[#4cd7f6]' : 'bg-[#ffb4ab]'}`} />
            <span className="font-mono text-[11px] text-[#bcc9cd]">LanceDB:</span>
            <span className={`font-mono text-[11px] font-medium ${health.lancedb ? 'text-[#dfe2f1]' : 'text-[#ffb4ab]'}`}>
              {health.lancedb ? 'Connected' : 'Error'}
            </span>
          </div>

          {/* Ollama */}
          <div className="flex items-center gap-1.5 bg-[#171b26] px-2.5 py-1.5 rounded-lg border border-[#262a35] shrink-0">
            <span className={`w-1.5 h-1.5 rounded-full ${health.ollama ? 'bg-[#d0bcff]' : 'bg-[#ffb4ab]'}`} />
            <span className="font-mono text-[11px] text-[#bcc9cd]">Ollama:</span>
            <span className={`font-mono text-[11px] font-medium ${health.ollama ? 'text-[#d0bcff]' : 'text-[#ffb4ab]'}`}>
              {health.ollama ? 'Ready' : 'Standby'}
            </span>
          </div>

          {/* CrossEncoder */}
          <div className="hidden lg:flex items-center gap-1.5 bg-[#171b26] px-2.5 py-1.5 rounded-lg border border-[#262a35] shrink-0">
            <span className="w-1.5 h-1.5 rounded-full bg-[#869397]" />
            <span className="font-mono text-[11px] text-[#bcc9cd]">CrossEncoder:</span>
            <span className="font-mono text-[11px] text-[#869397]">Lazy Standby</span>
          </div>
        </div>

        {/* Right Controls */}
        <div className="flex items-center gap-3">
          {/* Search Box */}
          <div className="relative hidden md:flex items-center">
            <span className="material-symbols-outlined absolute left-3 text-[#bcc9cd] text-[18px]">
              search
            </span>
            <input
              type="text"
              value={searchFilter}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Filter chunks, nodes, or logs..."
              className="w-60 lg:w-72 bg-[#171b26] text-[#dfe2f1] placeholder:text-[#869397] text-[12px] pl-9 pr-3 py-1.5 rounded-lg border border-[#262a35] focus:outline-none focus:ring-1 focus:ring-[#4cd7f6] transition-all"
            />
            {searchFilter && (
              <button
                onClick={() => onSearchChange('')}
                className="absolute right-2 text-[#869397] hover:text-[#dfe2f1] text-[12px]"
              >
                ✕
              </button>
            )}
          </div>

          {/* Database Manager Trigger */}
          {onOpenDatabaseManager && (
            <button
              onClick={onOpenDatabaseManager}
              className="flex items-center gap-1.5 bg-[#262a35] hover:bg-[#353944] text-[#dfe2f1] px-3 py-1.5 rounded-lg text-[12px] font-medium transition-colors border border-[#3d494c]/40 cursor-pointer shadow-sm"
              title="Gestisci Database LanceDB"
            >
              <span className="material-symbols-outlined text-[16px] text-[#4cd7f6]">database</span>
              <span className="font-mono">Database</span>
            </button>
          )}

          {/* Direct Theme Toggle */}
          <button
            onClick={onToggleTheme}
            className="flex items-center gap-1.5 bg-[#262a35] hover:bg-[#353944] text-[#dfe2f1] px-3 py-1.5 rounded-lg text-[12px] font-medium transition-colors border border-[#3d494c]/40 cursor-pointer"
            title="Alterna Tema Scuro / Chiaro"
          >
            <span className="material-symbols-outlined text-[16px] text-[#4cd7f6]">
              {themeMode === 'light' ? 'dark_mode' : 'light_mode'}
            </span>
            <span className="hidden sm:inline font-mono">Tema</span>
          </button>

          {/* Quick Ingest Button */}
          <button
            onClick={onOpenIngest}
            className="flex items-center gap-1.5 bg-[#262a35] hover:bg-[#353944] text-[#dfe2f1] px-3 py-1.5 rounded-lg text-[12px] font-medium transition-colors border border-[#3d494c]/40 cursor-pointer shadow-sm"
          >
            <span className="material-symbols-outlined text-[16px] text-[#4cd7f6]">add</span>
            <span className="font-mono">Ingest</span>
          </button>

          {/* Icon Actions */}
          <div className="flex items-center gap-1">
            <button
              onClick={onOpenTerminal}
              className="w-8 h-8 rounded-lg bg-[#262a35] hover:bg-[#353944] text-[#bcc9cd] hover:text-[#dfe2f1] flex items-center justify-center transition-colors border border-[#3d494c]/30"
              title="Apri Telemetria & Log Terminale"
            >
              <span className="material-symbols-outlined text-[18px]">terminal</span>
            </button>
            <div
              className="w-8 h-8 rounded-lg bg-[#262a35] hover:bg-[#353944] text-[#bcc9cd] hover:text-[#dfe2f1] flex items-center justify-center transition-colors border border-[#3d494c]/30 cursor-pointer relative"
              title={healthError || "Notifiche di Sistema"}
            >
              <span className="material-symbols-outlined text-[18px]">notifications</span>
              <span className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-[#4cd7f6]" />
            </div>
          </div>

          {/* Runtime status — deliberately non-interactive until a real identity provider exists */}
          <div
            className="w-8 h-8 rounded-full border border-[#3d494c]/60 bg-[#262a35] flex items-center justify-center"
            title={healthError || 'Stato runtime RAG'}
            aria-label="Stato runtime RAG"
          >
            <span className={`material-symbols-outlined text-[18px] ${health.fastapi ? 'text-[#4cd7f6]' : 'text-[#ffb4ab]'}`}>
              {health.fastapi ? 'hub' : 'cloud_off'}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
};
