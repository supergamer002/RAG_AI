import { apiFetch, apiJson, apiUrl, getApiToken, setApiToken } from '../api';
import React, { useState } from 'react';
import { ChunkItem } from '../types';

interface ChunkModalProps {
  chunk: ChunkItem | null;
  isOpen: boolean;
  onClose: () => void;
  onShowToast: (msg: string, isError?: boolean) => void;
}

export const ChunkModal: React.FC<ChunkModalProps> = ({
  chunk,
  isOpen,
  onClose,
  onShowToast,
}) => {
  const [showVectorRaw, setShowVectorRaw] = useState(false);

  if (!isOpen || !chunk) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(chunk.text);
    onShowToast(`Testo del Chunk #${chunk.chunkNum} copiato negli appunti!`);
  };

  const handleDownload = () => {
    const blob = new Blob([JSON.stringify(chunk, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `chunk_${chunk.chunkNum}_${chunk.docTitle.replace(/\s+/g, '_')}.json`;
    a.click();
    URL.revokeObjectURL(url);
    onShowToast(`Estratto Chunk #${chunk.chunkNum} scaricato.`);
  };

  const [realVector, setRealVector] = useState<number[]>([]);
  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

  const handleToggleVector = () => {
    if (!showVectorRaw && realVector.length === 0) {
      apiFetch(`/api/chunks/${chunk.id}/vector`)
        .then((res) => res.ok ? res.json() : null)
        .then((data) => {
          if (data && data.vector) {
            setRealVector(data.vector);
          }
        })
        .catch((err) => {
          onShowToast(`Errore caricamento vettore: ${err instanceof Error ? err.message : 'errore sconosciuto'}`, true);
        });
    }
    setShowVectorRaw(!showVectorRaw);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-[#0f131d]/80 backdrop-blur-xl transition-all duration-200 overflow-y-auto"
      style={{ overscrollBehavior: 'contain' }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="relative w-full max-w-4xl max-h-[92vh] bg-[#171b26] rounded-xl shadow-2xl flex flex-col overflow-hidden border border-[#262a35]">
        {/* Modal Header */}
        <div className="p-4 sm:p-5 bg-[#0a0e18] flex items-start justify-between gap-4 border-b border-[#262a35]">
          <div className="flex flex-col gap-1.5 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="px-2 py-0.5 bg-[#4cd7f6]/20 text-[#4cd7f6] rounded font-mono text-[10px] uppercase font-bold tracking-wider border border-[#4cd7f6]/30">
                {chunk.docType}
              </span>
              <span className="px-2 py-0.5 bg-[#1c1f2a] text-[#bcc9cd] rounded font-mono text-[11px] border border-[#262a35]">
                Chunk ID: #{chunk.chunkNum}
              </span>
              <span className="px-2 py-0.5 bg-[#06b6d4]/20 text-[#4cd7f6] rounded font-mono text-[11px] font-semibold border border-[#06b6d4]/30">
                Rerank: {chunk.rerankScore.toFixed(3)}
              </span>
              <span className="px-2 py-0.5 bg-[#3131c0]/40 text-[#c0c1ff] rounded font-mono text-[11px] border border-[#3131c0]/60">
                Dense: {chunk.denseScore.toFixed(3)}
              </span>
              {chunk.rankDelta !== 0 && (
                <span className="px-2 py-0.5 bg-[#10b981]/20 text-[#10b981] rounded font-mono text-[11px]">
                  Delta: {chunk.rankDelta > 0 ? `+${chunk.rankDelta}` : chunk.rankDelta}
                </span>
              )}
            </div>

            <h2 className="text-[18px] sm:text-[20px] text-[#dfe2f1] font-semibold tracking-tight truncate">
              {chunk.docTitle}
            </h2>

            <div className="flex items-center gap-1.5 font-mono text-[11px] text-[#bcc9cd] truncate">
              <span className="material-symbols-outlined text-[15px] text-[#4cd7f6]">
                bookmark
              </span>
              <span>{chunk.section}</span>
            </div>
          </div>

          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg bg-[#1c1f2a] hover:bg-[#262a35] text-[#bcc9cd] hover:text-[#dfe2f1] flex items-center justify-center transition-colors border border-[#262a35] shrink-0"
            title="Chiudi modale"
          >
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-5 sm:p-6 overflow-y-auto flex-1 grid grid-cols-1 lg:grid-cols-12 gap-5 max-h-[calc(90vh-140px)]">
          {/* Left Text Extract */}
          <div className="lg:col-span-8 flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="font-mono text-[10px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                Estratto Completo del Chunk
              </span>
              <span className="font-mono text-[11px] text-[#4cd7f6]">
                {chunk.tokenCount} Tokens{chunk.overlapPct == null ? '' : ` (Sovrapposizione ${chunk.overlapPct}%)`}
              </span>
            </div>

            <div className="bg-[#0a0e18] p-4 rounded-lg text-[13px] text-[#dfe2f1] leading-relaxed flex flex-col gap-3 border border-[#262a35] max-h-[46vh] overflow-y-auto font-sans whitespace-pre-wrap">
              <p>{chunk.text}</p>
            </div>

            {/* Vector Inspector Collapsible */}
            {showVectorRaw && (
              <div className="mt-2 bg-[#0a0e18] p-3 rounded-lg border border-[#4cd7f6]/40 flex flex-col gap-2">
                <div className="flex items-center justify-between text-[11px] font-mono">
                  <span className="text-[#4cd7f6] font-semibold">
                    Visualizzazione Spazio Vettoriale Reale LanceDB
                  </span>
                  <span className="text-[#bcc9cd]">{realVector.length > 0 ? `${realVector.length} dims caricate` : 'Caricamento...'}</span>
                </div>
                {/* Visual heat strip */}
                {realVector.length > 0 && <div className="grid grid-cols-16 sm:grid-cols-32 gap-1 py-1">
                  {realVector.slice(0, 64).map((val, idx) => {
                    const norm = Math.min(Math.max((val + 0.5) / 1.0, 0), 1);
                    return (
                      <div
                        key={idx}
                        title={`Dim #${idx}: ${val}`}
                        className="h-4 rounded-xs transition-transform hover:scale-125"
                        style={{
                          backgroundColor: `rgba(76, 215, 246, ${Math.max(norm, 0.15)})`,
                        }}
                      />
                    );
                  })}
                </div>}
                <div className="font-mono text-[10px] text-[#bcc9cd] max-h-20 overflow-y-auto bg-[#171b26] p-2 rounded border border-[#262a35] break-all">
                  {realVector.length > 0 ? `[${realVector.join(', ')}]` : 'Vettore non disponibile.'}
                </div>
              </div>
            )}
          </div>

          {/* Right Metadata Column */}
          <div className="lg:col-span-4 flex flex-col gap-2.5 bg-[#0a0e18] p-4 rounded-lg border border-[#262a35]">
            <span className="font-mono text-[10px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
              Metadati &amp; Info Vettoriali
            </span>

            <div className="flex flex-col gap-1.5 font-mono text-[11px]">
              <div className="flex justify-between py-1.5 px-2 bg-[#1c1f2a]/60 rounded border border-[#262a35]/40">
                <span className="text-[#bcc9cd]">Tabella LanceDB:</span>
                <span className="text-[#4cd7f6] font-medium">{chunk.vectorTable ?? '—'}</span>
              </div>
              <div className="flex justify-between py-1.5 px-2 bg-[#1c1f2a]/60 rounded border border-[#262a35]/40">
                <span className="text-[#bcc9cd]">Embedding Model:</span>
                <span className="text-[#dfe2f1] font-medium">{chunk.embeddingModel}</span>
              </div>
              <div className="flex justify-between py-1.5 px-2 bg-[#1c1f2a]/60 rounded border border-[#262a35]/40">
                <span className="text-[#bcc9cd]">Dimensioni:</span>
                <span className="text-[#d0bcff] font-medium">{chunk.dimensions}</span>
              </div>
              <div className="flex justify-between py-1.5 px-2 bg-[#1c1f2a]/60 rounded border border-[#262a35]/40">
                <span className="text-[#bcc9cd]">Offset Caratteri:</span>
                <span className="text-[#dfe2f1] font-medium">{chunk.charOffset}</span>
              </div>
              <div className="flex justify-between py-1.5 px-2 bg-[#1c1f2a]/60 rounded border border-[#262a35]/40">
                <span className="text-[#bcc9cd]">Docling Parser:</span>
                <span className="text-[#4cd7f6] font-medium">{chunk.parser ?? '—'}</span>
              </div>
              <div className="flex justify-between py-1.5 px-2 bg-[#1c1f2a]/60 rounded border border-[#262a35]/40">
                <span className="text-[#bcc9cd]">Timestamp Ingest:</span>
                <span className="text-[#dfe2f1] font-medium">{chunk.timestamp || '—'}</span>
              </div>
              <div className="flex justify-between py-1.5 px-2 bg-[#1c1f2a]/60 rounded border border-[#262a35]/40">
                <span className="text-[#bcc9cd]">Cross-Score:</span>
                <span className="text-[#4cd7f6] font-bold">
                  {chunk.rerankScore.toFixed(3)} / 1.0
                </span>
              </div>
              <div className="flex justify-between py-1.5 px-2 bg-[#1c1f2a]/60 rounded border border-[#262a35]/40">
                <span className="text-[#bcc9cd]">BM25 Term Score:</span>
                <span className="text-[#c0c1ff] font-medium">{chunk.bm25Score.toFixed(1)}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Modal Footer Actions */}
        <div className="p-4 bg-[#0a0e18] flex flex-wrap items-center justify-between gap-3 border-t border-[#262a35]">
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={handleCopy}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#1c1f2a] hover:bg-[#262a35] text-[#dfe2f1] text-[12px] font-mono transition-colors border border-[#262a35]"
            >
              <span className="material-symbols-outlined text-[16px] text-[#4cd7f6]">
                content_copy
              </span>
              <span>Copia Testo Chunk</span>
            </button>

            <button
              onClick={handleDownload}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#1c1f2a] hover:bg-[#262a35] text-[#dfe2f1] text-[12px] font-mono transition-colors border border-[#262a35]"
            >
              <span className="material-symbols-outlined text-[16px] text-[#c0c1ff]">
                download
              </span>
              <span>Scarica Estratto</span>
            </button>

            <button
              onClick={handleToggleVector}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[12px] font-mono transition-colors border ${
                showVectorRaw
                  ? 'bg-[#4cd7f6]/20 text-[#4cd7f6] border-[#4cd7f6]/50'
                  : 'bg-[#1c1f2a] hover:bg-[#262a35] text-[#dfe2f1] border-[#262a35]'
              }`}
            >
              <span className="material-symbols-outlined text-[16px] text-[#d0bcff]">
                data_object
              </span>
              <span>{showVectorRaw ? 'Nascondi Vettore' : 'Ispeziona Vettore'}</span>
            </button>
          </div>

          <button
            onClick={onClose}
            className="px-5 py-1.5 bg-[#4cd7f6] hover:bg-[#06b6d4] text-[#003640] text-[12px] rounded-lg font-semibold transition-all shadow-md"
          >
            Chiudi
          </button>
        </div>
      </div>
    </div>
  );
};
