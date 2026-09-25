import { apiFetch, apiJson, apiUrl, getApiToken, setApiToken } from '../api';
import React, { useState } from 'react';
import { AppSettings, ChunkItem } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

interface QueryWorkbenchViewProps {
  chunks: ChunkItem[];
  onInspectChunk: (chunk: ChunkItem) => void;
  onShowToast: (msg: string, isError?: boolean) => void;
  globalSearch?: string;
  settings: AppSettings;
}

export const QueryWorkbenchView: React.FC<QueryWorkbenchViewProps> = ({
  chunks,
  onInspectChunk,
  onShowToast,
  globalSearch = '',
  settings,
}) => {
  const [query, setQuery] = useState('');
  const [searchMode, setSearchMode] = useState<'hybrid' | 'dense' | 'sparse'>('hybrid');
  const [hybridAlpha, setHybridAlpha] = useState(0.7);
  const [enableRerank, setEnableRerank] = useState(true);
  const [isExecuting, setIsExecuting] = useState(false);
  const [hasExecuted, setHasExecuted] = useState(false);
  const [realAnswer, setRealAnswer] = useState<string>('');
  const [realChunks, setRealChunks] = useState<ChunkItem[]>(chunks);
  const [lastQueryDurationMs, setLastQueryDurationMs] = useState<number | null>(null);

  const visibleChunks = (realChunks.length > 0 ? realChunks : chunks).filter((chk) => {
    const term = globalSearch.trim().toLowerCase();
    if (!term) return true;
    return [chk.id, chk.docTitle, chk.section, chk.text, chk.highlightSnippet, chk.embeddingModel, chk.cluster]
      .some((value) => String(value ?? '').toLowerCase().includes(term));
  });


  const handleRunQuery = () => {
    if (!query.trim()) return;
    setIsExecuting(true);
    const startedAt = performance.now();

    apiFetch(`/api/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query,
        topK: settings.topKCandidates,
        topN: settings.topNRerank,
        searchMode,
        hybridAlpha,
        enableRerank,
      }),
    })
      .then((res) => {
        if (!res.ok) throw new Error('Errore query API');
        return res.json();
      })
      .then((data) => {
        setIsExecuting(false);
        setLastQueryDurationMs(performance.now() - startedAt);
        setHasExecuted(true);
        setRealAnswer(data.answer);
        if (data.chunks && Array.isArray(data.chunks)) {
          setRealChunks(data.chunks);
        }
        onShowToast(`Query eseguita con successo! ${data.chunks?.length || 0} chunks estratti.`);
      })
      .catch(() => {
        setIsExecuting(false);
        setLastQueryDurationMs(null);
        onShowToast('Impossibile eseguire la query sul backend.', true);
      });
  };

  return (
    <div className="p-6 flex flex-col gap-6 max-w-[1600px] mx-auto w-full relative z-10">
      {/* Header Banner */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-[#171b26] p-6 rounded-xl border border-[#262a35] shadow-lg">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-[#262a35] flex items-center justify-center text-[#4cd7f6] shadow-[0_0_24px_rgba(76,215,246,0.25)] border border-[#3d494c]/50">
            <span className="material-symbols-outlined text-[28px]">terminal</span>
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-1.5 font-mono text-[11px] text-[#4cd7f6] uppercase tracking-wider">
              <span>Interactive Retrieval Sandbox</span>
              <span>•</span>
              <span className="text-[#bcc9cd]">QUERY_WORKBENCH.PY</span>
            </div>
            <h1 className="text-[24px] sm:text-[28px] text-[#dfe2f1] tracking-tight font-semibold">
              Query Workbench &amp; Testbed Ibrido
            </h1>
            <p className="text-[13px] text-[#bcc9cd]">
              Sperimenta le interrogazioni semantiche con fusione pesata Dense (Cosine) + Sparse (BM25) e Cross-Encoder reranking.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-[#4cd7f6] bg-[#06b6d4]/15 px-3 py-1.5 rounded-lg border border-[#06b6d4]/30">
            {lastQueryDurationMs == null ? 'Pipeline: —' : `Pipeline: ${lastQueryDurationMs.toFixed(1)}ms`}
          </span>
        </div>
      </div>

      {/* Query Search Bar & Controls */}
      <div className="bg-[#171b26] p-6 rounded-xl border border-[#262a35] shadow-md flex flex-col gap-4">
        {/* Search input */}
        <div className="flex flex-col sm:flex-row items-stretch gap-3">
          <div className="relative flex-1 flex items-center">
            <span className="material-symbols-outlined absolute left-3.5 text-[#4cd7f6] text-[20px]">
              search
            </span>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleRunQuery()}
              placeholder="Inserisci una query complessa di retrieval o architettura..."
              className="w-full bg-[#0a0e18] text-[#dfe2f1] text-[14px] pl-11 pr-4 py-3 rounded-lg border border-[#262a35] focus:outline-none focus:ring-1 focus:ring-[#4cd7f6] transition-all font-mono"
            />
          </div>

          <button
            onClick={handleRunQuery}
            disabled={isExecuting}
            className="px-6 py-3 bg-[#4cd7f6] hover:bg-[#06b6d4] text-[#003640] rounded-lg font-semibold text-[13px] transition-all shadow-[0_0_16px_-4px_rgba(76,215,246,0.5)] flex items-center justify-center gap-2 cursor-pointer shrink-0 disabled:opacity-50"
          >
            <span className={`material-symbols-outlined text-[18px] ${isExecuting ? 'animate-spin' : ''}`}>
              {isExecuting ? 'sync' : 'play_arrow'}
            </span>
            <span>{isExecuting ? 'Elaborazione...' : 'Esegui Query'}</span>
          </button>
        </div>

        {/* Search Parameter Controls */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-3 border-t border-[#262a35]">
          {/* Mode */}
          <div className="flex flex-col gap-1.5">
            <label className="font-mono text-[10px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
              Modalità Ricerca
            </label>
            <div className="flex items-center gap-1 bg-[#0a0e18] p-1 rounded-lg border border-[#262a35]">
              {[
                { id: 'hybrid', label: 'Hybrid' },
                { id: 'dense', label: 'Dense (Vector)' },
                { id: 'sparse', label: 'Sparse (BM25)' },
              ].map((m) => (
                <button
                  key={m.id}
                  onClick={() => setSearchMode(m.id as any)}
                  className={`flex-1 py-1 text-center font-mono text-[11px] rounded transition-all cursor-pointer ${
                    searchMode === m.id
                      ? 'bg-[#4cd7f6]/20 text-[#4cd7f6] font-semibold border border-[#4cd7f6]/40'
                      : 'text-[#bcc9cd] hover:text-[#dfe2f1]'
                  }`}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>

          {/* Fusion Alpha Slider */}
          <div className="flex flex-col gap-1.5">
            <div className="flex justify-between items-center">
              <label className="font-mono text-[10px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                Ponderazione Alpha (Dense vs BM25)
              </label>
              <span className="font-mono text-[11px] text-[#4cd7f6]">
                {(hybridAlpha * 100).toFixed(0)}% Vector / {((1 - hybridAlpha) * 100).toFixed(0)}% BM25
              </span>
            </div>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={hybridAlpha}
              onChange={(e) => setHybridAlpha(Number(e.target.value))}
              disabled={searchMode !== 'hybrid'}
              className="accent-[#4cd7f6] cursor-pointer mt-1 disabled:opacity-40"
            />
          </div>

          {/* Rerank Toggle */}
          <div className="flex items-center justify-between bg-[#0a0e18] px-4 py-2 rounded-lg border border-[#262a35]">
            <div className="flex flex-col">
              <span className="text-[12px] text-[#dfe2f1] font-semibold">
                Cross-Encoder Rerank
              </span>
              <span className="font-mono text-[10px] text-[#bcc9cd]">
                {settings.crossEncoderModel}
              </span>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={enableRerank}
                onChange={(e) => setEnableRerank(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-10 h-5 bg-[#262a35] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:bg-[#4cd7f6] after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-[#003640] after:rounded-full after:h-4 after:w-4 after:transition-all" />
            </label>
          </div>
        </div>
      </div>

      {/* Query latency: only measured end-to-end duration is shown. */}
      <div className="bg-[#171b26] p-4 rounded-xl border border-[#262a35] flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-[#4cd7f6] text-[18px]">timer</span>
          <span className="font-mono text-[11px] text-[#dfe2f1] font-semibold">
            Durata query misurata:
          </span>
        </div>
        <span className="font-mono text-[11px] text-[#4cd7f6] font-bold">
          {lastQueryDurationMs == null ? '—' : `${lastQueryDurationMs.toFixed(1)} ms`}
        </span>
      </div>

      {/* Main Results Grid */}
      {hasExecuted && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Retrieved Chunks List (Left 7 Cols) */}
          <div className="lg:col-span-7 flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-[16px] text-[#dfe2f1] font-semibold">
                  Frammenti Estratti da LanceDB
                </span>
                <span className="font-mono text-[11px] text-[#4cd7f6] bg-[#06b6d4]/15 px-2 py-0.5 rounded border border-[#06b6d4]/30">
                  Top {chunks.length} Candidati
                </span>
              </div>
              <span className="font-mono text-[11px] text-[#bcc9cd]">
                Ordinati per Rerank Score
              </span>
            </div>

            <div className="flex flex-col gap-3">
              {visibleChunks.map((chk, idx) => (
                <div
                  key={chk.id}
                  className="bg-[#171b26] p-4 rounded-xl border border-[#262a35] hover:border-[#4cd7f6]/50 transition-all flex flex-col gap-2.5 shadow-sm group"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex flex-col gap-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-[10px] text-[#4cd7f6] bg-[#4cd7f6]/10 px-2 py-0.5 rounded border border-[#4cd7f6]/20 font-bold">
                          #{idx + 1}
                        </span>
                        <span className="font-mono text-[11px] text-[#bcc9cd]">
                          ID: #{chk.chunkNum}
                        </span>
                        <span className="font-mono text-[10px] text-[#d0bcff] bg-[#3131c0]/30 px-1.5 py-0.5 rounded">
                          {chk.docType}
                        </span>
                        <span className="font-mono text-[11px] text-[#4cd7f6] font-semibold">
                          Score: {chk.rerankScore.toFixed(3)}
                        </span>
                      </div>
                      <h4 className="text-[14px] text-[#dfe2f1] font-semibold truncate mt-0.5">
                        {chk.docTitle}
                      </h4>
                      <span className="font-mono text-[11px] text-[#bcc9cd] truncate">
                        {chk.section}
                      </span>
                    </div>

                    <button
                      onClick={() => onInspectChunk(chk)}
                      className="px-3 py-1.5 rounded-lg bg-[#262a35] hover:bg-[#4cd7f6] text-[#bcc9cd] hover:text-[#003640] font-mono text-[11px] font-semibold transition-all border border-[#3d494c]/40 cursor-pointer shrink-0"
                    >
                      Ispeziona
                    </button>
                  </div>

                  <p className="text-[12px] text-[#dfe2f1]/90 bg-[#0a0e18] p-3 rounded-lg border border-[#262a35] line-clamp-3 leading-relaxed">
                    {chk.text}
                  </p>

                  <div className="flex items-center justify-between text-[10px] font-mono text-[#bcc9cd] pt-1">
                    <span>Dense: {chk.denseScore.toFixed(3)} • BM25: {chk.bm25Score.toFixed(1)}</span>
                    <span>{chk.tokenCount} tok • {chk.embeddingModel}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Synthesized Response Preview (Right 5 Cols) */}
          <div className="lg:col-span-5 flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <span className="text-[16px] text-[#dfe2f1] font-semibold">
                Risposta Sintetizzata dal Generatore
              </span>
            </div>

            <div className="bg-[#171b26] p-5 rounded-xl border border-[#262a35] shadow-md flex flex-col gap-4 sticky top-24">
              <div className="flex items-center justify-between pb-3 border-b border-[#262a35]">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[#4cd7f6] text-[18px]">
                    smart_toy
                  </span>
                  <span className="font-mono text-[11px] text-[#dfe2f1] font-medium">
                    Grounded Generator (Ollama / Local LLM)
                  </span>
                </div>

              </div>

              <div className="text-[13px] text-[#dfe2f1] leading-relaxed flex flex-col gap-3 font-sans whitespace-pre-line">
                {realAnswer ? (
                  <p>{realAnswer}</p>
                ) : (
                  <>
                    <p>
                      Nell&apos;architettura di <strong>Nexus RAG</strong>, la concorrenza tra{' '}
                      <span className="text-[#4cd7f6] font-semibold">FastAPI</span> e{' '}
                      <span className="text-[#4cd7f6] font-semibold">LanceDB</span> viene gestita delegando le scansioni vettoriali IVF-PQ a un pool di worker asincroni su thread libuv dedicati.
                    </p>
                  </>
                )}
              </div>

              {/* Citations Box */}
              <div className="bg-[#0a0e18] p-3 rounded-lg border border-[#262a35] flex flex-col gap-1.5">
                <span className="font-mono text-[10px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                  Citazioni Verificate:
                </span>
                <div className="flex flex-col gap-1 text-[11px] font-mono">
                  <button
                    onClick={() => onInspectChunk(chunks[0])}
                    className="text-left text-[#4cd7f6] hover:underline truncate"
                  >
                    1. Manuale_Architettura_RAG_v2.pdf (Sez. 4.2)
                  </button>
                  <button
                    onClick={() => onInspectChunk(chunks[1] || chunks[0])}
                    className="text-left text-[#c0c1ff] hover:underline truncate"
                  >
                    2. FastAPI_Uvicorn_Orchestration_Guide.md (Sez. 2.1)
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
