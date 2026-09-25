import { apiFetch, apiJson, apiUrl, getApiToken, setApiToken } from '../api';
import React, { useState, useEffect } from 'react';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

interface DatabaseItem {
  id: string;
  name: string;
  path: string;
  createdAt: string;
  updatedAt: string;
  embeddingModel: string;
  dimension: number;
}

interface DatabaseManagerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onShowToast: (msg: string, isError?: boolean) => void;
  onDatabaseChanged?: () => void;
}

export const DatabaseManagerModal: React.FC<DatabaseManagerModalProps> = ({
  isOpen,
  onClose,
  onShowToast,
  onDatabaseChanged,
}) => {
  const [databases, setDatabases] = useState<DatabaseItem[]>([]);
  const [activeDbId, setActiveDbId] = useState<string>('default');
  const [newDbName, setNewDbName] = useState<string>('');
  const [isCreating, setIsCreating] = useState(false);

  const fetchDatabases = () => {
    apiFetch(`/api/databases`)
      .then((res) => res.ok ? res.json() : null)
      .then((data) => {
        if (data) {
          setActiveDbId(data.activeDatabase);
          setDatabases(data.databases || []);
        }
      })
      .catch(() => {});
  };

  useEffect(() => {
    if (isOpen) {
      fetchDatabases();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleCreateDatabase = () => {
    if (!newDbName.trim()) return;
    setIsCreating(true);

    apiFetch(`/api/databases`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: newDbName.trim() }),
    })
      .then((res) => {
        if (!res.ok) throw new Error('Errore durante la creazione');
        return res.json();
      })
      .then((data) => {
        setIsCreating(false);
        setNewDbName('');
        onShowToast(`Database "${data.name}" creato con successo!`);
        fetchDatabases();
      })
      .catch((err) => {
        setIsCreating(false);
        onShowToast(`Impossibile creare il database: ${err.message}`, true);
      });
  };

  const handleActivate = (dbId: string, name: string) => {
    apiFetch(`/api/databases/${dbId}/activate`, {
      method: 'POST',
    })
      .then((res) => {
        if (!res.ok) throw new Error('Errore attivazione');
        return res.json();
      })
      .then(() => {
        setActiveDbId(dbId);
        onShowToast(`Database attivo cambiato in "${name}"!`);
        fetchDatabases();
        if (onDatabaseChanged) onDatabaseChanged();
      })
      .catch((err) => {
        onShowToast(`Errore durante l'attivazione: ${err.message}`, true);
      });
  };

  const handleRename = (dbId: string, currentName: string) => {
    const updated = prompt('Nuovo nome per il database:', currentName);
    if (!updated || !updated.trim() || updated.trim() === currentName) return;

    apiFetch(`/api/databases/${dbId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: updated.trim() }),
    })
      .then((res) => {
        if (!res.ok) throw new Error('Errore durante la rinomina');
        return res.json();
      })
      .then((data) => {
        onShowToast(`Database rinominato in "${data.name}".`);
        fetchDatabases();
      })
      .catch((err) => {
        onShowToast(`Impossibile rinominare: ${err.message}`, true);
      });
  };

  const handleExport = async (dbId: string, name: string) => {
    try {
      const res = await apiFetch(`/api/databases/${dbId}/export`);
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || `HTTP ${res.status}`);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `database_${dbId}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      onShowToast(`Database "${name}" esportato.`);
    } catch (err) {
      onShowToast(`Impossibile esportare: ${err instanceof Error ? err.message : 'errore sconosciuto'}`, true);
    }
  };

  const handleImportFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || !e.target.files[0]) return;
    const file = e.target.files[0];
    const chosenName = prompt('Nome del database importato:', file.name.replace(/\.zip$/i, ''));
    if (!chosenName || !chosenName.trim()) {
      e.target.value = '';
      return;
    }
    const formData = new FormData();
    formData.append('file', file);
    formData.append('name', chosenName.trim());

    apiFetch(`/api/databases/import`, {
      method: 'POST',
      body: formData,
    })
      .then((res) => {
        if (!res.ok) throw new Error('Errore durante l\'importazione');
        return res.json();
      })
      .then((data) => {
        onShowToast(`Database "${data.name}" importato con successo!`);
        fetchDatabases();
      })
      .catch((err) => {
        onShowToast(`Impossibile importare: ${err.message}`, true);
      });
  };

  const handleDelete = (dbId: string, name: string) => {
    if (!confirm(`Sei sicuro di voler eliminare il database "${name}"?`)) return;

    apiFetch(`/api/databases/${dbId}`, {
      method: 'DELETE',
    })
      .then((res) => {
        if (!res.ok) throw new Error('Errore eliminazione');
        return res.json();
      })
      .then(() => {
        onShowToast(`Database "${name}" eliminato.`);
        fetchDatabases();
      })
      .catch((err) => {
        onShowToast(`Impossibile eliminare: ${err.message}`, true);
      });
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#0f131d]/85 backdrop-blur-xl"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="relative w-full max-w-2xl bg-[#171b26] rounded-xl border border-[#262a35] shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="p-5 bg-[#0a0e18] flex items-center justify-between border-b border-[#262a35]">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#262a35] flex items-center justify-center text-[#4cd7f6] border border-[#3d494c]/40">
              <span className="material-symbols-outlined text-[20px]">database</span>
            </div>
            <div>
              <h2 className="text-[16px] text-[#dfe2f1] font-semibold">
                Gestione Multi-Database LanceDB
              </h2>
              <span className="font-mono text-[11px] text-[#bcc9cd]">
                Ambienti Vettoriali e Store Indipendenti
              </span>
            </div>
          </div>

          <button
            onClick={onClose}
            className="text-[#bcc9cd] hover:text-[#dfe2f1] p-1 rounded transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="p-6 flex flex-col gap-5 max-h-[70vh] overflow-y-auto">
          {/* Create New DB Bar & Import Trigger */}
          <div className="flex flex-col sm:flex-row items-center gap-2 bg-[#0a0e18] p-3 rounded-lg border border-[#262a35]">
            <input
              type="text"
              value={newDbName}
              onChange={(e) => setNewDbName(e.target.value)}
              placeholder="Nome del nuovo database (es. Ingegneria Chimica)..."
              className="flex-1 bg-[#171b26] text-[#dfe2f1] text-[13px] px-3 py-2 rounded-lg border border-[#262a35] focus:outline-none focus:ring-1 focus:ring-[#4cd7f6] font-mono w-full"
            />
            <div className="flex items-center gap-2 shrink-0">
              <button
                onClick={handleCreateDatabase}
                disabled={isCreating || !newDbName.trim()}
                className="px-4 py-2 bg-[#4cd7f6] hover:bg-[#06b6d4] text-[#003640] font-semibold text-[12px] rounded-lg font-mono transition-all cursor-pointer disabled:opacity-50"
              >
                + Nuovo
              </button>
              <label className="px-3 py-2 bg-[#262a35] hover:bg-[#353944] text-[#dfe2f1] font-semibold text-[12px] rounded-lg font-mono transition-all cursor-pointer border border-[#3d494c]/40">
                Importa .zip
                <input
                  type="file"
                  accept=".zip"
                  onChange={handleImportFile}
                  className="hidden"
                />
              </label>
            </div>
          </div>

          {/* Database List */}
          <div className="flex flex-col gap-3">
            {databases.map((db) => {
              const isActive = db.id === activeDbId;
              return (
                <div
                  key={db.id}
                  className={`p-4 rounded-xl border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 transition-all ${
                    isActive
                      ? 'bg-[#06b6d4]/10 border-[#4cd7f6]/50 shadow-[0_0_16px_-4px_rgba(76,215,246,0.3)]'
                      : 'bg-[#0a0e18] border-[#262a35]'
                  }`}
                >
                  <div className="flex flex-col gap-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-[#dfe2f1] text-[14px]">
                        {db.name}
                      </span>
                      {isActive && (
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-[#10b981]/20 text-[#10b981] border border-[#10b981]/40 uppercase font-bold">
                          Attivo
                        </span>
                      )}
                    </div>
                    <span className="font-mono text-[11px] text-[#bcc9cd] truncate">
                      Modello: {db.embeddingModel} ({db.dimension}d) • Creato: {db.createdAt}
                    </span>
                  </div>

                  <div className="flex items-center gap-2 font-mono shrink-0">
                    {!isActive && (
                      <button
                        onClick={() => handleActivate(db.id, db.name)}
                        className="px-3 py-1.5 bg-[#262a35] hover:bg-[#4cd7f6] text-[#dfe2f1] hover:text-[#003640] text-[11px] rounded font-semibold transition-colors border border-[#3d494c]/40 cursor-pointer"
                      >
                        Attiva
                      </button>
                    )}
                    <button
                      onClick={() => handleRename(db.id, db.name)}
                      className="px-2.5 py-1.5 bg-[#262a35] hover:bg-[#353944] text-[#bcc9cd] hover:text-[#dfe2f1] text-[11px] rounded transition-colors border border-[#3d494c]/40 cursor-pointer"
                      title="Rinomina database"
                    >
                      Rinomina
                    </button>
                    <button
                      onClick={() => handleExport(db.id, db.name)}
                      className="px-2.5 py-1.5 bg-[#262a35] hover:bg-[#353944] text-[#c0c1ff] hover:text-[#dfe2f1] text-[11px] rounded transition-colors border border-[#3d494c]/40 cursor-pointer"
                      title="Esporta database in ZIP"
                    >
                      Esporta
                    </button>
                    {!isActive && databases.length > 1 && (
                      <button
                        onClick={() => handleDelete(db.id, db.name)}
                        className="px-2.5 py-1.5 bg-[#ffb4ab]/15 hover:bg-[#ffb4ab]/30 text-[#ffb4ab] text-[11px] rounded transition-colors border border-[#ffb4ab]/30 cursor-pointer"
                        title="Elimina database"
                      >
                        ✕
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 bg-[#0a0e18] flex items-center justify-end border-t border-[#262a35]">
          <button
            onClick={onClose}
            className="px-5 py-2 bg-[#1c1f2a] hover:bg-[#262a35] text-[#dfe2f1] font-mono text-[12px] rounded-lg transition-colors cursor-pointer"
          >
            Chiudi
          </button>
        </div>
      </div>
    </div>
  );
};
