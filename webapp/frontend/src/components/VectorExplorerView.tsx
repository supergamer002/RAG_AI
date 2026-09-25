import { apiFetch, apiJson, apiUrl, getApiToken, setApiToken } from '../api';
import React, { useState } from 'react';
import { ChunkItem } from '../types';

interface VectorExplorerViewProps {
  chunks: ChunkItem[];
  onInspectChunk: (chunk: ChunkItem) => void;
  onShowToast: (msg: string, isError?: boolean) => void;
  globalSearch?: string;
}

export const VectorExplorerView: React.FC<VectorExplorerViewProps> = ({
  chunks,
  onInspectChunk,
  onShowToast,
  globalSearch = '',
}) => {
  const [projection, setProjection] = useState<'UMAP' | 't-SNE' | 'PCA'>('UMAP');
  const [selectedCluster, setSelectedCluster] = useState<string>('all');
  const [hoveredChunk, setHoveredChunk] = useState<ChunkItem | null>(null);
  const [projectedPoints, setProjectedPoints] = useState<any[]>([]);
  const [vectorDimensions, setVectorDimensions] = useState<number | null>(null);

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

  const handleSelectAlgorithm = (alg: 'UMAP' | 't-SNE' | 'PCA') => {
    setProjection(alg);
    apiFetch(`/api/vectors/project`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ method: alg.toLowerCase() }),
    })
      .then((res) => {
        if (!res.ok) throw new Error('Errore nel calcolo della proiezione');
        return res.json();
      })
      .then((data) => {
        if (data && Array.isArray(data.points) && data.points.length > 0) {
          setProjectedPoints(data.points);
          setVectorDimensions(typeof data.dimensions === 'number' ? data.dimensions : null);
          onShowToast(`Proiezione vettoriale reale ${alg} calcolata per ${data.points.length} punti.`);
        } else {
          setProjectedPoints([]);
          setVectorDimensions(null);
          setHoveredChunk(null);
          onShowToast(`Nessuna proiezione disponibile per ${alg}.`, true);
        }
      })
      .catch((err) => {
        onShowToast(`Impossibile ricalcolare la proiezione: ${err.message}`, true);
      });
  };

  // Cluster membership is computed by KMeans and has no semantic name by itself.
  // Build the filter list only from clusters returned by the backend.
  const clusters = [
    { name: 'all', label: 'Tutti i Cluster', color: '#4cd7f6' },
    ...Array.from(new Set(projectedPoints.map((p) => p.cluster).filter(Boolean)))
      .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
      .map((name) => ({ name, label: name, color: getClusterColor(name) })),
  ];

  // Show only coordinates returned by the backend. Never synthesize fallback points.
  const scatterPoints = projectedPoints.map((p, idx) => ({
    ...(chunks[idx % Math.max(chunks.length, 1)] ?? {}),
    id: p.id,
    docTitle: p.title,
    section: p.section,
    cluster: p.cluster,
    x: p.x,
    y: p.y,
  })) as ChunkItem[];

  const visibleScatterPoints = scatterPoints.filter((point) => {
    const term = globalSearch.trim().toLowerCase();
    if (!term) return true;
    return [point.id, point.docTitle, point.section, point.cluster].some((value) =>
      String(value ?? '').toLowerCase().includes(term)
    );
  });

  const getClusterColor = (clusterName: string) => {
    const palette = ['#4cd7f6', '#6366f1', '#d0bcff', '#10b981', '#f59e0b', '#f472b6'];
    const match = clusterName.match(/Cluster\s+(\d+)/i);
    const index = match ? Number(match[1]) : 0;
    return palette[index % palette.length];
  };

  return (
    <div className="p-6 flex flex-col gap-6 max-w-[1600px] mx-auto w-full relative z-10">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-[#171b26] p-6 rounded-xl border border-[#262a35] shadow-lg">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-[#262a35] flex items-center justify-center text-[#4cd7f6] shadow-[0_0_24px_rgba(76,215,246,0.25)] border border-[#3d494c]/50">
            <span className="material-symbols-outlined text-[28px]">scatter_plot</span>
          </div>
          <div className="flex flex-col">
            <div className="flex items-center gap-1.5 font-mono text-[11px] text-[#4cd7f6] uppercase tracking-wider">
              <span>Embedding Space Dimensionality Reduction</span>
              <span>•</span>
              <span className="text-[#bcc9cd]">{vectorDimensions == null ? '—' : `${vectorDimensions}_DIM`} → 2D</span>
            </div>
            <h1 className="text-[24px] sm:text-[28px] text-[#dfe2f1] tracking-tight font-semibold">
              Vector Space Explorer
            </h1>
            <p className="text-[13px] text-[#bcc9cd]">
              Esplora la topologia geometrica e i cluster semantici proiettati in 2D tramite UMAP / t-SNE / PCA.
            </p>
          </div>
        </div>

        {/* Algorithm Switcher */}
        <div className="flex items-center gap-1 bg-[#0a0e18] p-1 rounded-lg border border-[#262a35]">
          {(['UMAP', 't-SNE', 'PCA'] as const).map((alg) => (
            <button
              key={alg}
              onClick={() => handleSelectAlgorithm(alg)}
              className={`px-3 py-1.5 rounded font-mono text-[11px] transition-all cursor-pointer ${
                projection === alg
                  ? 'bg-[#4cd7f6]/20 text-[#4cd7f6] font-semibold border border-[#4cd7f6]/40'
                  : 'text-[#bcc9cd] hover:text-[#dfe2f1]'
              }`}
            >
              {alg}
            </button>
          ))}
        </div>
      </div>

      {/* Cluster Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[11px] text-[#bcc9cd]">Cluster KMeans:</span>
        {clusters.map((c) => {
          const isActive = selectedCluster === c.name;
          return (
            <button
              key={c.name}
              onClick={() => setSelectedCluster(c.name)}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-lg font-mono text-[11px] transition-all cursor-pointer border ${
                isActive
                  ? 'bg-[#1c1f2a] text-[#dfe2f1] border-[#4cd7f6]'
                  : 'bg-[#171b26] text-[#bcc9cd] hover:text-[#dfe2f1] border-[#262a35]'
              }`}
            >
              {c.color && (
                <span className="w-2 h-2 rounded-full" style={{ backgroundColor: c.color }} />
              )}
              <span>{c.label}</span>
            </button>
          );
        })}
      </div>

      {/* Visual Vector Canvas & Info Card */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Canvas Area (Col-8) */}
        <div className="lg:col-span-8 bg-[#171b26] p-6 rounded-xl border border-[#262a35] shadow-lg flex flex-col gap-4 relative">
          <div className="flex items-center justify-between text-[11px] font-mono text-[#bcc9cd]">
            <span>Metrica di Distanza: Cosine Similarity [1 - cos(θ)]</span>
            <span>{projectedPoints.length.toLocaleString()} Vettori Proiettati</span>
          </div>

          {/* Scatter Plot 2D Box */}
          <div className="w-full h-[450px] bg-[#0a0e18] rounded-lg border border-[#262a35] relative overflow-hidden flex items-center justify-center p-6">
            {/* Background Grid Lines */}
            <div
              className="absolute inset-0 opacity-15 pointer-events-none"
              style={{
                backgroundImage:
                  'linear-gradient(to right, #4cd7f6 1px, transparent 1px), linear-gradient(to bottom, #4cd7f6 1px, transparent 1px)',
                backgroundSize: '40px 40px',
              }}
            />

            {/* Central Axis crosshair */}
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none opacity-20">
              <div className="w-full h-px bg-[#4cd7f6]" />
              <div className="h-full w-px bg-[#4cd7f6] absolute" />
            </div>

            {/* Scatter Points */}
            {scatterPoints.length === 0 ? (
              <div className="relative z-10 flex max-w-md flex-col items-center gap-2 text-center font-mono">
                <span className="material-symbols-outlined text-[34px] text-[#4cd7f6]">scatter_plot</span>
                <span className="text-[13px] font-semibold text-[#dfe2f1]">Nessuna proiezione reale disponibile</span>
                <span className="text-[11px] leading-relaxed text-[#bcc9cd]">
                  Seleziona UMAP, t-SNE o PCA per calcolare una nuova proiezione dei vettori.
                </span>
              </div>
            ) : (
              scatterPoints
                .filter((p) => selectedCluster === 'all' || p.cluster === selectedCluster)
                .map((point) => {
                const color = getClusterColor(point.cluster);
                const isHovered = hoveredChunk?.id === point.id;
                return (
                  <div
                    key={point.id}
                    onMouseEnter={() => setHoveredChunk(point as ChunkItem)}
                    onClick={() => onInspectChunk(point as ChunkItem)}
                    className="absolute cursor-pointer transition-transform duration-200 group"
                    style={{
                      left: `${point.x ?? 50}%`,
                      top: `${point.y ?? 50}%`,
                      transform: 'translate(-50%, -50%)',
                    }}
                  >
                    {/* Pulsing ring on hover */}
                    {isHovered && (
                      <div
                        className="absolute -inset-2 rounded-full animate-ping opacity-75"
                        style={{ backgroundColor: color }}
                      />
                    )}
                    <div
                      className={`w-3.5 h-3.5 rounded-full border-2 border-[#0a0e18] shadow-md transition-all ${
                        isHovered ? 'scale-150 ring-2 ring-white' : 'hover:scale-125'
                      }`}
                      style={{ backgroundColor: color }}
                    />
                    <span className="hidden group-hover:block absolute left-4 top-0 bg-[#171b26] text-[#dfe2f1] font-mono text-[10px] px-2 py-0.5 rounded border border-[#262a35] whitespace-nowrap z-30 shadow-xl">
                      #{point.chunkNum} • {point.docTitle.slice(0, 20)}...
                    </span>
                  </div>
                );
              })
            )}
          </div>

          <div className="flex items-center justify-between font-mono text-[11px] text-[#bcc9cd]">
            <span>💡 Clicca su un nodo per aprire l&apos;ispettore dettagliato del chunk.</span>
            <span>Risoluzione Spaziale: Voronoi 256</span>
          </div>
        </div>

        {/* Selected / Hovered Node Inspector (Col-4) */}
        <div className="lg:col-span-4 bg-[#171b26] p-6 rounded-xl border border-[#262a35] shadow-lg flex flex-col gap-4">
          <div className="flex items-center gap-2 pb-3 border-b border-[#262a35]">
            <span className="material-symbols-outlined text-[#4cd7f6] text-[20px]">
              fingerprint
            </span>
            <span className="text-[15px] text-[#dfe2f1] font-semibold">
              Proprietà Nodo Vettoriale
            </span>
          </div>

          {hoveredChunk ? (
            <div className="flex flex-col gap-3 font-mono text-[12px]">
              <div className="flex items-center justify-between">
                <span className="text-[#bcc9cd]">Chunk ID:</span>
                <span className="text-[#4cd7f6] font-bold">#{hoveredChunk.chunkNum}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#bcc9cd]">Documento:</span>
                <span className="text-[#dfe2f1] truncate max-w-[180px]">
                  {hoveredChunk.docTitle}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#bcc9cd]">Cluster:</span>
                <span
                  className="px-2 py-0.5 rounded text-[10px]"
                  style={{
                    backgroundColor: `${getClusterColor(hoveredChunk.cluster)}20`,
                    color: getClusterColor(hoveredChunk.cluster),
                  }}
                >
                  {hoveredChunk.cluster}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#bcc9cd]">Coordinate Proiettate:</span>
                <span className="text-[#d0bcff]">
                  [{hoveredChunk.x}, {hoveredChunk.y}]
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#bcc9cd]">Rerank Score:</span>
                <span className="text-[#4cd7f6] font-bold">
                  {hoveredChunk.rerankScore.toFixed(3)}
                </span>
              </div>

              <div className="mt-2 bg-[#0a0e18] p-3 rounded-lg border border-[#262a35] flex flex-col gap-1.5">
                <span className="text-[10px] text-[#bcc9cd] uppercase tracking-wider font-semibold">
                  Estratto Testo:
                </span>
                <p className="text-[11px] text-[#dfe2f1] line-clamp-4 leading-relaxed font-sans">
                  {hoveredChunk.text}
                </p>
              </div>

              <button
                onClick={() => onInspectChunk(hoveredChunk)}
                className="mt-2 w-full py-2 bg-[#4cd7f6] hover:bg-[#06b6d4] text-[#003640] rounded-lg font-semibold font-mono text-[12px] transition-colors cursor-pointer"
              >
                Apri Ispettore Completo
              </button>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-16 text-center text-[#bcc9cd] font-mono text-[12px]">
              <span className="material-symbols-outlined text-[36px] text-[#869397] mb-2 opacity-50">
                touch_app
              </span>
              <span>Passa il mouse su un punto per visualizzarne le coordinate e i metadati.</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
