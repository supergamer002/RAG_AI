export type NavPage = 
  | 'settings' 
  | 'query-workbench' 
  | 'knowledge-nodes' 
  | 'vector-explorer' 
  | 'pipeline-telemetry' 
  | 'evaluations';

export type ThemeMode = 'dark' | 'light' | 'system';
export type SettingsTab = 'runtime' | 'lancedb' | 'docling' | 'models' | 'security';

export interface AppSettings {
  // Theme
  themeMode: ThemeMode;
  
  // Runtime / FastAPI
  hostUrl: string;
  portNumber: number;
  workerConcurrency: number;
  logLevel: 'DEBUG' | 'INFO' | 'WARNING';
  corsOrigins: string;

  // LanceDB & Vectors
  storagePath: string;
  tableName: string;
  indexAlgorithm: 'IVF-PQ' | 'Flat' | 'HNSW';
  numCentroids: number;
  subVectorsPQ: number;
  distanceMetric: 'Cosine' | 'L2' | 'Dot';
  autoCompaction: boolean;

  // Ingestion & Docling
  chunkSize: number;
  chunkOverlap: number;
  ocrTablesExtraction: boolean;
  splitMode: 'ast' | 'fixed' | 'sentences';

  // Models & Endpoints
  ollamaUrl: string;
  embeddingModel: string;
  crossEncoderModel: string;
  keepAliveSeconds: number;
  topKCandidates: number;
  topNRerank: number;

  // API & Security
  apiToken: string;
  rateLimitMax: number;
  maxPayloadMB: number;
}

export interface ChunkItem {
  id: string;
  chunkNum: number;
  docTitle: string;
  docType: 'Libro' | 'Specifiche' | 'Manuale' | 'Codice' | 'Ricerca';
  section: string;
  text: string;
  highlightSnippet: string;
  denseScore: number;
  bm25Score: number;
  rerankScore: number;
  rankDelta: number;
  tokenCount: number;
  overlapPct: number;
  embeddingModel: string;
  dimensions: string;
  charOffset: string;
  timestamp: string;
  cluster: string;
  x?: number;
  y?: number;
}

export interface KnowledgeDocument {
  id: string;
  name: string;
  type: 'PDF' | 'Markdown' | 'DOCX' | 'Python' | 'YAML';
  fileSize: string;
  chunksCount: number;
  sectionsCount: number;
  status: 'Indicizzato' | 'In Elaborazione' | 'In Coda' | 'Verificato';
  indexedDate: string;
  vectorTable: string;
  embeddingDim: number;
  doclingAstNodes: number;
}

export interface TelemetryLog {
  id: string;
  timestamp: string;
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR';
  component: 'FastAPI' | 'LanceDB' | 'Ollama' | 'Docling' | 'CrossEncoder';
  message: string;
  durationMs?: number;
}

export interface EvalMetric {
  id: string;
  name: string;
  score: number;
  benchmarkTarget: number;
  description: string;
  delta: string;
}
