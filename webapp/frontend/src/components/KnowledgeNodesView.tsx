import { apiFetch, apiJson, apiUrl, getApiToken, setApiToken } from '../api';
import React, { useState } from 'react';
import { KnowledgeDocument } from '../types';

interface KnowledgeNodesViewProps {
  documents: KnowledgeDocument[];
  onShowToast: (msg: string, isError?: boolean) => void;
  onOpenIngest: () => void;
  globalSearch?: string;
  chunksCount?: number | null;
  activeDatabaseName?: string | null;
  storageBytes?: number | null;
}

const formatBytes = (bytes: number): string => {
  if (!Number.isFinite(bytes) || bytes < 0) return '—';
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** exponent).toFixed(exponent === 0 ? 0 : 2)} ${units[exponent]}`;
};

export const KnowledgeNodesView: React.FC<KnowledgeNodesViewProps> = ({
  documents,
  onShowToast,
  onOpenIngest,
  globalSearch = '',
  chunksCount = null,
  activeDatabaseName = null,
  storageBytes = null,
}) => {
  const [filterType, setFilterType] = useState<string>('all');
  const [searchTerm, setSearchTerm] = useState('');

  const filteredDocs = documents.filter((doc) => {
    const matchesType = filterType === 'all' || doc.type.toLowerCase() === filterType.toLowerCase();
    const localSearch = searchTerm.trim().toLowerCase();
    const global = globalSearch.trim().toLowerCase();
    const matchesSearch =
      !localSearch ||
      doc.name.toLowerCase().includes(localSearch) ||
      doc.vectorTable.toLowerCase().includes(localSearch);
    const matchesGlobal =
      !global ||
      [doc.name, doc.type, doc.vectorTable, doc.status].some((value) =>
        value.toLowerCase().includes(global)
      );
    return matchesType && matchesSearch && matchesGlobal;
  });

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

  const handleReindex = (docId: string, docName: string) => {
    apiFetch(`/api/documents/${docId}/reindex`, {
      method: 'POST',
    })
      .then((res) => {
        if (!res.ok) throw new Error('Errore durante la re-indicizzazione');
        return res.json();
      })
      .then((data) => {
        onShowToast(`Re-indicizzazione avviata in background per "${docName}" (Job ID: ${data.jobId.slice(0, 8)}).`);
      })
      .catch((err) => {
        onShowToast(`Impossibile re-indicizzare "${docName}": ${err.message}`, true);
      });
  };

  return (
    <div className="p-6 flex flex-col gap-6 max-w-[1600px] mx-auto w-full relative z-10">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-[#171b26] p-6 rounded-xl border border-[#262a35] shadow-lg">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-[#262a35] flex items-center justify-center text-[#4cd7f6] shadow-[0_0_24px_rgba(76,215,246,0.25)] border border-[#3d494c]/50">
            <span className="material-symbols-outlined text-[28px]">hub</span>
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-1.5 font-mono text-[11px] text-[#4cd7f6] uppercase tracking-wider">
              <span>Knowledge Source Corpus</span>
              <span>•</span>
              <span className="text-[#bcc9cd]">ACTIVE_DATABASE</span>
            </div>
            <h1 className="text-[24px] sm:text-[28px] text-[#dfe2f1] tracking-tight font-semibold">
              Knowledge Nodes &amp; Corpus Documentale
            </h1>
            <p className="text-[13px] text-[#bcc9cd]">
              Monitora i file caricati, i nodi AST generati da Docling e la suddivisione in frammenti vettorializzati su LanceDB.
            </p>
          </div>
        </div>

        <button
          onClick={onOpenIngest}
          className="flex items-center gap-2 px-5 py-2.5 bg-[#4cd7f6] hover:bg-[#06b6d4] text-[#003640] rounded-lg font-semibold text-[13px] transition-all shadow-[0_0_16px_-4px_rgba(76,215,246,0.5)] cursor-pointer shrink-0"
        >
          <span className="material-symbols-outlined text-[18px]">upload_file</span>
          <span>Ingest Nuovo File</span>
        </button>
      </div>

      {/* Summary Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-[#171b26] p-4 rounded-xl border border-[#262a35]">
          <span className="font-mono text-[10px] text-[#bcc9cd] uppercase tracking-wider">
            Documenti Attivi
          </span>
          <div className="text-[22px] font-semibold text-[#dfe2f1] mt-1">
            {documents.length}{' '}
            <span className="text-[12px] font-normal text-[#bcc9cd]">file verificati</span>
          </div>
          <span className="font-mono text-[11px] text-[#4cd7f6] mt-0.5">
            100% Parsed con Docling AST
          </span>
        </div>

        <div className="bg-[#171b26] p-4 rounded-xl border border-[#262a35]">
          <span className="font-mono text-[10px] text-[#bcc9cd] uppercase tracking-wider">
            Totale Chunks Generati
          </span>
          <div className="text-[22px] font-semibold text-[#dfe2f1] mt-1">
            {chunksCount == null ? '—' : chunksCount.toLocaleString()} <span className="text-[12px] font-normal text-[#bcc9cd]">frammenti</span>
          </div>
          <span className="font-mono text-[11px] text-[#d0bcff] mt-0.5">
            Conteggio restituito dal database attivo
          </span>
        </div>

        <div className="bg-[#171b26] p-4 rounded-xl border border-[#262a35]">
          <span className="font-mono text-[10px] text-[#bcc9cd] uppercase tracking-wider">
            Database attivo
          </span>
          <div className="text-[22px] font-semibold text-[#dfe2f1] mt-1 truncate">{activeDatabaseName ?? "—"}</div>
          <span className="font-mono text-[11px] text-[#c0c1ff] mt-0.5">
            Identificativo fornito dal backend
          </span>
        </div>

        <div className="bg-[#171b26] p-4 rounded-xl border border-[#262a35]">
          <span className="font-mono text-[10px] text-[#bcc9cd] uppercase tracking-wider">
            Storage VFS Occupato
          </span>
          <div className="text-[22px] font-semibold text-[#dfe2f1] mt-1">{storageBytes == null ? '—' : formatBytes(storageBytes)}</div>
          <span className="font-mono text-[11px] text-[#10b981] mt-0.5">
            Dimensione su disco del database attivo
          </span>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-[#171b26] p-4 rounded-xl border border-[#262a35] flex flex-col sm:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-1.5 overflow-x-auto w-full sm:w-auto">
          {['all', 'pdf', 'markdown', 'yaml'].map((type) => (
            <button
              key={type}
              onClick={() => setFilterType(type)}
              className={`px-3 py-1.5 rounded-lg font-mono text-[11px] uppercase transition-all cursor-pointer ${
                filterType === type
                  ? 'bg-[#4cd7f6]/20 text-[#4cd7f6] font-semibold border border-[#4cd7f6]/40'
                  : 'text-[#bcc9cd] hover:text-[#dfe2f1] bg-[#0a0e18]'
              }`}
            >
              {type === 'all' ? 'Tutti i Tipi' : type}
            </button>
          ))}
        </div>

        <div className="relative w-full sm:w-72">
          <span className="material-symbols-outlined absolute left-3 top-2.5 text-[#bcc9cd] text-[18px]">
            search
          </span>
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Cerca nome documento..."
            className="w-full bg-[#0a0e18] text-[#dfe2f1] text-[12px] pl-9 pr-3 py-2 rounded-lg border border-[#262a35] focus:outline-none focus:ring-1 focus:ring-[#4cd7f6]"
          />
        </div>
      </div>

      {/* Documents Table */}
      <div className="bg-[#171b26] rounded-xl border border-[#262a35] overflow-hidden shadow-md">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[12px]">
            <thead className="bg-[#0a0e18] text-[#bcc9cd] font-mono text-[10px] uppercase tracking-wider border-b border-[#262a35]">
              <tr>
                <th className="py-3.5 px-4 font-semibold">Nome Documento</th>
                <th className="py-3.5 px-4 font-semibold">Formato</th>
                <th className="py-3.5 px-4 font-semibold">Peso</th>
                <th className="py-3.5 px-4 font-semibold">Chunks</th>
                <th className="py-3.5 px-4 font-semibold">Nodi Docling AST</th>
                <th className="py-3.5 px-4 font-semibold">Stato Indice</th>
                <th className="py-3.5 px-4 font-semibold">Data Ingest</th>
                <th className="py-3.5 px-4 font-semibold text-right">Azioni</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#262a35]">
              {filteredDocs.map((doc) => (
                <tr key={doc.id} className="hover:bg-[#1c1f2a]/60 transition-colors">
                  <td className="py-3.5 px-4">
                    <div className="flex items-center gap-2">
                      <span className="material-symbols-outlined text-[#4cd7f6] text-[18px]">
                        description
                      </span>
                      <span className="font-semibold text-[#dfe2f1] font-mono truncate max-w-xs sm:max-w-md">
                        {doc.name}
                      </span>
                    </div>
                  </td>
                  <td className="py-3.5 px-4 font-mono">
                    <span className="px-2 py-0.5 rounded text-[10px] bg-[#262a35] text-[#bcc9cd] border border-[#3d494c]/40">
                      {doc.type}
                    </span>
                  </td>
                  <td className="py-3.5 px-4 font-mono text-[#bcc9cd]">{doc.fileSize ?? '—'}</td>
                  <td className="py-3.5 px-4 font-mono text-[#4cd7f6] font-semibold">
                    {doc.chunksCount.toLocaleString()}
                  </td>
                  <td className="py-3.5 px-4 font-mono text-[#d0bcff]">
                    {doc.doclingAstNodes} nodi
                  </td>
                  <td className="py-3.5 px-4 font-mono">
                    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] bg-[#10b981]/15 text-[#10b981] border border-[#10b981]/30">
                      <span className="w-1.5 h-1.5 rounded-full bg-[#10b981]" />
                      {doc.status}
                    </span>
                  </td>
                  <td className="py-3.5 px-4 font-mono text-[#bcc9cd]">{doc.indexedDate || '—'}</td>
                  <td className="py-3.5 px-4 text-right">
                    <div className="flex items-center justify-end gap-2 font-mono">
                      <button
                        onClick={() => handleReindex(doc.id, doc.name)}
                        className="px-2.5 py-1 rounded bg-[#262a35] hover:bg-[#353944] text-[#dfe2f1] text-[11px] transition-colors border border-[#3d494c]/30 cursor-pointer"
                        title="Re-indicizza con Docling"
                      >
                        Re-index
                      </button>
                    </div>
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
