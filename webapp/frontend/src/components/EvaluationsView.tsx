import { apiFetch, apiJson, apiUrl, getApiToken, setApiToken } from '../api';
import React, { useEffect, useState } from 'react';
import { EvalMetric } from '../types';

interface EvaluationsViewProps {
  metrics: EvalMetric[];
  onShowToast: (msg: string, isError?: boolean) => void;
}

export const EvaluationsView: React.FC<EvaluationsViewProps> = ({
  metrics,
  onShowToast,
}) => {
  const [isRunningEval, setIsRunningEval] = useState(false);
  const [liveMetrics, setLiveMetrics] = useState<EvalMetric[]>(metrics);
  const [testCases, setTestCases] = useState<any[]>([]);

  useEffect(() => {
    setLiveMetrics(metrics);
  }, [metrics]);

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

  const handleRunSuite = async () => {
    setIsRunningEval(true);
    setTestCases([]);
    try {
      const data = await apiJson<{ jobId: string }>('/api/eval/run', { method: 'POST' });
      const jobId = data.jobId;
      const startedAt = Date.now();
      let pollErrors = 0;

      const poll = async (): Promise<void> => {
        if (Date.now() - startedAt > 30 * 60 * 1000) {
          setIsRunningEval(false);
          onShowToast('Il benchmark sta impiegando oltre 30 minuti. Il job resta consultabile dal backend.', true);
          return;
        }

        try {
          const statusData = await apiJson<any>(`/api/eval/status/${jobId}`);
          pollErrors = 0;

          if (Array.isArray(statusData.testCases)) {
            setTestCases(statusData.testCases);
          }
          if (Array.isArray(statusData.results)) {
            setLiveMetrics(statusData.results);
          }

          if (['completed', 'completed_with_errors', 'failed'].includes(statusData.status)) {
            setIsRunningEval(false);
            onShowToast(
              statusData.status === 'failed'
                ? `Benchmark non completato: ${statusData.error || 'errore sconosciuto'}`
                : `Benchmark completato: ${statusData.results?.length || 0} metriche calcolate${statusData.error ? ` (${statusData.error})` : ''}.`,
              statusData.status === 'failed'
            );
            return;
          }

          window.setTimeout(() => void poll(), 1000);
        } catch (err) {
          pollErrors += 1;
          if (pollErrors >= 5) {
            setIsRunningEval(false);
            onShowToast(
              `Errore nel monitoraggio benchmark: ${err instanceof Error ? err.message : 'errore sconosciuto'}`,
              true
            );
            return;
          }
          window.setTimeout(() => void poll(), Math.min(5000, 1000 * pollErrors));
        }
      };

      await poll();
    } catch (err) {
      setIsRunningEval(false);
      onShowToast(`Impossibile avviare il benchmark: ${err instanceof Error ? err.message : 'errore sconosciuto'}`, true);
    }
  };

  return (
    <div className="p-6 flex flex-col gap-6 max-w-[1600px] mx-auto w-full relative z-10">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-[#171b26] p-6 rounded-xl border border-[#262a35] shadow-lg">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-[#262a35] flex items-center justify-center text-[#4cd7f6] shadow-[0_0_24px_rgba(76,215,246,0.25)] border border-[#3d494c]/50">
            <span className="material-symbols-outlined text-[28px]">rule</span>
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-1.5 font-mono text-[11px] text-[#4cd7f6] uppercase tracking-wider">
              <span>Quality Assurance &amp; RAG Benchmark</span>
              <span>•</span>
              <span className="text-[#bcc9cd]">RAG_EVAL</span>
            </div>
            <h1 className="text-[24px] sm:text-[28px] text-[#dfe2f1] tracking-tight font-semibold">
              RAG Quality Evaluations
            </h1>
            <p className="text-[13px] text-[#bcc9cd]">
              Valutazione automatizzata basata su retrieval reale, similarità query-risposta e giudizio LLM sulla fedeltà al contesto.
            </p>
          </div>
        </div>

        <button
          onClick={handleRunSuite}
          disabled={isRunningEval}
          className="flex items-center gap-2 px-5 py-2.5 bg-[#4cd7f6] hover:bg-[#06b6d4] text-[#003640] rounded-lg font-semibold text-[13px] transition-all shadow-[0_0_16px_-4px_rgba(76,215,246,0.5)] cursor-pointer disabled:opacity-50"
        >
          <span className={`material-symbols-outlined text-[18px] ${isRunningEval ? 'animate-spin' : ''}`}>
            {isRunningEval ? 'sync' : 'auto_fix_high'}
          </span>
          <span>{isRunningEval ? 'Valutazione in corso...' : 'Esegui Benchmark Suite'}</span>
        </button>
      </div>

      {/* Metrics Grid or Clean Empty State */}
      {liveMetrics.length === 0 ? (
        <div className="bg-[#171b26] p-12 rounded-xl border border-[#262a35] shadow-md flex flex-col items-center justify-center text-center gap-3">
          <span className="material-symbols-outlined text-[#4cd7f6] text-[48px] opacity-60">
            analytics
          </span>
          <h3 className="text-[18px] text-[#dfe2f1] font-semibold">Nessun Test di Valutazione Eseguito</h3>
          <p className="text-[13px] text-[#bcc9cd] max-w-lg">
            Nessuna valutazione eseguita. Avvia il benchmark per eseguire realmente le query sul database attivo e calcolare le metriche.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {liveMetrics.map((m) => (
            <div
              key={m.id}
              className="bg-[#171b26] p-5 rounded-xl border border-[#262a35] shadow-md flex flex-col justify-between gap-3"
            >
              <div className="flex flex-col gap-1">
                <div className="flex items-center justify-between">
                  <span className="text-[14px] text-[#dfe2f1] font-semibold">{m.name}</span>
                  <span className="font-mono text-[11px] text-[#10b981] bg-[#10b981]/15 px-2 py-0.5 rounded border border-[#10b981]/30">
                    {m.delta}
                  </span>
                </div>
                <p className="text-[12px] text-[#bcc9cd] leading-relaxed mt-1">{m.description}</p>
              </div>

              <div className="flex flex-col gap-2 pt-2 border-t border-[#262a35]">
                <div className="flex items-baseline justify-between font-mono">
                  <span className="text-[24px] font-bold text-[#4cd7f6]">
                    {(m.score * 100).toFixed(1)}%
                  </span>
                  <span className="text-[11px] text-[#bcc9cd]">
                    Target: &gt;{(m.benchmarkTarget * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="w-full h-2 bg-[#0a0e18] rounded-full overflow-hidden border border-[#262a35]">
                  <div
                    className="h-full bg-[#4cd7f6] rounded-full transition-all duration-500"
                    style={{ width: `${Math.min(m.score * 100, 100)}%` }}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Test Cases Table */}
      <div className="bg-[#171b26] rounded-xl border border-[#262a35] overflow-hidden shadow-md flex flex-col">
        <div className="p-4 bg-[#0a0e18] border-b border-[#262a35] flex items-center justify-between">
          <span className="text-[14px] text-[#dfe2f1] font-semibold">
            Test Case di Validazione Automatica
          </span>
          <span className="font-mono text-[11px] text-[#4cd7f6]">Status: {testCases.length ? `${testCases.filter((tc) => tc.status === 'Found').length}/${testCases.length} documenti ground-truth trovati` : 'Nessuna esecuzione'}</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-[12px]">
            <thead className="bg-[#0a0e18]/60 text-[#bcc9cd] font-mono text-[10px] uppercase tracking-wider border-b border-[#262a35]">
              <tr>
                <th className="py-3 px-4">ID</th>
                <th className="py-3 px-4">Domanda di Test</th>
                <th className="py-3 px-4">Documento Ground Truth</th>
                <th className="py-3 px-4">Retrieval Match</th>
                <th className="py-3 px-4 text-right">Esito</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#262a35]">
              {testCases.length === 0 ? (
                <tr><td colSpan={5} className="py-8 px-4 text-center text-[#bcc9cd]">Nessuna suite eseguita.</td></tr>
              ) : testCases.map((tc) => (
                <tr key={tc.id} className="hover:bg-[#1c1f2a]/60 transition-colors">
                  <td className="py-3 px-4 font-mono text-[#bcc9cd]">{tc.id}</td>
                  <td className="py-3 px-4 font-medium text-[#dfe2f1] font-sans">{tc.query}</td>
                  <td className="py-3 px-4 font-mono text-[#bcc9cd] truncate max-w-xs">
                    {tc.expectedDoc}
                  </td>
                  <td className="py-3 px-4 font-mono text-[#4cd7f6] font-semibold">
                    {typeof tc.retrievalMatch === 'number' ? `${(tc.retrievalMatch * 100).toFixed(1)}%` : '—'}
                  </td>
                  <td className="py-3 px-4 text-right font-mono">
                    <span className={`px-2 py-0.5 rounded text-[10px] border ${tc.status === 'Found' ? 'bg-[#10b981]/15 text-[#10b981] border-[#10b981]/30' : tc.status === 'Error' ? 'bg-red-500/15 text-red-400 border-red-500/30' : 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30'}`}>
                      {tc.status === 'Found' ? '✓' : tc.status === 'Error' ? '!' : '•'} {tc.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
