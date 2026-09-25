import React, { useState } from 'react';
import { EvalMetric } from '../types';

interface EvaluationsViewProps {
  metrics: EvalMetric[];
  onShowToast: (msg: string) => void;
}

export const EvaluationsView: React.FC<EvaluationsViewProps> = ({
  metrics,
  onShowToast,
}) => {
  const [isRunningEval, setIsRunningEval] = useState(false);

  const testCases = [
    {
      id: 'tc-1',
      query: 'Come si configura il lock della memoria VRAM in Ollama?',
      expectedDoc: 'Ollama_Local_Inference_VRAM_Benchmark.md',
      score: 0.98,
      status: 'Passed',
    },
    {
      id: 'tc-2',
      query: 'Qual è il numero di centroidi Voronoi raccomandato in LanceDB?',
      expectedDoc: 'LanceDB_IVF_PQ_Quantization_Whitepaper.pdf',
      score: 0.96,
      status: 'Passed',
    },
    {
      id: 'tc-3',
      query: 'In che modo Docling gestisce il chunking semantico senza tagliare tabelle?',
      expectedDoc: 'Docling_Layout_AST_Specification.pdf',
      score: 0.94,
      status: 'Passed',
    },
    {
      id: 'tc-4',
      query: 'Come funziona l\'integrazione tra threadpool UVicorn e libuv?',
      expectedDoc: 'FastAPI_Uvicorn_Orchestration_Guide.md',
      score: 0.95,
      status: 'Passed',
    },
  ];

  const handleRunSuite = () => {
    setIsRunningEval(true);
    setTimeout(() => {
      setIsRunningEval(false);
      onShowToast('Suite di valutazione Ragas completata! Score medio: 94.8% (+0.6%)');
    }, 900);
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
              <span>Quality Assurance &amp; Triad Benchmarks</span>
              <span>•</span>
              <span className="text-[#bcc9cd]">RAGAS_SUITE</span>
            </div>
            <h1 className="text-[24px] sm:text-[28px] text-[#dfe2f1] tracking-tight font-semibold">
              RAG Quality Evaluations &amp; Triad
            </h1>
            <p className="text-[13px] text-[#bcc9cd]">
              Valutazione automatizzata su fedeltà di recupero, assenza di allucinazioni e allineamento semantico della sintesi.
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

      {/* Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {metrics.map((m) => (
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

      {/* Test Cases Table */}
      <div className="bg-[#171b26] rounded-xl border border-[#262a35] overflow-hidden shadow-md flex flex-col">
        <div className="p-4 bg-[#0a0e18] border-b border-[#262a35] flex items-center justify-between">
          <span className="text-[14px] text-[#dfe2f1] font-semibold">
            Test Case di Validazione Automatica (4 query campionate)
          </span>
          <span className="font-mono text-[11px] text-[#4cd7f6]">Status: 4/4 Passed</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-[12px]">
            <thead className="bg-[#0a0e18]/60 text-[#bcc9cd] font-mono text-[10px] uppercase tracking-wider border-b border-[#262a35]">
              <tr>
                <th className="py-3 px-4">ID</th>
                <th className="py-3 px-4">Domanda di Test</th>
                <th className="py-3 px-4">Documento Ground Truth</th>
                <th className="py-3 px-4">Ragas Match</th>
                <th className="py-3 px-4 text-right">Esito</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#262a35]">
              {testCases.map((tc) => (
                <tr key={tc.id} className="hover:bg-[#1c1f2a]/60 transition-colors">
                  <td className="py-3 px-4 font-mono text-[#bcc9cd]">{tc.id}</td>
                  <td className="py-3 px-4 font-medium text-[#dfe2f1] font-sans">{tc.query}</td>
                  <td className="py-3 px-4 font-mono text-[#bcc9cd] truncate max-w-xs">
                    {tc.expectedDoc}
                  </td>
                  <td className="py-3 px-4 font-mono text-[#4cd7f6] font-semibold">
                    {(tc.score * 100).toFixed(1)}%
                  </td>
                  <td className="py-3 px-4 text-right font-mono">
                    <span className="px-2 py-0.5 rounded text-[10px] bg-[#10b981]/15 text-[#10b981] border border-[#10b981]/30">
                      ✓ {tc.status}
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
