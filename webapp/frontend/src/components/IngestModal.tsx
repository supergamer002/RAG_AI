import React, { useState } from 'react';

interface IngestModalProps {
  isOpen: boolean;
  onClose: () => void;
  onIngestSuccess: (filename: string, chunksCreated: number) => void;
  onShowToast: (msg: string) => void;
}

export const IngestModal: React.FC<IngestModalProps> = ({
  isOpen,
  onClose,
  onIngestSuccess,
  onShowToast,
}) => {
  const [selectedFile, setSelectedFile] = useState<string>('Specifiche_Tecniche_LanceDB_v0.12.pdf');
  const [ocrEnabled, setOcrEnabled] = useState(true);
  const [chunkTokens, setChunkTokens] = useState(512);
  const [overlapPct, setOverlapPct] = useState(15);
  const [isProcessing, setIsProcessing] = useState(false);
  const [step, setStep] = useState<string>('');

  if (!isOpen) return null;

  const handleStartIngest = () => {
    setIsProcessing(true);
    setStep('Docling layout parsing (AST extraction)...');

    setTimeout(() => {
      setStep('Calcolo embeddings vettoriali via nomic-embed-text (1024-dim)...');
      setTimeout(() => {
        setStep('Scrittura IVF-PQ index in tabella "rag_chunks"...');
        setTimeout(() => {
          setIsProcessing(false);
          const chunks = Math.floor(Math.random() * 200) + 180;
          onIngestSuccess(selectedFile, chunks);
          onShowToast(`File "${selectedFile}" indicizzato con successo (${chunks} chunks)!`);
          onClose();
        }, 600);
      }, 700);
    }, 800);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#0f131d]/85 backdrop-blur-xl"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isProcessing) onClose();
      }}
    >
      <div className="relative w-full max-w-xl bg-[#171b26] rounded-xl border border-[#262a35] shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="p-5 bg-[#0a0e18] flex items-center justify-between border-b border-[#262a35]">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#262a35] flex items-center justify-center text-[#4cd7f6] border border-[#3d494c]/40">
              <span className="material-symbols-outlined text-[20px]">upload_file</span>
            </div>
            <div>
              <h2 className="text-[16px] text-[#dfe2f1] font-semibold">
                Ingest &amp; Indicizzazione Documenti
              </h2>
              <span className="font-mono text-[11px] text-[#bcc9cd]">
                Parser Docling AST + LanceDB
              </span>
            </div>
          </div>

          {!isProcessing && (
            <button
              onClick={onClose}
              className="text-[#bcc9cd] hover:text-[#dfe2f1] p-1 rounded transition-colors"
            >
              ✕
            </button>
          )}
        </div>

        {/* Content */}
        <div className="p-6 flex flex-col gap-4">
          {/* File Selection Box */}
          <div className="border-2 border-dashed border-[#262a35] hover:border-[#4cd7f6]/50 rounded-xl p-6 flex flex-col items-center justify-center text-center bg-[#0a0e18] cursor-pointer transition-colors">
            <span className="material-symbols-outlined text-[#4cd7f6] text-[36px] mb-2">
              cloud_upload
            </span>
            <span className="text-[13px] text-[#dfe2f1] font-semibold font-mono">
              {selectedFile}
            </span>
            <span className="text-[11px] text-[#bcc9cd] mt-1">
              Trascina o seleziona un file PDF, Markdown, DOCX o TXT (Max 50MB)
            </span>
          </div>

          {/* Config options */}
          <div className="grid grid-cols-2 gap-4 pt-1 font-mono text-[12px]">
            <div className="flex flex-col gap-1.5">
              <label className="text-[10px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                Chunk Size
              </label>
              <select
                value={chunkTokens}
                onChange={(e) => setChunkTokens(Number(e.target.value))}
                className="bg-[#0a0e18] text-[#dfe2f1] p-2 rounded-lg border border-[#262a35] focus:outline-none"
              >
                <option value="256">256 Tokens</option>
                <option value="512">512 Tokens (Consigliato)</option>
                <option value="1024">1024 Tokens</option>
              </select>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-[10px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                Overlap (%)
              </label>
              <select
                value={overlapPct}
                onChange={(e) => setOverlapPct(Number(e.target.value))}
                className="bg-[#0a0e18] text-[#dfe2f1] p-2 rounded-lg border border-[#262a35] focus:outline-none"
              >
                <option value="10">10%</option>
                <option value="15">15% (Bilanciato)</option>
                <option value="20">20%</option>
              </select>
            </div>
          </div>

          <div className="flex items-center justify-between bg-[#0a0e18] p-3 rounded-lg border border-[#262a35]">
            <div className="flex flex-col">
              <span className="text-[12px] text-[#dfe2f1] font-semibold">
                Estrazione Tabelle &amp; Grafici (Docling OCR)
              </span>
              <span className="font-mono text-[10px] text-[#bcc9cd]">
                Riconoscimento semantico delle matrici
              </span>
            </div>
            <input
              type="checkbox"
              checked={ocrEnabled}
              onChange={(e) => setOcrEnabled(e.target.checked)}
              className="accent-[#4cd7f6] w-4 h-4 cursor-pointer"
            />
          </div>

          {/* Progress State */}
          {isProcessing && (
            <div className="bg-[#0a0e18] p-3.5 rounded-lg border border-[#4cd7f6]/40 flex flex-col gap-2">
              <div className="flex items-center gap-2 text-[12px] font-mono text-[#4cd7f6]">
                <span className="material-symbols-outlined text-[16px] animate-spin">
                  sync
                </span>
                <span>{step}</span>
              </div>
              <div className="w-full h-1.5 bg-[#171b26] rounded-full overflow-hidden">
                <div className="w-2/3 h-full bg-[#4cd7f6] animate-pulse rounded-full" />
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 bg-[#0a0e18] flex items-center justify-end gap-3 border-t border-[#262a35]">
          <button
            type="button"
            onClick={onClose}
            disabled={isProcessing}
            className="px-4 py-2 bg-[#1c1f2a] hover:bg-[#262a35] text-[#dfe2f1] text-[12px] rounded-lg transition-colors font-mono cursor-pointer disabled:opacity-50"
          >
            Annulla
          </button>
          <button
            type="button"
            onClick={handleStartIngest}
            disabled={isProcessing}
            className="px-5 py-2 bg-[#4cd7f6] hover:bg-[#06b6d4] text-[#003640] font-semibold text-[12px] rounded-lg transition-all shadow-md font-mono flex items-center gap-2 cursor-pointer disabled:opacity-50"
          >
            <span className="material-symbols-outlined text-[16px]">play_arrow</span>
            <span>{isProcessing ? 'Ingestion in corso...' : 'Avvia Ingestion'}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
