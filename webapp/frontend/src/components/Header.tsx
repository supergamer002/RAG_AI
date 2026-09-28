import { apiFetch, formatApiError } from '../api';
import React, { useState, useEffect } from 'react';
import { ThemeMode } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

interface HeaderProps {
  themeMode: ThemeMode;
  onToggleTheme: () => void;
  onOpenIngest: () => void;
  onOpenTerminal: () => void;
  onOpenDatabaseManager?: () => void;
  searchFilter: string;
  onSearchChange: (value: string) => void;
}

export const Header: React.FC<HeaderProps> = ({
  themeMode,
  onToggleTheme,
  onOpenIngest,
  onOpenTerminal,
  onOpenDatabaseManager,
  searchFilter,
  onSearchChange,
}) => {
  const [healthError, setHealthError] = useState<string | null>(null);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [notifications, setNotifications] = useState<Array<{ id: string; title: string; message: string; time: string; unread: boolean }>>([]);
  const [health, setHealth] = useState<{ fastapi: boolean; lancedb: boolean; ollama: boolean }>({
    fastapi: true,
    lancedb: true,
    ollama: false,
  });

  useEffect(() => {
    const checkHealth = () => {
      apiFetch(`/api/health`)
        .then((res) => res.ok ? res.json() : null)
        .then((data) => {
          if (data) {
            const nextHealth = {
              fastapi: !!data.fastapi,
              lancedb: !!data.lancedb,
              ollama: !!data.ollama,
            };
            setHealthError(null);
            setHealth((previous) => {
              const changedServices = [
                ['FastAPI', previous.fastapi, nextHealth.fastapi],
                ['LanceDB', previous.lancedb, nextHealth.lancedb],
                ['Ollama', previous.ollama, nextHealth.ollama],
              ].filter(([, oldValue, newValue]) => oldValue !== newValue);

              if (changedServices.length > 0) {
                const now = new Date().toLocaleTimeString();
                setNotifications((current) => [
                  ...changedServices.map(([service, , enabled]) => ({
                    id: `${service}-${Date.now()}-${enabled}`,
                    title: `${service} ${enabled ? 'online' : 'non disponibile'}`,
                    message: enabled
                      ? `${service} è tornato operativo.`
                      : `${service} non è attualmente disponibile.`,
                    time: now,
                    unread: true,
                  })),
                  ...current,
                ].slice(0, 20));
              }

              return nextHealth;
            });
          }
        })
        .catch((err) => {
          const message = formatApiError(err, 'Health check');
          setHealthError(message);
          setHealth((previous) => {
            if (previous.fastapi || previous.lancedb || previous.ollama) {
              setNotifications((current) => [{
                id: `backend-error-${Date.now()}`,
                title: 'Backend non raggiungibile',
                message,
                time: new Date().toLocaleTimeString(),
                unread: true,
              }, ...current].slice(0, 20));
            }
            return { fastapi: false, lancedb: false, ollama: false };
          });
        });
    };

    checkHealth();
    const interval = setInterval(checkHealth, 5000);
    return () => clearInterval(interval);
  }, []);

  const unreadCount = notifications.filter((notification) => notification.unread).length;

  const handleOpenNotifications = () => {
    setNotificationsOpen((open) => !open);
    setNotifications((current) => current.map((notification) => ({ ...notification, unread: false })));
  };

  const handleClearNotifications = () => {
    setNotifications([]);
    setNotificationsOpen(false);
  };

  return (
    <header className="fixed top-0 left-64 right-0 h-16 bg-[#0f131d]/85 backdrop-blur-xl z-40 border-b border-[#262a35]/60">
      <div className="h-16 w-full px-6 flex items-center justify-between gap-4">
        {/* Left Server Status Indicators */}
        <div className="flex items-center gap-2 overflow-x-auto py-1 scrollbar-none">
          {/* FastAPI */}
          <div className="flex items-center gap-1.5 bg-[#171b26] px-2.5 py-1.5 rounded-lg border border-[#06b6d4]/30 shadow-[0_0_12px_-4px_rgba(6,182,212,0.25)] shrink-0">
            <span className={`w-1.5 h-1.5 rounded-full ${health.fastapi ? 'bg-[#4cd7f6] animate-ping' : 'bg-[#ffb4ab]'}`} />
            <span className="font-mono text-[11px] text-[#bcc9cd]">FastAPI:</span>
            <span className={`font-mono text-[11px] font-semibold ${health.fastapi ? 'text-[#4cd7f6]' : 'text-[#ffb4ab]'}`}>
              {health.fastapi ? 'Online' : 'Offline'}
            </span>
          </div>

          {/* LanceDB */}
          <div className="flex items-center gap-1.5 bg-[#171b26] px-2.5 py-1.5 rounded-lg border border-[#262a35] shrink-0">
            <span className={`w-1.5 h-1.5 rounded-full ${health.lancedb ? 'bg-[#4cd7f6]' : 'bg-[#ffb4ab]'}`} />
            <span className="font-mono text-[11px] text-[#bcc9cd]">LanceDB:</span>
            <span className={`font-mono text-[11px] font-medium ${health.lancedb ? 'text-[#dfe2f1]' : 'text-[#ffb4ab]'}`}>
              {health.lancedb ? 'Connected' : 'Error'}
            </span>
          </div>

          {/* Ollama */}
          <div className="flex items-center gap-1.5 bg-[#171b26] px-2.5 py-1.5 rounded-lg border border-[#262a35] shrink-0">
            <span className={`w-1.5 h-1.5 rounded-full ${health.ollama ? 'bg-[#d0bcff]' : 'bg-[#ffb4ab]'}`} />
            <span className="font-mono text-[11px] text-[#bcc9cd]">Ollama:</span>
            <span className={`font-mono text-[11px] font-medium ${health.ollama ? 'text-[#d0bcff]' : 'text-[#ffb4ab]'}`}>
              {health.ollama ? 'Ready' : 'Standby'}
            </span>
          </div>

          {/* CrossEncoder */}
          <div className="hidden lg:flex items-center gap-1.5 bg-[#171b26] px-2.5 py-1.5 rounded-lg border border-[#262a35] shrink-0">
            <span className="w-1.5 h-1.5 rounded-full bg-[#869397]" />
            <span className="font-mono text-[11px] text-[#bcc9cd]">CrossEncoder:</span>
            <span className="font-mono text-[11px] text-[#869397]">Lazy Standby</span>
          </div>
        </div>

        {/* Right Controls */}
        <div className="flex items-center gap-3">
          {/* Search Box */}
          <div className="relative hidden md:flex items-center">
            <span className="material-symbols-outlined absolute left-3 text-[#bcc9cd] text-[18px]">
              search
            </span>
            <input
              type="text"
              value={searchFilter}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Filter chunks, nodes, or logs..."
              className="w-60 lg:w-72 bg-[#171b26] text-[#dfe2f1] placeholder:text-[#869397] text-[12px] pl-9 pr-3 py-1.5 rounded-lg border border-[#262a35] focus:outline-none focus:ring-1 focus:ring-[#4cd7f6] transition-all"
            />
            {searchFilter && (
              <button
                onClick={() => onSearchChange('')}
                className="absolute right-2 text-[#869397] hover:text-[#dfe2f1] text-[12px]"
              >
                ✕
              </button>
            )}
          </div>

          {/* Database Manager Trigger */}
          {onOpenDatabaseManager && (
            <button
              onClick={onOpenDatabaseManager}
              className="flex items-center gap-1.5 bg-[#262a35] hover:bg-[#353944] text-[#dfe2f1] px-3 py-1.5 rounded-lg text-[12px] font-medium transition-colors border border-[#3d494c]/40 cursor-pointer shadow-sm"
              title="Gestisci Database LanceDB"
            >
              <span className="material-symbols-outlined text-[16px] text-[#4cd7f6]">database</span>
              <span className="font-mono">Database</span>
            </button>
          )}

          {/* Direct Theme Toggle */}
          <button
            onClick={onToggleTheme}
            className="flex items-center gap-1.5 bg-[#262a35] hover:bg-[#353944] text-[#dfe2f1] px-3 py-1.5 rounded-lg text-[12px] font-medium transition-colors border border-[#3d494c]/40 cursor-pointer"
            title="Alterna Tema Scuro / Chiaro"
          >
            <span className="material-symbols-outlined text-[16px] text-[#4cd7f6]">
              {themeMode === 'light' ? 'dark_mode' : 'light_mode'}
            </span>
            <span className="hidden sm:inline font-mono">Tema</span>
          </button>

          {/* Quick Ingest Button */}
          <button
            onClick={onOpenIngest}
            className="flex items-center gap-1.5 bg-[#262a35] hover:bg-[#353944] text-[#dfe2f1] px-3 py-1.5 rounded-lg text-[12px] font-medium transition-colors border border-[#3d494c]/40 cursor-pointer shadow-sm"
          >
            <span className="material-symbols-outlined text-[16px] text-[#4cd7f6]">add</span>
            <span className="font-mono">Ingest</span>
          </button>

          {/* Icon Actions */}
          <div className="flex items-center gap-1">
            <button
              onClick={onOpenTerminal}
              className="w-8 h-8 rounded-lg bg-[#262a35] hover:bg-[#353944] text-[#bcc9cd] hover:text-[#dfe2f1] flex items-center justify-center transition-colors border border-[#3d494c]/30"
              title="Apri Telemetria & Log Terminale"
            >
              <span className="material-symbols-outlined text-[18px]">terminal</span>
            </button>
            <div className="relative">
              <button
                type="button"
                onClick={handleOpenNotifications}
                className="w-8 h-8 rounded-lg bg-[#262a35] hover:bg-[#353944] text-[#bcc9cd] hover:text-[#dfe2f1] flex items-center justify-center transition-colors border border-[#3d494c]/30 cursor-pointer"
                title="Apri notifiche runtime"
                aria-label="Apri notifiche runtime"
                aria-expanded={notificationsOpen}
              >
                <span className="material-symbols-outlined text-[18px]">
                  {unreadCount > 0 ? 'notifications' : 'notifications_none'}
                </span>
                {(unreadCount > 0 || healthError) && (
                  <span className="absolute -top-0.5 -right-0.5 min-w-[13px] h-[13px] px-0.5 rounded-full bg-[#ffb4ab] text-[#35100d] text-[8px] font-bold flex items-center justify-center">
                    {unreadCount > 9 ? '9+' : unreadCount || '!'}
                  </span>
                )}
              </button>

              {notificationsOpen && (
                <div className="absolute right-0 top-10 w-80 max-w-[calc(100vw-2rem)] rounded-xl border border-[#3d494c]/50 bg-[#171b26] shadow-2xl overflow-hidden z-50">
                  <div className="flex items-center justify-between px-4 py-3 border-b border-[#262a35]">
                    <div>
                      <div className="text-[12px] font-semibold text-[#dfe2f1]">Notifiche runtime</div>
                      <div className="text-[10px] font-mono text-[#869397]">{notifications.length} eventi</div>
                    </div>
                    <button
                      type="button"
                      onClick={handleClearNotifications}
                      className="text-[10px] font-mono text-[#869397] hover:text-[#dfe2f1] cursor-pointer"
                    >
                      Cancella
                    </button>
                  </div>

                  <div className="max-h-80 overflow-y-auto">
                    {notifications.length === 0 ? (
                      <div className="px-4 py-6 text-center text-[11px] text-[#869397]">
                        Nessuna nuova notifica.
                      </div>
                    ) : (
                      notifications.map((notification) => (
                        <div
                          key={notification.id}
                          className={`px-4 py-3 border-b border-[#262a35]/70 last:border-b-0 ${notification.unread ? 'bg-[#1c1f2a]' : ''}`}
                        >
                          <div className="flex items-start gap-2">
                            <span className="material-symbols-outlined text-[16px] text-[#4cd7f6] mt-0.5">
                              {notification.title.includes('non disponibile') || notification.title.includes('non raggiungibile') ? 'error' : 'notifications'}
                            </span>
                            <div className="min-w-0">
                              <div className="text-[11px] font-semibold text-[#dfe2f1]">{notification.title}</div>
                              <div className="text-[10px] leading-4 text-[#bcc9cd] mt-0.5">{notification.message}</div>
                              <div className="text-[9px] font-mono text-[#869397] mt-1">{notification.time}</div>
                            </div>
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Runtime status — deliberately non-interactive until a real identity provider exists */}
          <div
            className="w-8 h-8 rounded-full border border-[#3d494c]/60 bg-[#262a35] flex items-center justify-center"
            title={healthError || 'Stato runtime RAG'}
            aria-label="Stato runtime RAG"
          >
            <span className={`material-symbols-outlined text-[18px] ${health.fastapi ? 'text-[#4cd7f6]' : 'text-[#ffb4ab]'}`}>
              {health.fastapi ? 'hub' : 'cloud_off'}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
};
