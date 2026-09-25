import React, { useState } from 'react';
import { AppSettings, SettingsTab, ThemeMode } from '../types';

interface SettingsViewProps {
  settings: AppSettings;
  onUpdateSettings: (newSettings: Partial<AppSettings>) => void;
  onSelectTheme: (mode: ThemeMode) => void;
  onTestConnections: () => void;
  onRestartWorker: () => void;
  onSave: () => void;
  onReset: () => void;
}

export const SettingsView: React.FC<SettingsViewProps> = ({
  settings,
  onUpdateSettings,
  onSelectTheme,
  onTestConnections,
  onRestartWorker,
  onSave,
  onReset,
}) => {
  const [activeTab, setActiveTab] = useState<SettingsTab>('runtime');
  const [showSecret, setShowSecret] = useState(false);
  const [isTesting, setIsTesting] = useState(false);

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

  const handleTestPing = () => {
    setIsTesting(true);
    fetch(`${API_BASE_URL}/api/health`)
      .then((res) => res.json())
      .then((data) => {
        setIsTesting(false);
        const fast = data.fastapi ? '200 OK' : 'Offline';
        const lance = data.lancedb ? 'Active' : 'Error';
        const ollama = data.ollama ? 'Online' : 'Offline';
        onTestConnections();
      })
      .catch(() => {
        setIsTesting(false);
        onTestConnections();
      });
  };

  return (
    <div className="relative w-full overflow-hidden">
      {/* Subtle Ambient Glow Orbs */}
      <div className="absolute -top-24 right-1/4 w-96 h-96 bg-[#4cd7f6]/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute top-80 -left-20 w-80 h-80 bg-[#3131c0]/20 rounded-full blur-3xl pointer-events-none" />

      <div className="p-6 flex flex-col gap-6 max-w-[1600px] mx-auto w-full relative z-10">
        {/* Header Banner / Control Horizon */}
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 bg-[#171b26] p-6 rounded-xl border border-[#262a35] shadow-lg relative overflow-hidden">
          <div className="absolute right-0 top-0 bottom-0 w-1/3 bg-gradient-to-l from-[#4cd7f6]/5 to-transparent pointer-events-none" />

          <div className="flex items-center gap-4 min-w-0">
            <div className="w-12 h-12 rounded-xl bg-[#262a35] flex items-center justify-center text-[#4cd7f6] shadow-[0_0_24px_rgba(76,215,246,0.25)] shrink-0 border border-[#3d494c]/50">
              <span className="material-symbols-outlined text-[28px]">tune</span>
            </div>
            <div className="flex flex-col min-w-0">
              <div className="flex items-center gap-1.5 font-mono text-[11px] text-[#4cd7f6] uppercase tracking-wider">
                <span>System Configuration Hub</span>
                <span>•</span>
                <span className="text-[#bcc9cd]">SYS_CONF.TOML</span>
              </div>
              <h1 className="text-[24px] sm:text-[28px] text-[#dfe2f1] tracking-tight font-semibold truncate leading-tight mt-0.5">
                Parametri di Rete &amp; Orchestrazione
              </h1>
              <p className="text-[13px] text-[#bcc9cd] mt-0.5 max-w-3xl">
                Regola a caldo i runtime FastAPI, gli indici LanceDB ad alta dimensionalità, le soglie Docling e la latenza dei pesi neurali locali.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2.5 w-full lg:w-auto shrink-0">
            <button
              onClick={handleTestPing}
              className="flex items-center gap-2 bg-[#262a35] hover:bg-[#353944] text-[#dfe2f1] px-4 py-2 rounded-lg font-mono text-[12px] transition-all border border-[#3d494c]/40 cursor-pointer shadow-sm"
            >
              <span className={`material-symbols-outlined text-[#4cd7f6] text-[18px] ${isTesting ? 'animate-spin' : ''}`}>
                cell_tower
              </span>
              <span>{isTesting ? 'Test in corso...' : 'Verifica Connessioni a Caldo'}</span>
            </button>

            <button
              onClick={onRestartWorker}
              className="flex items-center gap-2 bg-[#262a35] hover:bg-[#353944] text-[#ffb4ab] px-4 py-2 rounded-lg font-mono text-[12px] transition-all border border-[#93000a]/40 cursor-pointer shadow-sm hover:border-[#ffb4ab]/40"
            >
              <span className="material-symbols-outlined text-[18px]">restart_alt</span>
              <span>Riavvia Worker FastAPI</span>
            </button>
          </div>
        </div>

        {/* Quick Metrics Strip */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Metric 1 */}
          <div className="bg-[#171b26] p-4 rounded-xl flex items-center justify-between border border-[#262a35] shadow-sm">
            <div className="flex flex-col">
              <span className="font-mono text-[10px] text-[#bcc9cd] uppercase tracking-wider">
                Storage Index VFS
              </span>
              <span className="text-[20px] text-[#dfe2f1] font-semibold mt-0.5">1.84 GB</span>
              <span className="font-mono text-[11px] text-[#4cd7f6]">
                {settings.tableName} [Lance 0.12]
              </span>
            </div>
            <div className="w-10 h-10 rounded-lg bg-[#1c1f2a] flex items-center justify-center text-[#4cd7f6] border border-[#262a35]">
              <span className="material-symbols-outlined text-[22px]">database</span>
            </div>
          </div>

          {/* Metric 2 */}
          <div className="bg-[#171b26] p-4 rounded-xl flex items-center justify-between border border-[#262a35] shadow-sm">
            <div className="flex flex-col">
              <span className="font-mono text-[10px] text-[#bcc9cd] uppercase tracking-wider">
                VRAM Dedicata Ollama
              </span>
              <span className="text-[20px] text-[#dfe2f1] font-semibold mt-0.5">4.22 / 12.0 GB</span>
              <span className="font-mono text-[11px] text-[#d0bcff]">
                Keep-Alive {settings.keepAliveSeconds}s Lock
              </span>
            </div>
            <div className="w-10 h-10 rounded-lg bg-[#1c1f2a] flex items-center justify-center text-[#d0bcff] border border-[#262a35]">
              <span className="material-symbols-outlined text-[22px]">memory</span>
            </div>
          </div>

          {/* Metric 3 */}
          <div className="bg-[#171b26] p-4 rounded-xl flex items-center justify-between border border-[#262a35] shadow-sm">
            <div className="flex flex-col">
              <span className="font-mono text-[10px] text-[#bcc9cd] uppercase tracking-wider">
                Pipeline Token Window
              </span>
              <span className="text-[20px] text-[#dfe2f1] font-semibold mt-0.5">
                {settings.chunkSize} Tokens
              </span>
              <span className="font-mono text-[11px] text-[#bcc9cd]">
                Overlap {settings.chunkOverlap}% ({Math.round(settings.chunkSize * (settings.chunkOverlap / 100))} tokens)
              </span>
            </div>
            <div className="w-10 h-10 rounded-lg bg-[#1c1f2a] flex items-center justify-center text-[#c0c1ff] border border-[#262a35]">
              <span className="material-symbols-outlined text-[22px]">splitscreen</span>
            </div>
          </div>

          {/* Metric 4 */}
          <div className="bg-[#171b26] p-4 rounded-xl flex items-center justify-between border border-[#262a35] shadow-sm">
            <div className="flex flex-col">
              <span className="font-mono text-[10px] text-[#bcc9cd] uppercase tracking-wider">
                Top-K / Rerank Target
              </span>
              <span className="text-[20px] text-[#dfe2f1] font-semibold mt-0.5">
                {settings.topKCandidates} → {settings.topNRerank}
              </span>
              <span className="font-mono text-[11px] text-[#4cd7f6] truncate max-w-[160px]">
                ms-marco-MiniLM-L-6
              </span>
            </div>
            <div className="w-10 h-10 rounded-lg bg-[#1c1f2a] flex items-center justify-center text-[#4cd7f6] border border-[#262a35]">
              <span className="material-symbols-outlined text-[22px]">filter_list</span>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="bg-[#0a0e18] p-1 rounded-xl border border-[#262a35] flex flex-wrap gap-1 shadow-inner">
          {[
            { id: 'runtime' as SettingsTab, label: 'Generali & Runtime', icon: 'speed' },
            { id: 'lancedb' as SettingsTab, label: 'LanceDB & Vettori', icon: 'hub' },
            { id: 'docling' as SettingsTab, label: 'Ingestion & Docling', icon: 'description' },
            { id: 'models' as SettingsTab, label: 'Modelli & Endpoint', icon: 'neurology' },
            { id: 'security' as SettingsTab, label: 'API & Sicurezza', icon: 'shield' },
          ].map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-1.5 px-4 py-2.5 rounded-lg font-mono text-[12px] transition-all cursor-pointer ${
                  isActive
                    ? 'bg-[#06b6d4] text-[#00424f] font-semibold shadow-[0_0_16px_-4px_rgba(6,182,212,0.35)]'
                    : 'text-[#bcc9cd] hover:text-[#dfe2f1] hover:bg-[#262a35]'
                }`}
              >
                <span className="material-symbols-outlined text-[16px]">{tab.icon}</span>
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Main Settings Body */}
        <div className="flex flex-col gap-6">
          {/* TAB 1: Generali & Runtime */}
          {activeTab === 'runtime' && (
            <div className="flex flex-col gap-6">
              {/* Aspetto & Tema Interfaccia Card */}
              <div className="bg-[#171b26] p-6 rounded-xl border border-[#262a35] shadow-md flex flex-col gap-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-[#262a35]">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-[#262a35] flex items-center justify-center text-[#4cd7f6] border border-[#3d494c]/40">
                      <span className="material-symbols-outlined text-[22px]">palette</span>
                    </div>
                    <div className="flex flex-col">
                      <div className="flex items-center gap-2">
                        <span className="text-[16px] text-[#dfe2f1] font-semibold">
                          Aspetto &amp; Tema Interfaccia
                        </span>
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-[#4cd7f6]/10 text-[#4cd7f6] border border-[#4cd7f6]/20">
                          GUI Dynamic
                        </span>
                      </div>
                      <span className="text-[12px] text-[#bcc9cd]">
                        Scegli tra la palette scura ad alta densità per ambienti di lavoro notturni o la modalità chiara ad alto contrasto.
                      </span>
                    </div>
                  </div>

                  {/* Direct Switch Toggle */}
                  <div className="flex items-center gap-3 bg-[#0a0e18] px-4 py-2 rounded-lg border border-[#262a35] self-start sm:self-auto shadow-inner">
                    <span className="material-symbols-outlined text-[18px] text-[#bcc9cd]">
                      dark_mode
                    </span>
                    <span className="font-mono text-[11px] text-[#bcc9cd] font-medium">Tema Chiaro</span>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={settings.themeMode === 'light'}
                        onChange={(e) => onSelectTheme(e.target.checked ? 'light' : 'dark')}
                        className="sr-only peer"
                      />
                      <div className="w-11 h-6 bg-[#262a35] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white peer-checked:bg-[#4cd7f6] after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-[#003640] after:border-[#1c1f2a] after:border after:rounded-full after:h-5 after:w-5 after:transition-all" />
                    </label>
                    <span className="material-symbols-outlined text-[18px] text-[#4cd7f6]">
                      light_mode
                    </span>
                  </div>
                </div>

                {/* 3 Visual Theme Option Cards */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-1">
                  {/* Option 1: Obsidian Dark */}
                  <button
                    type="button"
                    onClick={() => onSelectTheme('dark')}
                    className={`flex flex-col gap-2.5 p-4 rounded-xl text-left transition-all border-2 relative cursor-pointer ${
                      settings.themeMode === 'dark'
                        ? 'border-[#4cd7f6] bg-[#0a0e18] shadow-[0_0_16px_-4px_rgba(76,215,246,0.3)]'
                        : 'border-[#262a35] bg-[#0a0e18] hover:border-[#4cd7f6]/50'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <span className="material-symbols-outlined text-[#4cd7f6] text-[20px]">
                          dark_mode
                        </span>
                        <span className="text-[14px] text-[#dfe2f1] font-semibold">
                          Scuro (Obsidian)
                        </span>
                      </div>
                      <span className="material-symbols-outlined text-[#4cd7f6] text-[20px]">
                        {settings.themeMode === 'dark' ? 'check_circle' : 'radio_button_unchecked'}
                      </span>
                    </div>

                    {/* Mini Visual Preview Dark */}
                    <div className="w-full h-20 rounded-lg bg-[#0f131d] border border-[#313540] p-2 flex flex-col justify-between overflow-hidden shadow-inner pointer-events-none">
                      <div className="flex items-center justify-between border-b border-[#262a35] pb-1.5">
                        <div className="flex items-center gap-1.5">
                          <div className="w-2.5 h-2.5 rounded-full bg-[#4cd7f6]" />
                          <div className="w-12 h-1.5 rounded bg-[#313540]" />
                        </div>
                        <div className="w-6 h-1.5 rounded bg-[#4cd7f6]/40" />
                      </div>
                      <div className="grid grid-cols-3 gap-1">
                        <div className="h-6 rounded bg-[#1c1f2a] border border-[#313540]/60 flex items-center px-1">
                          <div className="w-full h-1 bg-[#4cd7f6]/60 rounded" />
                        </div>
                        <div className="h-6 rounded bg-[#1c1f2a] border border-[#313540]/60 flex items-center px-1">
                          <div className="w-full h-1 bg-[#c0c1ff]/60 rounded" />
                        </div>
                        <div className="h-6 rounded bg-[#1c1f2a] border border-[#313540]/60 flex items-center px-1">
                          <div className="w-full h-1 bg-[#313540] rounded" />
                        </div>
                      </div>
                    </div>

                    <span className="font-mono text-[11px] text-[#bcc9cd]">
                      Design nativo ad alta immersione visiva e ridotto affaticamento oculare.
                    </span>
                  </button>

                  {/* Option 2: Clean Slate Light */}
                  <button
                    type="button"
                    onClick={() => onSelectTheme('light')}
                    className={`flex flex-col gap-2.5 p-4 rounded-xl text-left transition-all border-2 relative cursor-pointer ${
                      settings.themeMode === 'light'
                        ? 'border-[#4cd7f6] bg-[#0a0e18] shadow-[0_0_16px_-4px_rgba(76,215,246,0.3)]'
                        : 'border-[#262a35] bg-[#0a0e18] hover:border-[#4cd7f6]/50'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <span className="material-symbols-outlined text-[#4cd7f6] text-[20px]">
                          light_mode
                        </span>
                        <span className="text-[14px] text-[#dfe2f1] font-semibold">
                          Chiaro (Clean Slate)
                        </span>
                      </div>
                      <span className="material-symbols-outlined text-[20px] text-[#bcc9cd]">
                        {settings.themeMode === 'light' ? 'check_circle' : 'radio_button_unchecked'}
                      </span>
                    </div>

                    {/* Mini Visual Preview Light */}
                    <div className="w-full h-20 rounded-lg bg-[#f8fafc] border border-[#cbd5e1] p-2 flex flex-col justify-between overflow-hidden shadow-sm pointer-events-none">
                      <div className="flex items-center justify-between border-b border-[#e2e8f0] pb-1.5">
                        <div className="flex items-center gap-1.5">
                          <div className="w-2.5 h-2.5 rounded-full bg-[#0891b2]" />
                          <div className="w-12 h-1.5 rounded bg-[#94a3b8]" />
                        </div>
                        <div className="w-6 h-1.5 rounded bg-[#0891b2]/40" />
                      </div>
                      <div className="grid grid-cols-3 gap-1">
                        <div className="h-6 rounded bg-white border border-[#e2e8f0] flex items-center px-1">
                          <div className="w-full h-1 bg-[#0891b2] rounded" />
                        </div>
                        <div className="h-6 rounded bg-white border border-[#e2e8f0] flex items-center px-1">
                          <div className="w-full h-1 bg-[#6366f1] rounded" />
                        </div>
                        <div className="h-6 rounded bg-white border border-[#e2e8f0] flex items-center px-1">
                          <div className="w-full h-1 bg-[#cbd5e1] rounded" />
                        </div>
                      </div>
                    </div>

                    <span className="font-mono text-[11px] text-[#bcc9cd]">
                      Massima leggibilità durante le ore diurne con contrasto elevato su sfondi neutri.
                    </span>
                  </button>

                  {/* Option 3: System Auto */}
                  <button
                    type="button"
                    onClick={() => onSelectTheme('system')}
                    className={`flex flex-col gap-2.5 p-4 rounded-xl text-left transition-all border-2 relative cursor-pointer ${
                      settings.themeMode === 'system'
                        ? 'border-[#4cd7f6] bg-[#0a0e18] shadow-[0_0_16px_-4px_rgba(76,215,246,0.3)]'
                        : 'border-[#262a35] bg-[#0a0e18] hover:border-[#4cd7f6]/50'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <span className="material-symbols-outlined text-[#d0bcff] text-[20px]">
                          devices
                        </span>
                        <span className="text-[14px] text-[#dfe2f1] font-semibold">
                          Sistema (Auto)
                        </span>
                      </div>
                      <span className="material-symbols-outlined text-[20px] text-[#bcc9cd]">
                        {settings.themeMode === 'system' ? 'check_circle' : 'radio_button_unchecked'}
                      </span>
                    </div>

                    {/* Mini Visual Preview Split */}
                    <div className="w-full h-20 rounded-lg border border-[#313540] overflow-hidden flex relative shadow-inner pointer-events-none">
                      <div className="w-1/2 h-full bg-[#0f131d] p-2 flex flex-col justify-between border-r border-[#313540]">
                        <div className="w-8 h-1.5 rounded bg-[#4cd7f6]" />
                        <div className="w-full h-5 rounded bg-[#1c1f2a] border border-[#313540] flex items-center px-1">
                          <div className="w-3/4 h-1 bg-[#4cd7f6]/60 rounded" />
                        </div>
                      </div>
                      <div className="w-1/2 h-full bg-[#f8fafc] p-2 flex flex-col justify-between">
                        <div className="w-8 h-1.5 rounded bg-[#0891b2] self-end" />
                        <div className="w-full h-5 rounded bg-white border border-[#cbd5e1] flex items-center px-1">
                          <div className="w-3/4 h-1 bg-[#0891b2] rounded" />
                        </div>
                      </div>
                      <div className="absolute inset-x-0 bottom-0 bg-[#262a35]/90 text-center text-[9px] font-mono py-0.5 text-[#dfe2f1]">
                        prefers-color-scheme
                      </div>
                    </div>

                    <span className="font-mono text-[11px] text-[#bcc9cd]">
                      Sincronizza automaticamente l&apos;aspetto visivo con il sistema operativo ospite.
                    </span>
                  </button>
                </div>
              </div>

              {/* 2-Column Section: Backend Execution Plane & Network Parameters */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                {/* Left Info Panel */}
                <div className="lg:col-span-4 flex flex-col gap-4">
                  <div className="bg-[#171b26] p-6 rounded-xl border border-[#262a35] shadow-md flex flex-col gap-3">
                    <div className="flex items-center gap-1.5 text-[#4cd7f6] font-mono text-[11px] uppercase font-semibold">
                      <span className="material-symbols-outlined text-[18px]">dns</span>
                      <span>Backend Execution Plane</span>
                    </div>
                    <h3 className="text-[17px] text-[#dfe2f1] font-semibold">
                      FastAPI Engine Asincrono
                    </h3>
                    <p className="text-[13px] text-[#bcc9cd] leading-relaxed">
                      Gestisce il server UVicorn, il pool dei thread di inferenza paralleli e i canali CORS autorizzati verso i client front-end e le estensioni VS Code.
                    </p>

                    {/* Live Waveform Pulse */}
                    <div className="mt-3 bg-[#0a0e18] p-4 rounded-lg border border-[#262a35] flex flex-col gap-2">
                      <div className="flex justify-between font-mono text-[11px] text-[#bcc9cd]">
                        <span>Thread Pool Concurrency</span>
                        <span className="text-[#4cd7f6] font-semibold">
                          {settings.workerConcurrency} Workers (Uvicorn)
                        </span>
                      </div>
                      <div className="w-full h-8 flex items-center">
                        <svg className="w-full h-6 text-[#4cd7f6]" fill="none" viewBox="0 0 240 24">
                          <path
                            d="M0 12 H40 L45 3 L55 21 L60 12 H95 L100 6 L108 19 L114 12 H160 L165 4 L175 22 L180 12 H240"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinejoin="round"
                            vectorEffect="non-scaling-stroke"
                          />
                        </svg>
                      </div>
                      <span className="font-mono text-[10px] text-[#bcc9cd]">
                        Load balance su loop libuv
                      </span>
                    </div>
                  </div>
                </div>

                {/* Right Inputs Panel */}
                <div className="lg:col-span-8 bg-[#171b26] p-6 rounded-xl border border-[#262a35] shadow-md flex flex-col gap-5">
                  <h3 className="text-[17px] text-[#dfe2f1] font-semibold">
                    Parametri Network &amp; UVicorn
                  </h3>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Host */}
                    <div className="flex flex-col gap-1.5">
                      <label className="font-mono text-[11px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                        Host Interface
                      </label>
                      <div className="relative flex items-center">
                        <span className="material-symbols-outlined absolute left-3 text-[#bcc9cd] text-[18px]">
                          terminal
                        </span>
                        <input
                          type="text"
                          value={settings.hostUrl}
                          onChange={(e) => onUpdateSettings({ hostUrl: e.target.value })}
                          className="w-full bg-[#0a0e18] text-[#dfe2f1] font-mono text-[12px] pl-10 pr-3 py-2.5 rounded-lg border border-[#262a35] focus:outline-none focus:ring-1 focus:ring-[#4cd7f6]"
                        />
                      </div>
                      <span className="text-[11px] text-[#bcc9cd]">
                        Indirizzo IPv4 o hostname di bind locale.
                      </span>
                    </div>

                    {/* Port */}
                    <div className="flex flex-col gap-1.5">
                      <label className="font-mono text-[11px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                        Porta del Server
                      </label>
                      <div className="relative flex items-center">
                        <span className="material-symbols-outlined absolute left-3 text-[#bcc9cd] text-[18px]">
                          router
                        </span>
                        <input
                          type="number"
                          value={settings.portNumber}
                          onChange={(e) => onUpdateSettings({ portNumber: Number(e.target.value) })}
                          className="w-full bg-[#0a0e18] text-[#dfe2f1] font-mono text-[12px] pl-10 pr-3 py-2.5 rounded-lg border border-[#262a35] focus:outline-none focus:ring-1 focus:ring-[#4cd7f6]"
                        />
                      </div>
                      <span className="text-[11px] text-[#bcc9cd]">
                        Default 8000 per socket HTTP/WebSocket standard.
                      </span>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Workers */}
                    <div className="flex flex-col gap-1.5">
                      <label className="font-mono text-[11px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                        Worker Concurrency
                      </label>
                      <select
                        value={settings.workerConcurrency}
                        onChange={(e) => onUpdateSettings({ workerConcurrency: Number(e.target.value) })}
                        className="w-full bg-[#0a0e18] text-[#dfe2f1] font-mono text-[12px] px-3 py-2.5 rounded-lg border border-[#262a35] focus:outline-none focus:ring-1 focus:ring-[#4cd7f6]"
                      >
                        <option value="2">2 Thread Worker (Consumo Minimo)</option>
                        <option value="4">4 Thread Worker (Bilanciato CPU)</option>
                        <option value="8">8 Thread Worker (Consigliato per I/O e GPU)</option>
                        <option value="16">16 Thread Worker (Cluster Enterprise)</option>
                      </select>
                      <span className="text-[11px] text-[#bcc9cd]">
                        Istanze UVicorn per ingest e query concorrenti.
                      </span>
                    </div>

                    {/* Log level */}
                    <div className="flex flex-col gap-1.5">
                      <label className="font-mono text-[11px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                        Livello Log Telemetria
                      </label>
                      <div className="flex items-center gap-1 bg-[#0a0e18] p-1 rounded-lg border border-[#262a35]">
                        {(['DEBUG', 'INFO', 'WARNING'] as const).map((lvl) => {
                          const isSel = settings.logLevel === lvl;
                          return (
                            <button
                              key={lvl}
                              type="button"
                              onClick={() => onUpdateSettings({ logLevel: lvl })}
                              className={`flex-1 py-1.5 rounded text-center font-mono text-[11px] transition-all cursor-pointer ${
                                isSel
                                  ? 'bg-[#4cd7f6]/20 text-[#4cd7f6] font-semibold border border-[#4cd7f6]/40'
                                  : 'text-[#bcc9cd] hover:text-[#dfe2f1]'
                              }`}
                            >
                              {lvl}
                            </button>
                          );
                        })}
                      </div>
                      <span className="text-[11px] text-[#bcc9cd]">
                        Controlla la granularità dei log su stdout.
                      </span>
                    </div>
                  </div>

                  {/* CORS */}
                  <div className="flex flex-col gap-1.5">
                    <label className="font-mono text-[11px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                      CORS Origins Consentiti (separati da virgola)
                    </label>
                    <textarea
                      value={settings.corsOrigins}
                      onChange={(e) => onUpdateSettings({ corsOrigins: e.target.value })}
                      rows={2}
                      className="w-full bg-[#0a0e18] text-[#dfe2f1] font-mono text-[12px] p-3 rounded-lg border border-[#262a35] focus:outline-none focus:ring-1 focus:ring-[#4cd7f6]"
                    />
                    <span className="text-[11px] text-[#bcc9cd]">
                      Origini autorizzate per chiamate cross-origin REST &amp; SSE.
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: LanceDB & Vettori */}
          {activeTab === 'lancedb' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-4 flex flex-col gap-4">
                <div className="bg-[#171b26] p-6 rounded-xl border border-[#262a35] shadow-md flex flex-col gap-3">
                  <div className="flex items-center gap-1.5 text-[#4cd7f6] font-mono text-[11px] uppercase font-semibold">
                    <span className="material-symbols-outlined text-[18px]">scatter_plot</span>
                    <span>Lance Format Storage</span>
                  </div>
                  <h3 className="text-[17px] text-[#dfe2f1] font-semibold">
                    Indice IVF-PQ &amp; Apache Arrow
                  </h3>
                  <p className="text-[13px] text-[#bcc9cd] leading-relaxed">
                    LanceDB sfrutta partizionamento vettoriale ad albero invertito con quantizzazione per operare sub-millisecond search su dischi NVMe.
                  </p>

                  <div className="mt-3 bg-[#0a0e18] p-4 rounded-lg border border-[#262a35] flex flex-col gap-2">
                    <div className="flex justify-between font-mono text-[11px] text-[#bcc9cd]">
                      <span>Index Partitions (IVF)</span>
                      <span className="text-[#d0bcff]">{settings.numCentroids} Centroids</span>
                    </div>
                    <div className="w-full h-12 flex items-center justify-around py-1">
                      {[32, 40, 28, 44, 24, 36, 48].map((h, i) => (
                        <div
                          key={i}
                          className="w-4 bg-[#4cd7f6]/20 rounded-t flex items-end justify-center"
                          style={{ height: `${h}px` }}
                        >
                          <div
                            className="w-full bg-[#4cd7f6] rounded-t"
                            style={{ height: `${Math.round(h * 0.7)}px` }}
                          />
                        </div>
                      ))}
                    </div>
                    <span className="font-mono text-[10px] text-[#bcc9cd] text-center">
                      Metric: Cosine Proximity (1 - cos(θ))
                    </span>
                  </div>
                </div>
              </div>

              <div className="lg:col-span-8 bg-[#171b26] p-6 rounded-xl border border-[#262a35] shadow-md flex flex-col gap-5">
                <h3 className="text-[17px] text-[#dfe2f1] font-semibold">
                  Archiviazione &amp; Struttura Tabellare
                </h3>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="flex flex-col gap-1.5">
                    <label className="font-mono text-[11px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                      Directory Persistenza Dati
                    </label>
                    <div className="relative flex items-center">
                      <span className="material-symbols-outlined absolute left-3 text-[#bcc9cd] text-[18px]">
                        folder_open
                      </span>
                      <input
                        type="text"
                        value={settings.storagePath}
                        onChange={(e) => onUpdateSettings({ storagePath: e.target.value })}
                        className="w-full bg-[#0a0e18] text-[#dfe2f1] font-mono text-[12px] pl-10 pr-3 py-2.5 rounded-lg border border-[#262a35] focus:outline-none focus:ring-1 focus:ring-[#4cd7f6]"
                      />
                    </div>
                    <span className="text-[11px] text-[#bcc9cd]">
                      Path relativo o assoluto al filesystem locale.
                    </span>
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <label className="font-mono text-[11px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                      Nome Tabella Vettoriale Primaria
                    </label>
                    <div className="relative flex items-center">
                      <span className="material-symbols-outlined absolute left-3 text-[#bcc9cd] text-[18px]">
                        table_rows
                      </span>
                      <input
                        type="text"
                        value={settings.tableName}
                        onChange={(e) => onUpdateSettings({ tableName: e.target.value })}
                        className="w-full bg-[#0a0e18] text-[#dfe2f1] font-mono text-[12px] pl-10 pr-3 py-2.5 rounded-lg border border-[#262a35] focus:outline-none focus:ring-1 focus:ring-[#4cd7f6]"
                      />
                    </div>
                    <span className="text-[11px] text-[#bcc9cd]">
                      Tabella Lance con indici semantici e full-text.
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="flex flex-col gap-1.5">
                    <label className="font-mono text-[11px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                      Algoritmo Indice
                    </label>
                    <select
                      value={settings.indexAlgorithm}
                      onChange={(e) =>
                        onUpdateSettings({
                          indexAlgorithm: e.target.value as 'IVF-PQ' | 'Flat' | 'HNSW',
                        })
                      }
                      className="w-full bg-[#0a0e18] text-[#dfe2f1] font-mono text-[12px] px-3 py-2.5 rounded-lg border border-[#262a35] focus:outline-none focus:ring-1 focus:ring-[#4cd7f6]"
                    >
                      <option value="IVF-PQ">IVF-PQ (Scalabile &amp; Veloce)</option>
                      <option value="Flat">Flat / Exact Scan (Max Recall)</option>
                      <option value="HNSW">HNSW (Bassa latenza RAM)</option>
                    </select>
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <label className="font-mono text-[11px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                      Numero Centroidi (IVF)
                    </label>
                    <input
                      type="number"
                      value={settings.numCentroids}
                      onChange={(e) => onUpdateSettings({ numCentroids: Number(e.target.value) })}
                      className="w-full bg-[#0a0e18] text-[#dfe2f1] font-mono text-[12px] px-3 py-2.5 rounded-lg border border-[#262a35] focus:outline-none focus:ring-1 focus:ring-[#4cd7f6]"
                    />
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <label className="font-mono text-[11px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                      Sotto-Vettori (PQ)
                    </label>
                    <input
                      type="number"
                      value={settings.subVectorsPQ}
                      onChange={(e) => onUpdateSettings({ subVectorsPQ: Number(e.target.value) })}
                      className="w-full bg-[#0a0e18] text-[#dfe2f1] font-mono text-[12px] px-3 py-2.5 rounded-lg border border-[#262a35] focus:outline-none focus:ring-1 focus:ring-[#4cd7f6]"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-center">
                  <div className="flex flex-col gap-1.5">
                    <label className="font-mono text-[11px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                      Metrica di Distanza Vettoriale
                    </label>
                    <select
                      value={settings.distanceMetric}
                      onChange={(e) =>
                        onUpdateSettings({
                          distanceMetric: e.target.value as 'Cosine' | 'L2' | 'Dot',
                        })
                      }
                      className="w-full bg-[#0a0e18] text-[#dfe2f1] font-mono text-[12px] px-3 py-2.5 rounded-lg border border-[#262a35] focus:outline-none focus:ring-1 focus:ring-[#4cd7f6]"
                    >
                      <option value="Cosine">Cosine (Raccomandato)</option>
                      <option value="L2">L2 Euclidean</option>
                      <option value="Dot">Dot Product</option>
                    </select>
                  </div>

                  <div className="flex items-center justify-between bg-[#0a0e18] p-4 rounded-lg border border-[#262a35] shadow-inner">
                    <div className="flex flex-col">
                      <span className="text-[13px] text-[#dfe2f1] font-semibold">
                        Compaction Automatica
                      </span>
                      <span className="font-mono text-[11px] text-[#bcc9cd]">
                        Esegui compaction ogni 1,000 upsert
                      </span>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={settings.autoCompaction}
                        onChange={(e) => onUpdateSettings({ autoCompaction: e.target.checked })}
                        className="sr-only peer"
                      />
                      <div className="w-11 h-6 bg-[#262a35] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white peer-checked:bg-[#4cd7f6] after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-[#003640] after:border-[#1c1f2a] after:border after:rounded-full after:h-5 after:w-5 after:transition-all" />
                    </label>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: Ingestion & Docling */}
          {activeTab === 'docling' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-4 flex flex-col gap-4">
                <div className="bg-[#171b26] p-6 rounded-xl border border-[#262a35] shadow-md flex flex-col gap-3">
                  <div className="flex items-center gap-1.5 text-[#4cd7f6] font-mono text-[11px] uppercase font-semibold">
                    <span className="material-symbols-outlined text-[18px]">find_in_page</span>
                    <span>Document Layout Parser</span>
                  </div>
                  <h3 className="text-[17px] text-[#dfe2f1] font-semibold">
                    Docling Structural AST
                  </h3>
                  <p className="text-[13px] text-[#bcc9cd] leading-relaxed">
                    Docling trasforma PDF, DOCX e presentazioni in un albero Markdown ricco, separando titoli, paragrafi, tabelle e grafici senza troncare blocchi logici.
                  </p>

                  <div className="mt-3 bg-[#0a0e18] p-4 rounded-lg border border-[#262a35] flex flex-col gap-2">
                    <div className="flex justify-between font-mono text-[11px] text-[#bcc9cd]">
                      <span>Chunk Boundary Preview</span>
                      <span className="text-[#4cd7f6] font-semibold">
                        {settings.chunkOverlap}% Overlap
                      </span>
                    </div>
                    <div className="flex items-center gap-1 w-full py-2">
                      <div className="h-6 flex-1 bg-[#4cd7f6]/20 rounded flex items-center justify-center font-mono text-[10px] text-[#4cd7f6]">
                        Chunk N-1
                      </div>
                      <div className="h-6 w-12 bg-[#d0bcff]/40 rounded flex items-center justify-center font-mono text-[10px] text-[#d0bcff]">
                        {settings.chunkOverlap}%
                      </div>
                      <div className="h-6 flex-1 bg-[#4cd7f6]/40 rounded flex items-center justify-center font-mono text-[10px] text-[#4cd7f6] font-semibold">
                        Chunk N
                      </div>
                    </div>
                    <span className="font-mono text-[10px] text-[#bcc9cd]">
                      Zero frammentazione di tabelle semantiche.
                    </span>
                  </div>
                </div>
              </div>

              <div className="lg:col-span-8 bg-[#171b26] p-6 rounded-xl border border-[#262a35] shadow-md flex flex-col gap-5">
                <h3 className="text-[17px] text-[#dfe2f1] font-semibold">
                  Strategia di Chunking &amp; Segmentazione
                </h3>

                {/* Chunk Size Slider & Numeric Sync */}
                <div className="flex flex-col gap-2 bg-[#0a0e18] p-4 rounded-lg border border-[#262a35] shadow-inner">
                  <div className="flex items-center justify-between">
                    <label className="font-mono text-[11px] text-[#dfe2f1] font-semibold uppercase tracking-wider">
                      Dimensione del Chunk (Tokens)
                    </label>
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        min="128"
                        max="2048"
                        step="64"
                        value={settings.chunkSize}
                        onChange={(e) => onUpdateSettings({ chunkSize: Number(e.target.value) })}
                        className="w-24 bg-[#1c1f2a] text-[#4cd7f6] font-mono font-bold text-[18px] px-2 py-1 rounded text-right focus:outline-none border border-[#262a35]"
                      />
                      <span className="font-mono text-[11px] text-[#bcc9cd]">tokens</span>
                    </div>
                  </div>
                  <input
                    type="range"
                    min="128"
                    max="2048"
                    step="64"
                    value={settings.chunkSize}
                    onChange={(e) => onUpdateSettings({ chunkSize: Number(e.target.value) })}
                    className="w-full accent-[#4cd7f6] cursor-pointer mt-1"
                  />
                  <div className="flex justify-between font-mono text-[10px] text-[#bcc9cd] mt-1">
                    <span>128 (Micro-frammenti)</span>
                    <span>512 (Ottimale RAG)</span>
                    <span>1024</span>
                    <span>2048 (Macro-blocchi)</span>
                  </div>
                </div>

                {/* Overlap Slider & Numeric Sync */}
                <div className="flex flex-col gap-2 bg-[#0a0e18] p-4 rounded-lg border border-[#262a35] shadow-inner">
                  <div className="flex items-center justify-between">
                    <label className="font-mono text-[11px] text-[#dfe2f1] font-semibold uppercase tracking-wider">
                      Chunk Overlap Percentuale (%)
                    </label>
                    <div className="flex items-center gap-2">
                      <input
                        type="number"
                        min="0"
                        max="40"
                        step="1"
                        value={settings.chunkOverlap}
                        onChange={(e) => onUpdateSettings({ chunkOverlap: Number(e.target.value) })}
                        className="w-20 bg-[#1c1f2a] text-[#d0bcff] font-mono font-bold text-[18px] px-2 py-1 rounded text-right focus:outline-none border border-[#262a35]"
                      />
                      <span className="font-mono text-[11px] text-[#bcc9cd]">%</span>
                    </div>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="40"
                    step="1"
                    value={settings.chunkOverlap}
                    onChange={(e) => onUpdateSettings({ chunkOverlap: Number(e.target.value) })}
                    className="w-full accent-[#d0bcff] cursor-pointer mt-1"
                  />
                  <div className="flex justify-between font-mono text-[10px] text-[#bcc9cd] mt-1">
                    <span>0% (Disgiunto)</span>
                    <span>15% (Bilanciato - 76t)</span>
                    <span>30%</span>
                    <span>40% (Alta continuità)</span>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="flex items-center justify-between bg-[#0a0e18] p-4 rounded-lg border border-[#262a35] shadow-inner">
                    <div className="flex flex-col pr-2">
                      <span className="text-[13px] text-[#dfe2f1] font-semibold">
                        Estrazione Tabelle &amp; Immagini
                      </span>
                      <span className="font-mono text-[11px] text-[#bcc9cd]">
                        OCR &amp; Layout Engine Docling
                      </span>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input
                        type="checkbox"
                        checked={settings.ocrTablesExtraction}
                        onChange={(e) =>
                          onUpdateSettings({ ocrTablesExtraction: e.target.checked })
                        }
                        className="sr-only peer"
                      />
                      <div className="w-11 h-6 bg-[#262a35] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white peer-checked:bg-[#4cd7f6] after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-[#003640] after:border-[#1c1f2a] after:border after:rounded-full after:h-5 after:w-5 after:transition-all" />
                    </label>
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <label className="font-mono text-[11px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                      Modalità Separazione
                    </label>
                    <select
                      value={settings.splitMode}
                      onChange={(e) =>
                        onUpdateSettings({
                          splitMode: e.target.value as 'ast' | 'fixed' | 'sentences',
                        })
                      }
                      className="w-full bg-[#0a0e18] text-[#dfe2f1] font-mono text-[12px] px-3 py-3 rounded-lg border border-[#262a35] focus:outline-none focus:ring-1 focus:ring-[#4cd7f6]"
                    >
                      <option value="ast">Semantica strutturale (Markdown AST)</option>
                      <option value="fixed">Fixed-Window con Tokenizer Spacy</option>
                      <option value="sentences">Sentence-boundary NLTK</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: Modelli & Endpoint */}
          {activeTab === 'models' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-4 flex flex-col gap-4">
                <div className="bg-[#171b26] p-6 rounded-xl border border-[#262a35] shadow-md flex flex-col gap-3">
                  <div className="flex items-center gap-1.5 text-[#4cd7f6] font-mono text-[11px] uppercase font-semibold">
                    <span className="material-symbols-outlined text-[18px]">smart_toy</span>
                    <span>Local Neural Inference</span>
                  </div>
                  <h3 className="text-[17px] text-[#dfe2f1] font-semibold">
                    Ollama Daemon &amp; Rerank
                  </h3>
                  <p className="text-[13px] text-[#bcc9cd] leading-relaxed">
                    Interfaccia diretta verso server Ollama locale e pesi HuggingFace scaricati su cache locale.
                  </p>

                  <div className="mt-3 bg-[#0a0e18] p-4 rounded-lg border border-[#262a35] flex flex-col gap-3">
                    <div className="flex justify-between font-mono text-[11px]">
                      <span className="text-[#bcc9cd]">Stato Modelli in VRAM</span>
                      <span className="text-[#4cd7f6] font-semibold">Caricati a caldo</span>
                    </div>

                    <div className="flex flex-col gap-1">
                      <div className="flex justify-between font-mono text-[11px] text-[#bcc9cd]">
                        <span>nomic-embed-text</span>
                        <span className="text-[#dfe2f1]">1.2 GB</span>
                      </div>
                      <div className="w-full h-2 bg-[#1c1f2a] rounded-full overflow-hidden">
                        <div className="w-1/4 h-full bg-[#4cd7f6] rounded-full" />
                      </div>
                    </div>

                    <div className="flex flex-col gap-1">
                      <div className="flex justify-between font-mono text-[11px] text-[#bcc9cd]">
                        <span>ms-marco-MiniLM (Cross-Enc)</span>
                        <span className="text-[#dfe2f1]">680 MB</span>
                      </div>
                      <div className="w-full h-2 bg-[#1c1f2a] rounded-full overflow-hidden">
                        <div className="w-1/6 h-full bg-[#d0bcff] rounded-full" />
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="lg:col-span-8 bg-[#171b26] p-6 rounded-xl border border-[#262a35] shadow-md flex flex-col gap-5">
                <h3 className="text-[17px] text-[#dfe2f1] font-semibold">
                  Endpoint &amp; Modelli di Dense Retrieval
                </h3>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="flex flex-col gap-1.5">
                    <label className="font-mono text-[11px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                      Ollama Base URL
                    </label>
                    <div className="relative flex items-center">
                      <span className="material-symbols-outlined absolute left-3 text-[#bcc9cd] text-[18px]">
                        terminal
                      </span>
                      <input
                        type="text"
                        value={settings.ollamaUrl}
                        onChange={(e) => onUpdateSettings({ ollamaUrl: e.target.value })}
                        className="w-full bg-[#0a0e18] text-[#dfe2f1] font-mono text-[12px] pl-10 pr-3 py-2.5 rounded-lg border border-[#262a35] focus:outline-none focus:ring-1 focus:ring-[#4cd7f6]"
                      />
                    </div>
                    <span className="text-[11px] text-[#bcc9cd]">
                      Endpoint del demone locale Ollama per embeddings.
                    </span>
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <label className="font-mono text-[11px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                      Embedding Model Attivo
                    </label>
                    <select
                      value={settings.embeddingModel}
                      onChange={(e) => onUpdateSettings({ embeddingModel: e.target.value })}
                      className="w-full bg-[#0a0e18] text-[#dfe2f1] font-mono text-[12px] px-3 py-2.5 rounded-lg border border-[#262a35] focus:outline-none focus:ring-1 focus:ring-[#4cd7f6]"
                    >
                      <option value="nomic-embed-text">nomic-embed-text (dim: 1024, context: 8k)</option>
                      <option value="mistral-embed:7b">mistral-embed:7b (dim: 4096)</option>
                      <option value="bge-m3">bge-m3:latest (dim: 1024, multilingue)</option>
                      <option value="all-minilm">all-minilm-l6-v2 (dim: 384)</option>
                    </select>
                    <span className="text-[11px] text-[#bcc9cd]">
                      Generatore del vettore denso di query e frammenti.
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="flex flex-col gap-1.5">
                    <label className="font-mono text-[11px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                      Cross-Encoder Reranker
                    </label>
                    <div className="relative flex items-center">
                      <span className="material-symbols-outlined absolute left-3 text-[#bcc9cd] text-[18px]">
                        model_training
                      </span>
                      <input
                        type="text"
                        value={settings.crossEncoderModel}
                        onChange={(e) => onUpdateSettings({ crossEncoderModel: e.target.value })}
                        className="w-full bg-[#0a0e18] text-[#dfe2f1] font-mono text-[12px] pl-10 pr-3 py-2.5 rounded-lg border border-[#262a35] focus:outline-none focus:ring-1 focus:ring-[#4cd7f6]"
                      />
                    </div>
                    <span className="text-[11px] text-[#bcc9cd]">
                      Eseguito localmente via ONNX / PyTorch.
                    </span>
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <label className="font-mono text-[11px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                      Keep-Alive VRAM Modelli (secondi)
                    </label>
                    <div className="relative flex items-center">
                      <span className="material-symbols-outlined absolute left-3 text-[#bcc9cd] text-[18px]">
                        timer
                      </span>
                      <input
                        type="number"
                        value={settings.keepAliveSeconds}
                        onChange={(e) =>
                          onUpdateSettings({ keepAliveSeconds: Number(e.target.value) })
                        }
                        className="w-full bg-[#0a0e18] text-[#dfe2f1] font-mono text-[12px] pl-10 pr-3 py-2.5 rounded-lg border border-[#262a35] focus:outline-none focus:ring-1 focus:ring-[#4cd7f6]"
                      />
                    </div>
                    <span className="text-[11px] text-[#bcc9cd]">
                      Permanenza del modello caricato in memoria GPU.
                    </span>
                  </div>
                </div>

                {/* Top K and Top N Inputs */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 bg-[#0a0e18] p-4 rounded-lg border border-[#262a35] shadow-inner">
                  <div className="flex flex-col gap-1.5">
                    <div className="flex justify-between items-center">
                      <label className="font-mono text-[11px] text-[#dfe2f1] font-semibold uppercase tracking-wider">
                        Top-K Candidati Preliminari
                      </label>
                      <span className="font-mono text-[12px] text-[#4cd7f6] font-bold">
                        {settings.topKCandidates} items
                      </span>
                    </div>
                    <input
                      type="range"
                      min="5"
                      max="50"
                      step="5"
                      value={settings.topKCandidates}
                      onChange={(e) =>
                        onUpdateSettings({ topKCandidates: Number(e.target.value) })
                      }
                      className="accent-[#4cd7f6] cursor-pointer mt-1"
                    />
                    <span className="text-[11px] text-[#bcc9cd]">
                      Risultati aggregati da LanceDB prima del rerank.
                    </span>
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <div className="flex justify-between items-center">
                      <label className="font-mono text-[11px] text-[#bcc9cd] font-semibold uppercase tracking-wider">
                        Top-N Rerank Restituiti
                      </label>
                      <span className="font-mono text-[12px] text-[#c0c1ff] font-bold">
                        {settings.topNRerank} items
                      </span>
                    </div>
                    <input
                      type="range"
                      min="1"
                      max="15"
                      step="1"
                      value={settings.topNRerank}
                      onChange={(e) => onUpdateSettings({ topNRerank: Number(e.target.value) })}
                      className="accent-[#c0c1ff] cursor-pointer mt-1"
                    />
                    <span className="text-[11px] text-[#bcc9cd]">
                      Chunk finali inviati al prompt del Generatore LLM.
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 5: API & Sicurezza */}
          {activeTab === 'security' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              <div className="lg:col-span-4 flex flex-col gap-4">
                <div className="bg-[#171b26] p-6 rounded-xl border border-[#262a35] shadow-md flex flex-col gap-3">
                  <div className="flex items-center gap-1.5 text-[#4cd7f6] font-mono text-[11px] uppercase font-semibold">
                    <span className="material-symbols-outlined text-[18px]">security</span>
                    <span>Protezione Token &amp; Auth</span>
                  </div>
                  <h3 className="text-[17px] text-[#dfe2f1] font-semibold">
                    Controllo Accessi &amp; Rate Limit
                  </h3>
                  <p className="text-[13px] text-[#bcc9cd] leading-relaxed">
                    Configura le chiavi bearer per le chiamate REST headless e le soglie anti-DDoS su ingestione batch non autorizzata.
                  </p>

                  <div className="mt-3 bg-[#0a0e18] p-4 rounded-lg border border-[#262a35] flex flex-col gap-2">
                    <div className="flex justify-between font-mono text-[11px] text-[#bcc9cd]">
                      <span>Stato API Key</span>
                      <span className="text-[#4cd7f6]">Attiva (SHA-256)</span>
                    </div>
                    <div className="font-mono text-[11px] text-[#bcc9cd] truncate">
                      nx_live_948f21e0...c81a
                    </div>
                  </div>
                </div>
              </div>

              <div className="lg:col-span-8 bg-[#171b26] p-6 rounded-xl border border-[#262a35] shadow-md flex flex-col gap-5">
                <h3 className="text-[17px] text-[#dfe2f1] font-semibold">
                  Credenziali di Servizio &amp; Soglie
                </h3>

                <div className="flex flex-col gap-1.5">
                  <label className="font-mono text-[11px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                    Master API Secret Token
                  </label>
                  <div className="relative flex items-center">
                    <span className="material-symbols-outlined absolute left-3 text-[#bcc9cd] text-[18px]">
                      key
                    </span>
                    <input
                      type={showSecret ? 'text' : 'password'}
                      value={settings.apiToken}
                      onChange={(e) => onUpdateSettings({ apiToken: e.target.value })}
                      className="w-full bg-[#0a0e18] text-[#dfe2f1] font-mono text-[12px] pl-10 pr-20 py-2.5 rounded-lg border border-[#262a35] focus:outline-none focus:ring-1 focus:ring-[#4cd7f6]"
                    />
                    <button
                      type="button"
                      onClick={() => setShowSecret(!showSecret)}
                      className="absolute right-3 text-[#bcc9cd] hover:text-[#dfe2f1] text-[11px] font-mono"
                    >
                      {showSecret ? 'Nascondi' : 'Mostra'}
                    </button>
                  </div>
                  <span className="text-[11px] text-[#bcc9cd]">
                    Passata nell&apos;header Authorization come Bearer token per chiamate server-to-server.
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="flex flex-col gap-1.5">
                    <label className="font-mono text-[11px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                      Rate Limit Massimo (req/min)
                    </label>
                    <input
                      type="number"
                      value={settings.rateLimitMax}
                      onChange={(e) => onUpdateSettings({ rateLimitMax: Number(e.target.value) })}
                      className="w-full bg-[#0a0e18] text-[#dfe2f1] font-mono text-[12px] px-3 py-2.5 rounded-lg border border-[#262a35] focus:outline-none focus:ring-1 focus:ring-[#4cd7f6]"
                    />
                    <span className="text-[11px] text-[#bcc9cd]">
                      Limite per singolo indirizzo IP client.
                    </span>
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <label className="font-mono text-[11px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                      Dimensione Massima Payload Ingest
                    </label>
                    <select
                      value={settings.maxPayloadMB}
                      onChange={(e) => onUpdateSettings({ maxPayloadMB: Number(e.target.value) })}
                      className="w-full bg-[#0a0e18] text-[#dfe2f1] font-mono text-[12px] px-3 py-2.5 rounded-lg border border-[#262a35] focus:outline-none focus:ring-1 focus:ring-[#4cd7f6]"
                    >
                      <option value="25">25 MB (Documenti standard)</option>
                      <option value="50">50 MB (Raccomandato per PDF Docling)</option>
                      <option value="150">150 MB (Grandi corpus)</option>
                    </select>
                    <span className="text-[11px] text-[#bcc9cd]">
                      Soglia multipart upload file prima di rifiutare 413.
                    </span>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Sticky Floating Action Bar */}
        <div className="sticky bottom-6 z-30 bg-[#0a0e18]/90 backdrop-blur-md p-4 rounded-xl border border-[#262a35] shadow-2xl flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-2.5 text-[#bcc9cd] font-mono text-[11px]">
            <span className="w-2 h-2 rounded-full bg-[#4cd7f6] animate-pulse" />
            <span>Tutte le modifiche verranno applicate nel file di configurazione locale senza downtime.</span>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onReset}
              className="px-4 py-2 bg-[#1c1f2a] hover:bg-[#262a35] text-[#dfe2f1] font-mono text-[12px] rounded-lg transition-colors border border-[#262a35] cursor-pointer"
            >
              Ripristina Default
            </button>
            <button
              type="button"
              onClick={onSave}
              className="px-5 py-2 bg-[#4cd7f6] hover:bg-[#06b6d4] text-[#003640] font-semibold font-mono text-[12px] rounded-lg transition-all shadow-[0_0_20px_-4px_rgba(76,215,246,0.5)] flex items-center gap-2 cursor-pointer"
            >
              <span className="material-symbols-outlined text-[18px]">save</span>
              <span>Salva Modifiche</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
