import { apiFetch, apiJson, apiUrl, getApiToken, setApiToken } from './api';
/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useEffect } from 'react';
import { NavPage, ThemeMode, AppSettings, ChunkItem, KnowledgeDocument, TelemetryLog, EvalMetric } from './types';
import { initialSettings } from './data/defaultSettings';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { SettingsView } from './components/SettingsView';
import { QueryWorkbenchView } from './components/QueryWorkbenchView';
import { KnowledgeNodesView } from './components/KnowledgeNodesView';
import { VectorExplorerView } from './components/VectorExplorerView';
import { PipelineTelemetryView } from './components/PipelineTelemetryView';
import { EvaluationsView } from './components/EvaluationsView';
import { ChunkModal } from './components/ChunkModal';
import { IngestModal } from './components/IngestModal';
import { DatabaseManagerModal } from './components/DatabaseManagerModal';

export default function App() {
  const [isDbModalOpen, setIsDbModalOpen] = useState(false);
  const [activePage, setActivePage] = useState<NavPage>('settings');
  const [settings, setSettings] = useState<AppSettings>(initialSettings);
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [chunks, setChunks] = useState<ChunkItem[]>([]);
  const [logs, setLogs] = useState<TelemetryLog[]>([]);
  const [evalMetrics, setEvalMetrics] = useState<EvalMetric[]>([]);
  const [searchFilter, setSearchFilter] = useState('');
  const [chunksCount, setChunksCount] = useState<number | null>(null);
  const [storageBytes, setStorageBytes] = useState<number | null>(null);
  const [activeDatabaseName, setActiveDatabaseName] = useState<string | null>(null);
  const [avgLatencyMs, setAvgLatencyMs] = useState<number | null>(null);

  const reloadData = () => {
    apiFetch(`/api/settings`)
      .then((res) => res.ok ? res.json() : null)
      .then((data) => {
        if (data) setSettings((prev) => ({ ...prev, ...data }));
      })
      .catch(() => {});

    apiFetch(`/api/documents`)
      .then((res) => res.ok ? res.json() : null)
      .then((data) => {
        if (Array.isArray(data)) setDocuments(data);
      })
      .catch(() => {});

    apiFetch(`/api/chunks?page=1&pageSize=20`)
      .then((res) => res.ok ? res.json() : null)
      .then((data) => {
        if (data && Array.isArray(data.items)) {
          setChunks(data.items);
          if (data.items.length > 0) setSelectedChunk(data.items[0]);
        }
      })
      .catch(() => {});

    apiFetch(`/api/telemetry`)
      .then((res) => res.ok ? res.json() : null)
      .then((data) => {
        if (Array.isArray(data)) {
          setLogs(data);
          const durations = data
            .map((entry) => Number(entry?.durationMs))
            .filter((value) => Number.isFinite(value) && value >= 0);
          setAvgLatencyMs(durations.length ? durations.reduce((a, b) => a + b, 0) / durations.length : null);
        }
      })
      .catch(() => {});

    apiFetch(`/api/eval`)
      .then((res) => res.ok ? res.json() : null)
      .then((data) => {
        if (Array.isArray(data)) setEvalMetrics(data);
      })
      .catch(() => {});

    setChunksCount(null);
    setStorageBytes(null);
    setActiveDatabaseName(null);
    apiFetch(`/api/stats`)
      .then((res) => res.ok ? res.json() : null)
      .then((data) => {
        if (data) {
          setChunksCount(typeof data.chunks === 'number' && Number.isFinite(data.chunks) ? data.chunks : null);
          setStorageBytes(typeof data.storageBytes === 'number' && Number.isFinite(data.storageBytes) ? data.storageBytes : null);
          setActiveDatabaseName(data.activeDatabase?.name ?? null);
        }
      })
      .catch(() => {});
  };

  useEffect(() => {
    reloadData();
  }, []);

  // Modals state
  const [selectedChunk, setSelectedChunk] = useState<ChunkItem | null>(null);
  const [isChunkModalOpen, setIsChunkModalOpen] = useState(false);
  const [isIngestModalOpen, setIsIngestModalOpen] = useState(false);

  // Toast notification state
  const [toast, setToast] = useState<{ message: string; isError?: boolean; visible: boolean }>({
    message: 'Impostazioni salvate con successo.',
    isError: false,
    visible: false,
  });

  // Automatically hide toast after timeout
  useEffect(() => {
    if (toast.visible) {
      const timer = setTimeout(() => {
        setToast((prev) => ({ ...prev, visible: false }));
      }, 4000);
      return () => clearTimeout(timer);
    }
  }, [toast.visible]);

  const showToast = (message: string, isError = false) => {
    setToast({ message, isError, visible: true });
  };

  // Theme application logic
  const applyThemeMode = (mode: ThemeMode) => {
    const html = document.documentElement;
    let isLight = false;

    if (mode === 'light') {
      isLight = true;
    } else if (mode === 'dark') {
      isLight = false;
    } else if (mode === 'system') {
      isLight = !window.matchMedia('(prefers-color-scheme: dark)').matches;
    }

    if (isLight) {
      html.classList.remove('dark');
      html.classList.add('theme-light');
    } else {
      html.classList.add('dark');
      html.classList.remove('theme-light');
    }
  };

  useEffect(() => {
    applyThemeMode(settings.themeMode);

    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const listener = (e: MediaQueryListEvent) => {
      if (settings.themeMode === 'system') {
        const html = document.documentElement;
        if (e.matches) {
          html.classList.add('dark');
          html.classList.remove('theme-light');
        } else {
          html.classList.remove('dark');
          html.classList.add('theme-light');
        }
      }
    };
    media.addEventListener('change', listener);
    return () => media.removeEventListener('change', listener);
  }, [settings.themeMode]);

  const handleSelectTheme = (mode: ThemeMode) => {
    setSettings((prev) => ({ ...prev, themeMode: mode }));
    applyThemeMode(mode);
    showToast(
      mode === 'light'
        ? 'Tema chiaro (Clean Slate) attivato'
        : mode === 'dark'
        ? 'Tema scuro (Obsidian) attivato'
        : 'Tema sincronizzato con il sistema operativo'
    );
  };

  const handleToggleThemeQuick = () => {
    const nextMode = settings.themeMode === 'light' ? 'dark' : 'light';
    handleSelectTheme(nextMode);
  };

  const handleUpdateSettings = (newPartial: Partial<AppSettings>) => {
    setSettings((prev) => ({ ...prev, ...newPartial }));
  };

  const handleSaveSettings = () => {
    apiFetch(`/api/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...settings, apiToken: settings.apiToken || getApiToken() }),
    })
      .then((res) => {
        if (res.ok) {
          setApiToken(settings.apiToken || getApiToken());
          showToast('Impostazioni salvate con successo.');
        } else {
          showToast('Errore durante il salvataggio delle impostazioni.', true);
        }
      })
      .catch(() => showToast('Impossibile contattare il backend.', true));
  };

  const handleResetSettings = async () => {
    try {
      const defaultsRes = await apiFetch(`/api/settings/defaults`);
      if (!defaultsRes.ok) throw new Error(`HTTP ${defaultsRes.status}`);
      const defaults = await defaultsRes.json();
      const saveRes = await apiFetch(`/api/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(defaults),
      });
      if (!saveRes.ok) throw new Error(`HTTP ${saveRes.status}`);
      const saved = await saveRes.json();
      setSettings((prev) => ({ ...prev, ...saved, apiToken: '' }));
      applyThemeMode(saved.themeMode ?? initialSettings.themeMode);
      showToast('Impostazioni ripristinate e salvate.');
    } catch (error) {
      showToast(`Impossibile ripristinare le impostazioni: ${error instanceof Error ? error.message : 'errore sconosciuto'}`, true);
    }
  };

  const handleTestConnections = async () => {
    try {
      const res = await apiFetch(`/api/health`);
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`);
      const status = (value: unknown) => value === true ? 'OK' : 'KO';
      showToast(`FastAPI ${status(data.fastapi)} • LanceDB ${status(data.lancedb)} • Ollama ${status(data.ollama)}`);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Errore sconosciuto';
      showToast(`Verifica connessioni fallita: ${message}`, true);
    }
  };

  const handleRestartWorker = () => {
    showToast('Configurazione e risorse RAG ricaricate nel processo FastAPI.');
  };

  const handleInspectChunk = (chunk: ChunkItem) => {
    setSelectedChunk(chunk);
    setIsChunkModalOpen(true);
  };

  const handleIngestSuccess = (_fileName: string, _chunksCreated: number) => {
    // Do not synthesize documents/logs locally. Refresh from the backend,
    // which is the authoritative source for the active database state.
    reloadData();
  };

  const handleClearLogs = () => {
    setLogs([]);
    showToast('Registro log svuotato');
  };

  return (
    <div className="min-h-screen bg-[#0f131d] text-[#dfe2f1] flex flex-col font-sans transition-colors duration-200">
      {/* Fixed Left Sidebar */}
      <Sidebar
        activePage={activePage}
        onNavigate={(page) => setActivePage(page)}
        chunksCount={chunksCount}
        activeModel={settings.embeddingModel}
        latencyMs={avgLatencyMs}
      />

      {/* Main App Canvas */}
      <div className="pl-64 flex flex-col min-h-screen">
        {/* Fixed Top Header */}
        <Header
          themeMode={settings.themeMode}
          onToggleTheme={handleToggleThemeQuick}
          onOpenIngest={() => setIsIngestModalOpen(true)}
          onOpenTerminal={() => setActivePage('pipeline-telemetry')}
          onOpenDatabaseManager={() => setIsDbModalOpen(true)}
          searchFilter={searchFilter}
          onSearchChange={setSearchFilter}
        />

        {/* Dynamic Main Viewport */}
        <main className="w-full pt-16 min-h-[calc(100vh-4rem)]">
          {activePage === 'settings' && (
            <SettingsView
              settings={settings}
              onUpdateSettings={handleUpdateSettings}
              onSelectTheme={handleSelectTheme}
              onTestConnections={handleTestConnections}
              onRestartWorker={handleRestartWorker}
              onSave={handleSaveSettings}
              onReset={handleResetSettings}
            />
          )}

          {activePage === 'query-workbench' && (
            <QueryWorkbenchView
              chunks={chunks}
              onInspectChunk={handleInspectChunk}
              onShowToast={showToast}
              globalSearch={searchFilter}
              settings={settings}
            />
          )}

          {activePage === 'knowledge-nodes' && (
            <KnowledgeNodesView
              documents={documents}
              onShowToast={showToast}
              onOpenIngest={() => setIsIngestModalOpen(true)}
              globalSearch={searchFilter}
              chunksCount={chunksCount}
              activeDatabaseName={activeDatabaseName}
              storageBytes={storageBytes}
            />
          )}

          {activePage === 'vector-explorer' && (
            <VectorExplorerView
              chunks={chunks}
              onInspectChunk={handleInspectChunk}
              onShowToast={showToast}
              globalSearch={searchFilter}
            />
          )}

          {activePage === 'pipeline-telemetry' && (
            <PipelineTelemetryView
              logs={logs}
              onClearLogs={handleClearLogs}
              onLogsUpdate={setLogs}
              onShowToast={showToast}
              globalSearch={searchFilter}
            />
          )}

          {activePage === 'evaluations' && (
            <EvaluationsView metrics={evalMetrics} onShowToast={showToast} />
          )}
        </main>
      </div>

      {/* Toast Notification Container (Matching screenshot top right) */}
      <div
        className={`fixed top-4 right-6 z-50 transform transition-all duration-300 pointer-events-none ${
          toast.visible ? 'translate-y-0 opacity-100' : '-translate-y-12 opacity-0'
        }`}
      >
        <div className="bg-[#171b26] text-[#dfe2f1] px-4 py-3 rounded-lg shadow-2xl flex items-center gap-3 border border-[#262a35] max-w-md">
          <span
            className={`material-symbols-outlined text-[20px] ${
              toast.isError ? 'text-[#ffb4ab]' : 'text-[#4cd7f6]'
            }`}
          >
            {toast.isError ? 'error' : 'check_circle'}
          </span>
          <span className="text-[13px] font-sans font-medium">{toast.message}</span>
        </div>
      </div>

      {/* Chunk Modal */}
      <ChunkModal
        chunk={selectedChunk}
        isOpen={isChunkModalOpen}
        onClose={() => setIsChunkModalOpen(false)}
        onShowToast={showToast}
      />

      {/* Ingest Modal */}
      <IngestModal
        isOpen={isIngestModalOpen}
        onClose={() => setIsIngestModalOpen(false)}
        onIngestSuccess={handleIngestSuccess}
        onShowToast={showToast}
      />

      {/* Database Manager Modal */}
      <DatabaseManagerModal
        isOpen={isDbModalOpen}
        onClose={() => setIsDbModalOpen(false)}
        onShowToast={showToast}
        onDatabaseChanged={reloadData}
      />
    </div>
  );
}
