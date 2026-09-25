import { apiFetch, apiJson, apiUrl, getApiToken, setApiToken } from '../api';
import React, { useEffect, useState } from 'react';
import { TelemetryLog } from '../types';

interface PipelineTelemetryViewProps {
  logs: TelemetryLog[];
  onClearLogs: () => void;
  onLogsUpdate: (logs: TelemetryLog[]) => void;
  onShowToast: (msg: string, isError?: boolean) => void;
  globalSearch?: string;
}

export const PipelineTelemetryView: React.FC<PipelineTelemetryViewProps> = ({
  logs,
  onClearLogs,
  onLogsUpdate,
  onShowToast,
  globalSearch = '',
}) => {
  const [levelFilter, setLevelFilter] = useState<string>('all');
  const [isPaused, setIsPaused] = useState(false);
  const [streamStatus, setStreamStatus] = useState<'connecting' | 'connected' | 'paused' | 'error'>('connecting');
  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

  useEffect(() => {
    if (isPaused) {
      setStreamStatus('paused');
      return;
    }

    const token = getApiToken();
    const streamUrl = `${API_BASE_URL}/api/telemetry/stream${token ? `?token=${encodeURIComponent(token)}` : ''}`;
    const source = new EventSource(streamUrl);
    setStreamStatus('connecting');

    const handleTelemetry = (event: MessageEvent<string>) => {
      try {
        const nextLogs = JSON.parse(event.data);
        if (Array.isArray(nextLogs)) {
          onLogsUpdate(nextLogs);
          setStreamStatus('connected');
        }
      } catch {
        setStreamStatus('error');
      }
    };

    source.addEventListener('telemetry', handleTelemetry as EventListener);
    source.onopen = () => setStreamStatus('connected');
    source.onerror = () => {
      setStreamStatus('error');
      source.close();
    };

    return () => {
      source.close();
    };
  }, [API_BASE_URL, isPaused, onLogsUpdate]);

  const globalTerm = globalSearch.trim().toLowerCase();
  const filteredLogs = logs.filter((log) => {
    const matchesLevel = levelFilter === 'all' || log.level.toLowerCase() === levelFilter.toLowerCase();
    const matchesGlobal = !globalTerm || [log.timestamp, log.level, log.component, log.message]
      .some((value) => String(value ?? '').toLowerCase().includes(globalTerm));
    return matchesLevel && matchesGlobal;
  });

  const getLevelBadge = (level: TelemetryLog['level']) => {
    switch (level) {
      case 'DEBUG':
        return 'text-[#bcc9cd] bg-[#1c1f2a] border-[#262a35]';
      case 'INFO':
        return 'text-[#4cd7f6] bg-[#06b6d4]/15 border-[#06b6d4]/30';
      case 'WARNING':
        return 'text-[#d0bcff] bg-[#3131c0]/20 border-[#3131c0]/40';
      case 'ERROR':
        return 'text-[#ffb4ab] bg-[#93000a]/20 border-[#93000a]/40';
    }
  };

  const durations = filteredLogs.map((l) => l.durationMs).filter((d): d is number => d !== undefined);
  const avgDuration = durations.length > 0 ? (durations.reduce((a, b) => a + b, 0) / durations.length).toFixed(1) : '0.0';
  const p95Duration = durations.length > 0 ? (durations.sort((a, b) => a - b)[Math.floor(durations.length * 0.95)] || durations[durations.length - 1]).toFixed(1) : '0.0';

  const handleClear = () => {
    apiFetch(`/api/telemetry`, { method: 'DELETE' })
      .then((res) => {
        if (!res.ok) throw new Error('Errore svuotamento buffer');
        return res.json();
      })
      .then(() => {
        onClearLogs();
        onShowToast('Buffer telemetria backend svuotato con successo.');
      })
      .catch((err) => {
        onShowToast(`Impossibile svuotare il buffer backend: ${err instanceof Error ? err.message : 'errore sconosciuto'}`, true);
      });
  };

  return (
    <div className="p-6 flex flex-col gap-6 max-w-[1600px] mx-auto w-full relative z-10">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-[#171b26] p-6 rounded-xl border border-[#262a35] shadow-lg">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-[#262a35] flex items-center justify-center text-[#4cd7f6] shadow-[0_0_24px_rgba(76,215,246,0.25)] border border-[#3d494c]/50">
            <span className="material-symbols-outlined text-[28px]">monitoring</span>
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-1.5 font-mono text-[11px] text-[#4cd7f6] uppercase tracking-wider">
              <span>Telemetry &amp; Engine Logs</span>
              <span>•</span>
              <span className="text-[#bcc9cd]">TELEMETRY / SSE</span>
            </div>
            <h1 className="text-[24px] sm:text-[28px] text-[#dfe2f1] tracking-tight font-semibold">
              Pipeline Telemetry &amp; Log Console
            </h1>
            <p className="text-[13px] text-[#bcc9cd]">
              Flusso SSE in tempo reale delle metriche diagnostiche RAG.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              const nextPaused = !isPaused;
              setIsPaused(nextPaused);
              onShowToast(nextPaused ? 'Streaming log in pausa' : 'Streaming log riattivato');
            }}
            className="flex items-center gap-1.5 px-3.5 py-2 bg-[#262a35] hover:bg-[#353944] text-[#dfe2f1] font-mono text-[12px] rounded-lg border border-[#3d494c]/40 transition-colors cursor-pointer"
          >
            <span className="material-symbols-outlined text-[16px] text-[#4cd7f6]">
              {isPaused ? 'play_arrow' : 'pause'}
            </span>
            <span>{isPaused ? 'Riprendi' : 'Pausa Flusso'}</span>
          </button>
          <button
            onClick={handleClear}
            className="flex items-center gap-1.5 px-3.5 py-2 bg-[#262a35] hover:bg-[#353944] text-[#bcc9cd] hover:text-[#dfe2f1] font-mono text-[12px] rounded-lg border border-[#3d494c]/40 transition-colors cursor-pointer"
          >
            <span className="material-symbols-outlined text-[16px]">delete_sweep</span>
            <span>Svuota Buffer Logs</span>
          </button>
        </div>
      </div>

      {/* Latency Quantile Meters */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-[#171b26] p-4 rounded-xl border border-[#262a35]">
          <span className="font-mono text-[10px] text-[#bcc9cd] uppercase tracking-wider">
            Latenza Media
          </span>
          <div className="text-[22px] font-semibold text-[#4cd7f6] mt-1 font-mono">{avgDuration} ms</div>
          <span className="font-mono text-[11px] text-[#bcc9cd]">Dati reali tracciatore</span>
        </div>

        <div className="bg-[#171b26] p-4 rounded-xl border border-[#262a35]">
          <span className="font-mono text-[10px] text-[#bcc9cd] uppercase tracking-wider">
            Latenza P95
          </span>
          <div className="text-[22px] font-semibold text-[#dfe2f1] mt-1 font-mono">{p95Duration} ms</div>
          <span className="font-mono text-[11px] text-[#bcc9cd]">Con Cross-Encoder Reranker</span>
        </div>

        <div className="bg-[#171b26] p-4 rounded-xl border border-[#262a35]">
          <span className="font-mono text-[10px] text-[#bcc9cd] uppercase tracking-wider">
            Log Tracciati
          </span>
          <div className="text-[22px] font-semibold text-[#d0bcff] mt-1 font-mono">{filteredLogs.length}</div>
          <span className="font-mono text-[11px] text-[#bcc9cd]">Componenti FastAPI / Ollama / LanceDB</span>
        </div>

        <div className="bg-[#171b26] p-4 rounded-xl border border-[#262a35]">
          <span className="font-mono text-[10px] text-[#bcc9cd] uppercase tracking-wider">
            Stato Backend
          </span>
          <div className={`text-[22px] font-semibold mt-1 font-mono ${
            streamStatus === 'connected' ? 'text-[#10b981]' : streamStatus === 'paused' ? 'text-[#f59e0b]' : 'text-[#ffb4ab]'
          }`}>
            {streamStatus === 'connected' ? 'SSE ONLINE' : streamStatus === 'paused' ? 'SSE PAUSED' : streamStatus === 'connecting' ? 'SSE CONNECTING' : 'SSE ERROR'}
          </div>
          <span className="font-mono text-[11px] text-[#bcc9cd]">Stream telemetria backend</span>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-1.5">
        <span className="font-mono text-[11px] text-[#bcc9cd] mr-2">Filtra Gravità:</span>
        {['all', 'debug', 'info', 'warning', 'error'].map((lvl) => (
          <button
            key={lvl}
            onClick={() => setLevelFilter(lvl)}
            className={`px-3 py-1 rounded-lg font-mono text-[11px] uppercase transition-all cursor-pointer ${
              levelFilter === lvl
                ? 'bg-[#4cd7f6]/20 text-[#4cd7f6] font-semibold border border-[#4cd7f6]/40'
                : 'text-[#bcc9cd] hover:text-[#dfe2f1] bg-[#171b26] border border-[#262a35]'
            }`}
          >
            {lvl}
          </button>
        ))}
      </div>

      {/* Log Console Terminal */}
      <div className="bg-[#0a0e18] rounded-xl border border-[#262a35] p-4 font-mono text-[12px] flex flex-col gap-2 shadow-2xl max-h-[550px] overflow-y-auto">
        <div className="flex items-center justify-between pb-2 border-b border-[#262a35] text-[#bcc9cd] text-[11px]">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-[#ffb4ab]/80" />
            <span className="w-2.5 h-2.5 rounded-full bg-[#f59e0b]/80" />
            <span className="w-2.5 h-2.5 rounded-full bg-[#10b981]/80" />
            <span className="ml-2 font-mono">nexus-telemetry-stdout.log</span>
          </div>
          <span>Buffer: {filteredLogs.length} righe</span>
        </div>

        <div className="flex flex-col gap-1.5 divide-y divide-[#262a35]/40 pt-1">
          {filteredLogs.map((log) => (
            <div
              key={log.id}
              className="pt-1.5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 hover:bg-[#1c1f2a]/40 px-2 py-1 rounded transition-colors"
            >
              <div className="flex items-start sm:items-center gap-2 min-w-0">
                <span className="text-[#869397] shrink-0">{log.timestamp}</span>
                <span
                  className={`px-1.5 py-0.5 rounded text-[10px] font-bold border shrink-0 ${getLevelBadge(
                    log.level
                  )}`}
                >
                  {log.level}
                </span>
                <span className="text-[#d0bcff] shrink-0">[{log.component}]</span>
                <span className="text-[#dfe2f1] break-all">{log.message}</span>
              </div>

              {log.durationMs !== undefined && (
                <span className="text-[#4cd7f6] shrink-0 font-semibold text-[11px]">
                  {log.durationMs}ms
                </span>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
