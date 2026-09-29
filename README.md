# RAG AI — versione semplificata

App per fare domande sui tuoi documenti (PDF, DOCX, TXT, MD…), risposte con fonti citate.
Un solo backend Python, nessuna configurazione: apri e usa.

## Requisiti
- **Python 3.10+**
- **[Ollama](https://ollama.com/download)** installato (i modelli si scaricano da soli al primo avvio)

## Avvio

**Windows:** doppio clic su `start.bat`
**Linux / macOS / WSL:** `./start.sh`

Lo script crea l'ambiente Python, installa le dipendenze e apre `http://localhost:8000` nel browser.
La prima volta l'app scarica in automatico i modelli necessari (qwen3:8b per le risposte,
qwen3-embedding:0.6b per la ricerca): un banner in alto mostra l'avanzamento.

## Uso
1. Usa `+` per singoli file oppure `▦` per un'intera cartella.
2. L'upload crea un job persistente: `In coda → In corso → Pronto/Parziale/Errore`.
3. La tab `Ingestion` mostra il flusso reale per il file corrente: `Estrazione → Segmentazione → Embedding → Salvataggio`, con percentuale della fase e avanzamento dei chunk.
4. Puoi continuare a chattare mentre l'ingest lavora in background.
5. Il pannello `Pronti` mostra i job completati; i documenti diventano ricercabili solo dopo l'indicizzazione.
6. I percorsi relativi delle cartelle vengono conservati, evitando collisioni tra file omonimi.
7. Le chat restano salvate a sinistra; puoi rinominarle o eliminarle.

Impostazioni (icona in basso a sinistra): modello di chat, modello di embedding, URL di Ollama,
numero di passaggi usati per rispondere, dimensione e sovrapposizione dei chunk. Se cambi il
modello di embedding, usa "Reindicizza" per aggiornare i documenti già caricati.

## Estrazione e segmentazione PDF
Per i PDF viene usato **PyMuPDF** invece di `pypdf`. L'estrattore analizza le dimensioni dei font e le righe ripetute di header/footer per riconoscere i marcatori `##H1##` e `##H2##`. La segmentazione usa prima la struttura del documento e, quando non è sufficientemente affidabile, una segmentazione semantica basata su TF-IDF/cosine similarity. Il chunker precedente resta come fallback se il segmentatore strutturale incontra un problema.

`fontTools` è incluso nelle dipendenze perché alcuni PDF tecnici usano font CFF Type1 e PyMuPDF può richiederlo per interpretarne correttamente la codifica.

## Dati
Tutto (documenti, embedding, conversazioni, impostazioni) è in un unico file `data/rag.db`
(SQLite), creato al primo avvio. Cancellalo per ripartire da zero.

## Sviluppo
```
pip install -r requirements-dev.txt
pytest
```
I test usano un Ollama simulato: non serve un'installazione reale per eseguirli.

## Cos'è cambiato rispetto alla versione precedente
Questa versione ibrida sostituisce l'architettura precedente (FastAPI + React separati,
LanceDB, docling, FlagEmbedding, reranking, avvio via WSL) con un singolo backend Python che
serve anche l'interfaccia web, usa SQLite invece di un database vettoriale dedicato e delega
interamente embedding e generazione a Ollama. È una base volutamente più semplice da far
girare, non un aggiornamento incrementale di `main`.
