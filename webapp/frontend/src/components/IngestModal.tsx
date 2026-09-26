import { apiFetch, apiJson, apiUrl, getApiToken, setApiToken } from '../api';
import React, { useState } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

interface IngestModalProps {
  isOpen: boolean;
  onClose: () => void;
  onIngestSuccess: (filename: string, chunksCreated: number) => void;
  onShowToast: (msg: string, isError?: boolean) => void;
}

export const IngestModal: React.FC<IngestModalProps> = ({
  isOpen,
  onClose,
  onIngestSuccess,
  onShowToast,
}) => {
  const [fileObjects, setFileObjects] = useState<File[]>([]);
  const [selectionLabel, setSelectionLabel] = useState('');
  const [ocrEnabled, setOcrEnabled] = useState(true);
  const [chunkTokens, setChunkTokens] = useState(512);
  const [overlapPct, setOverlapPct] = useState(15);
  const [isProcessing, setIsProcessing] = useState(false);
  const [step, setStep] = useState<string>('');

  if (!isOpen) return null;

  const handleStartIngest = () => {
    setIsProcessing(true);
    setStep('Inizio caricamento e parsing...');

    const formData = new FormData();
    if (fileObjects.length) {
      fileObjects.forEach((item) => formData.append('files', item, item.name));
      formData.append('relativePaths', JSON.stringify(fileObjects.map((item) => (item as File & { webkitRelativePath?: string }).webkitRelativePath || item.name)));
    } else {
      onShowToast('Seleziona almeno un file o una cartella.', true);
      setIsProcessing(false);
      return;
    }
    formData.append('chunkSize', String(chunkTokens));
    formData.append('chunkOverlap', String(overlapPct));
    formData.append('ocrEnabled', String(ocrEnabled));

    apiFetch(`/api/ingest`, {
      method: 'POST',
      body: formData,
    })
      .then((res) => {
        if (!res.ok) throw new Error('Errore nella richiesta di ingest');
        return res.json();
      })
      .then((data) => {
        const jobId = data.jobId;
        setStep('Elaborazione in background in corso...');

        let pollErrors = 0;
        const startedAt = Date.now();
        const maxClientWaitMs = 30 * 60 * 1000;
        const poll = async () => {
          if (Date.now() - startedAt > maxClientWaitMs) {
            setIsProcessing(false);
            onShowToast("L'ingestion sta impiegando troppo tempo. Controlla lo stato dal backend.", true);
            return;
          }
          try {
            const res = await apiFetch(`/api/ingest/status/${jobId}`);
            const statusData = await res.json().catch(() => null);
            if (!res.ok) throw new Error(statusData?.detail || `HTTP ${res.status}`);
            pollErrors = 0;
            const processed = statusData.filesProcessed || 0;
            const total = statusData.filesTotal || fileObjects.length;
            const current = statusData.currentFile ? ` — ${statusData.currentFile}` : '';
            setStep(`${processed}/${total} file elaborati${current}`);
            if (statusData.status === 'completed') {
              setIsProcessing(false);
              const created = statusData.chunksCreated || 0;
              const ingestedName = fileObjects.length === 1 ? fileObjects[0].name : selectionLabel || `${fileObjects.length} file`;
              onIngestSuccess(ingestedName, created);
              const failed = statusData.filesFailed || 0;
              const suffix = failed ? ` (${failed} file con errore)` : '';
              onShowToast(`${ingestedName} indicizzato con successo (${created} chunks)${suffix}!`, Boolean(failed));
              onClose();
              return;
            }
            if (statusData.status === 'failed') {
              setIsProcessing(false);
              const details = statusData.errors?.slice?.(0, 3).map((e: any) => `${e.file}: ${e.error}`).join(' | ');
              onShowToast(`Errore durante l'ingest: ${statusData.error || details || 'errore sconosciuto'}`, true);
              return;
            }
            window.setTimeout(poll, 1000);
          } catch (err) {
            pollErrors += 1;
            if (pollErrors >= 5) {
              setIsProcessing(false);
              onShowToast(`Errore nel controllo dell'ingest: ${err instanceof Error ? err.message : 'errore sconosciuto'}`, true);
              return;
            }
            window.setTimeout(poll, Math.min(5000, 1000 * pollErrors));
          }
        };
        void poll();
      })
      .catch((err) => {
        setIsProcessing(false);
        onShowToast(`Impossibile avviare l'ingest: ${err.message}`, true);
      });
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
          <label className="border-2 border-dashed border-[#262a35] hover:border-[#4cd7f6]/50 rounded-xl p-6 flex flex-col items-center justify-center text-center bg-[#0a0e18] cursor-pointer transition-colors relative">
            <input
              type="file"
              multiple
              accept=".pdf,.json"
              onChange={(e) => {
                const files = Array.from(e.target.files || []).filter((f) => ['.pdf', '.json'].includes(f.name.slice(f.name.lastIndexOf('.')).toLowerCase()));
                setFileObjects(files);
                setSelectionLabel(files.length === 1 ? files[0].name : `${files.length} file selezionati`);
              }}
              className="absolute inset-0 opacity-0 cursor-pointer w-full h-full"
            />
            <input
              type="file"
              multiple
              accept=".pdf,.json"
              // @ts-expect-error webkitdirectory non e' ancora incluso nello standard TypeScript DOM
              webkitdirectory="true"
              // @ts-expect-error directory non e' ancora incluso nello standard TypeScript DOM
              directory="true"
              onChange={(e) => {
                const files = Array.from(e.target.files || []).filter((f) => ['.pdf', '.json'].includes(f.name.slice(f.name.lastIndexOf('.')).toLowerCase()));
                setFileObjects(files);
                setSelectionLabel(files.length ? `Cartella: ${files.length} file` : '');
              }}
              className="hidden"
              id="ingest-folder-input"
            />
            <span className="material-symbols-outlined text-[#4cd7f6] text-[36px] mb-2">
              cloud_upload
            </span>
            <span className="text-[13px] text-[#dfe2f1] font-semibold font-mono">
              {selectionLabel || 'Seleziona file oppure una cartella intera'}
            </span>
            <span className="text-[11px] text-[#bcc9cd] mt-1">
              {fileObjects.length ? `${fileObjects.length} file pronti per l'ingest` : 'File supportati: PDF e JSON'}
            </span>
          </label>
          <button
            type="button"
            onClick={() => document.getElementById('ingest-folder-input')?.click()}
            disabled={isProcessing}
            className="w-full px-4 py-2 bg-[#1c1f2a] hover:bg-[#262a35] text-[#dfe2f1] text-[12px] rounded-lg border border-[#262a35] font-mono disabled:opacity-50"
          >
            📁 Seleziona cartella intera
          </button>

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
