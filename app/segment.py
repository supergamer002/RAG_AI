from __future__ import annotations

import json
import re
from pathlib import Path
import numpy as np


try:
    from .config import ExtractConfig
except ImportError:  # standalone smoke-test
    class ExtractConfig:  # type: ignore[no-redef]
        pass

HEADING_RE = re.compile(r"^##H([1-3])##\s*(.+)$")
PAGINA_RE = re.compile(r"^=== PAGINA \d+ ===$")
# Più permissiva dell'implementazione precedente: conserva anche frasi lunghe
# e usa la punteggiatura forte come primo candidato, senza imporre 60 parole/frase.
SENTENCE_END_RE = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÀ-ÖØ-Þ0-9(\"'])")

MIN_PAROLE_DEFAULT = 300
MAX_PAROLE_DEFAULT = 1500
MIN_PAROLE_UNITA_VALIDA = 60
DENSITA_MIN_PAROLE_PER_TITOLO = 2500

# Per i transcript: dimensione nominale dei blocchi e finestre di contesto.
SEMANTIC_BLOCK_WORDS = 70
SEMANTIC_WINDOW_BLOCKS = 2
SEMANTIC_MIN_WORDS = 150
SEMANTIC_TARGET_WORDS = 600
SEMANTIC_MAX_WORDS = MAX_PAROLE_DEFAULT

# Segnali discorsivi: non creano da soli un confine, ma lo rendono più probabile.
BOUNDARY_MARKERS = [
    # italiano
    r"\bora\s+(?:passiamo|vediamo|consideriamo|parliamo|analizziamo)\b",
    r"\badesso\s+(?:passiamo|vediamo|consideriamo|parliamo|analizziamo)\b",
    r"\bpassiamo\s+(?:a|al|alla|alle|agli|ai|ad)\b",
    r"\bvediamo\s+(?:ora|adesso|un altro|il prossimo|come)\b",
    r"\bconsideriamo\s+(?:ora|adesso|un altro|il caso)\b",
    r"\bun altro esempio\b",
    r"\bun altro aspetto\b",
    r"\ba questo punto\b",
    r"\bper concludere\b",
    r"\bin conclusione\b",
    r"\bin sintesi\b",
    # inglese
    r"\bnow\s+(?:let'?s|we)\b",
    r"\blet'?s\s+(?:move on|look at|consider|turn to)\b",
    r"\bnext\b",
    r"\banother example\b",
    r"\banother aspect\b",
    r"\bat this point\b",
    r"\bto summarize\b",
    r"\bin conclusion\b",
    r"\bfinally\b",
]

OUTRO_MARKERS = [
    r"\biscriviti\b",
    r"\biscrivetevi\b",
    r"\bsubscribe\b",
    r"\bseguimi\b",
    r"\bfollow (?:me|us)\b",
    r"\bmetti (?:un )?like\b",
    r"\blike (?:e|and) condividi\b",
    r"\blike and share\b",
    r"\battiva(?:te)?\s+(?:la )?campanell[ao]\b",
    r"\bring the bell\b",
    r"\bsupport(?:a|ate)?\s+(?:il|la|my|our)\b",
    r"\bsupport the channel\b",
    r"\bsostieni\b",
    r"\bci vediamo nel prossimo video\b",
    r"\bsee you in the next video\b",
    r"\bgrazie per aver guardato\b",
    r"\bthanks for watching\b",
]

_BOUNDARY_PATTERNS = [re.compile(p, re.I) for p in BOUNDARY_MARKERS]
_OUTRO_PATTERNS = [re.compile(p, re.I) for p in OUTRO_MARKERS]


def _parse_nodi(testo: str) -> list[dict]:
    righe = testo.split("\n")
    nodi: list[dict] = []
    corrente = {"livello": None, "titolo": None, "righe": []}
    for riga in righe:
        riga_pulita = riga.strip()
        if PAGINA_RE.match(riga_pulita):
            continue
        m = HEADING_RE.match(riga_pulita)
        if m:
            if corrente["righe"] or corrente["titolo"]:
                nodi.append(corrente)
            corrente = {
                "livello": int(m.group(1)),
                "titolo": m.group(2).strip(),
                "righe": [],
            }
        else:
            corrente["righe"].append(riga)
    if corrente["righe"] or corrente["titolo"]:
        nodi.append(corrente)
    return nodi


def segmenta_strutturato(
    testo: str,
    min_parole: int = MIN_PAROLE_DEFAULT,
    max_parole: int = MAX_PAROLE_DEFAULT,
) -> list[dict]:
    """Usa i titoli come ossatura e segmenta semanticamente solo quando serve.

    Compatibilità: restituisce sempre record con almeno ``titolo`` e ``testo``.
    A differenza della versione precedente, non chiude una sezione solo perché
    ha raggiunto min_parole: una sezione H2/H3 coerente resta unita fino al
    successivo cambio strutturale, salvo superamento del massimo.
    """
    nodi = _parse_nodi(testo)
    if not nodi:
        return []

    unita: list[dict] = []
    current: dict | None = None

    def flush() -> None:
        nonlocal current
        if current and current["testo"].strip():
            unita.append({"titolo": current["titolo"], "testo": current["testo"].strip()})
        current = None

    for nodo in nodi:
        testo_nodo = "\n".join(nodo["righe"]).strip()
        titolo = nodo["titolo"]
        if not titolo and not testo_nodo:
            continue

        # Ogni heading esplicito è un confine preferenziale. Se è un H1 dopo
        # contenuto precedente, chiudiamo sempre; gli H2/H3 diventano invece
        # parte dell'ossatura corrente solo quando la sezione è piccola.
        if nodo["livello"] == 1 and current and current["testo"].strip():
            flush()
        elif current and current["testo"].strip():
            parole_correnti = len(current["testo"].split())
            if parole_correnti >= min_parole:
                flush()

        pezzo = (f"{titolo}\n" if titolo else "") + testo_nodo
        if current is None:
            current = {"titolo": titolo, "testo": pezzo}
        else:
            nuovo = (current["testo"] + "\n" + pezzo).strip()
            if len(nuovo.split()) <= max_parole:
                current["testo"] = nuovo
            else:
                flush()
                current = {"titolo": titolo, "testo": pezzo}

    flush()

    # Una sezione strutturata molto lunga viene ulteriormente divisa, ma
    # conserva il suo titolo per permettere alle fasi successive di usarlo.
    risultato: list[dict] = []
    for u in unita:
        if len(u["testo"].split()) > max_parole:
            for sub in segmenta_semantico(
                u["testo"],
                min_parole=min_parole,
                target_parole=min(SEMANTIC_TARGET_WORDS, max_parole),
            ):
                risultato.append({"titolo": u["titolo"], "testo": sub["testo"]})
        else:
            risultato.append(u)
    return risultato


def ha_marcatori(testo: str) -> bool:
    return any(HEADING_RE.match(riga.strip()) for riga in testo.split("\n"))


def densita_titoli_sufficiente(testo: str) -> bool:
    n_marcatori = sum(1 for riga in testo.split("\n") if HEADING_RE.match(riga.strip()))
    n_parole = len(testo.split())
    if n_marcatori == 0:
        return False
    return (n_parole / n_marcatori) <= DENSITA_MIN_PAROLE_PER_TITOLO


def _metadati_unita(testo: str, ha_titolo: bool) -> dict:
    n_parole = len(testo.split())
    n_caratteri = len(testo)
    alfabetici = len(re.findall(r"[A-Za-zÀ-ÿ]", testo))
    n_formule = len(re.findall(r"\[FORMULA[^\]]*\]", testo))
    return {
        "n_parole": n_parole,
        "ha_titolo": ha_titolo,
        "rapporto_alfabetico": round(alfabetici / n_caratteri, 3) if n_caratteri else 0.0,
        "densita_formule": round(n_formule / max(1, n_parole), 4),
    }


def _applica_soglia_minima(unita: list[dict], min_parole: int = MIN_PAROLE_UNITA_VALIDA) -> list[dict]:
    """Fonde i frammenti residui al vicino più adatto, evitando mutazioni in-place."""
    if not unita:
        return unita
    risultato: list[dict] = []
    for u in unita:
        copia = dict(u)
        if len(copia["testo"].split()) < min_parole and risultato:
            # Conserva il titolo del segmento principale; il frammento breve
            # resta comunque dentro il contenuto.
            risultato[-1]["testo"] += "\n" + copia["testo"]
        else:
            risultato.append(copia)
    if risultato and len(risultato[0]["testo"].split()) < min_parole and len(risultato) > 1:
        primo = risultato.pop(0)
        risultato[0]["testo"] = primo["testo"] + "\n" + risultato[0]["testo"]
    return risultato


# ---------------------------------------------------------------------------
# Percorso B — trascrizioni senza struttura tipografica
# ---------------------------------------------------------------------------

def _split_frasi(testo: str) -> list[str]:
    """Split robusto: preferisce frasi reali, ma crea fallback per ASR povero."""
    testo = re.sub(r"\s+", " ", testo).strip()
    if not testo:
        return []

    frasi = [f.strip() for f in SENTENCE_END_RE.split(testo) if f.strip()]
    # Se la punteggiatura non produce sufficiente granularità, spezziamo le
    # frasi lunghe sui segni deboli e infine in finestre di circa 35 parole.
    espanse: list[str] = []
    for frase in frasi:
        parole = frase.split()
        if len(parole) <= 45:
            espanse.append(frase)
            continue
        parti = re.split(r"(?<=[,;:])\s+", frase)
        if len(parti) > 1:
            buffer: list[str] = []
            n = 0
            for parte in parti:
                buffer.append(parte)
                n += len(parte.split())
                if n >= 25:
                    espanse.append(" ".join(buffer).strip())
                    buffer, n = [], 0
            if buffer:
                espanse.append(" ".join(buffer).strip())
            continue
        for i in range(0, len(parole), 35):
            espanse.append(" ".join(parole[i:i + 35]))
    return espanse


def _blocchi(frasi: list[str], block_size: int = 4) -> list[str]:
    """Compatibilità con il vecchio helper: block_size resta interpretabile."""
    return [" ".join(frasi[i:i + block_size]) for i in range(0, len(frasi), block_size)]


def _blocchi_per_parole(frasi: list[str], target_words: int = SEMANTIC_BLOCK_WORDS) -> list[str]:
    blocchi: list[str] = []
    corrente: list[str] = []
    n = 0
    for frase in frasi:
        corrente.append(frase)
        n += len(frase.split())
        if n >= target_words:
            blocchi.append(" ".join(corrente))
            corrente, n = [], 0
    if corrente:
        blocchi.append(" ".join(corrente))
    return blocchi


def _tokenizza_tfidf(testo: str) -> list[str]:
    """Tokenizzazione leggera, senza dipendenze SciPy/scikit-learn."""
    return re.findall(r"(?u)\b\w[\w'’-]*\b", testo.lower())


def _tfidf_matrix(documenti: list[str]) -> np.ndarray:
    """TF-IDF denso per piccoli insiemi di blocchi.

    Questa implementazione sostituisce TfidfVectorizer: per la segmentazione
    lavoriamo su poche decine di blocchi alla volta, quindi una matrice densa
    NumPy è sufficiente e soprattutto evita la dipendenza da SciPy.
    """
    if not documenti:
        return np.empty((0, 0), dtype=np.float32)
    token_docs = [_tokenizza_tfidf(d) for d in documenti]
    vocab: dict[str, int] = {}
    for tokens in token_docs:
        for token in tokens:
            if token not in vocab:
                vocab[token] = len(vocab)
    if not vocab:
        return np.zeros((len(documenti), 0), dtype=np.float32)

    n_docs = len(documenti)
    df = np.zeros(len(vocab), dtype=np.int32)
    rows: list[dict[int, int]] = []
    for tokens in token_docs:
        counts: dict[int, int] = {}
        for token in tokens:
            idx = vocab[token]
            counts[idx] = counts.get(idx, 0) + 1
        rows.append(counts)
        for idx in counts:
            df[idx] += 1

    # Smooth IDF e sublinear TF, equivalenti alle impostazioni rilevanti
    # usate precedentemente per questo caso d'uso.
    idf = np.log((1.0 + n_docs) / (1.0 + df)) + 1.0
    mat = np.zeros((n_docs, len(vocab)), dtype=np.float32)
    for row_idx, counts in enumerate(rows):
        for col_idx, count in counts.items():
            mat[row_idx, col_idx] = (1.0 + np.log(count)) * idf[col_idx]
        norm = np.linalg.norm(mat[row_idx])
        if norm > 0:
            mat[row_idx] /= norm
    return mat


def _cosine_rows(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Cosine similarity tra una riga e una o più righe già normalizzate."""
    if left.size == 0 or right.size == 0:
        return np.zeros(right.shape[0], dtype=np.float32)
    lnorm = np.linalg.norm(left)
    if lnorm == 0:
        return np.zeros(right.shape[0], dtype=np.float32)
    rnorm = np.linalg.norm(right, axis=1)
    denom = np.maximum(lnorm * rnorm, 1e-12)
    return (right @ left) / denom


def _punteggi_confine(blocchi: list[str]) -> list[float]:
    """Similarità locale tra blocchi, senza dipendenze SciPy."""
    if len(blocchi) < 2:
        return []
    vec = _tfidf_matrix(blocchi)
    if vec.shape[1] == 0:
        return [1.0] * (len(blocchi) - 1)
    return [float(np.dot(vec[i], vec[i + 1])) for i in range(len(blocchi) - 1)]


def _local_shift_scores(blocchi: list[str], window: int = SEMANTIC_WINDOW_BLOCKS) -> list[float]:
    """Restituisce per ogni confine uno score 0..1 di cambio semantico locale."""
    n = len(blocchi)
    if n < 2:
        return []
    vec = _tfidf_matrix(blocchi)
    if vec.shape[1] == 0:
        return [0.0] * (n - 1)

    scores: list[float] = []
    for boundary in range(1, n):
        left_ids = list(range(max(0, boundary - window), boundary))
        right_ids = list(range(boundary, min(n, boundary + window)))
        left = vec[left_ids].mean(axis=0)
        right = vec[right_ids].mean(axis=0)
        lnorm = np.linalg.norm(left)
        rnorm = np.linalg.norm(right)
        sim = float(np.dot(left, right) / max(lnorm * rnorm, 1e-12)) if lnorm and rnorm else 0.0
        scores.append(max(0.0, min(1.0, 1.0 - sim)))
    return scores

def _marker_score(testo: str) -> tuple[float, float]:
    """(discourse, outro) per un breve testo vicino al confine."""
    discourse = sum(bool(p.search(testo)) for p in _BOUNDARY_PATTERNS)
    outro = sum(bool(p.search(testo)) for p in _OUTRO_PATTERNS)
    return min(1.0, discourse * 0.35), min(1.0, outro * 0.6)


def _trova_confini(punteggi: list[float], depth_ratio: float = 0.6) -> list[int]:
    """Vecchia API, con depth minima più permissiva."""
    confini = []
    n = len(punteggi)
    if n < 2:
        return confini
    for i in range(1, n - 1):
        if punteggi[i] <= punteggi[i - 1] and punteggi[i] <= punteggi[i + 1]:
            picco_sx = max(punteggi[max(0, i - 3):i] or [punteggi[i]])
            picco_dx = max(punteggi[i + 1:i + 4] or [punteggi[i]])
            profondita = (picco_sx - punteggi[i]) + (picco_dx - punteggi[i])
            soglia = depth_ratio * max(0.005, (picco_sx + picco_dx) / 2 - punteggi[i])
            if profondita > soglia and profondita > 0.07:
                confini.append(i)
    return confini


def _scegli_confini(frasi: list[str], blocchi: list[str]) -> list[int]:
    """Genera confini semantici e li filtra per evitare micro-segmenti."""
    if len(blocchi) < 2:
        return []
    shift = _local_shift_scores(blocchi)
    pair = _punteggi_confine(blocchi)
    candidati: list[tuple[float, int]] = []

    for i in range(1, len(blocchi)):
        # confine tra blocco i-1 e i
        score = shift[i - 1]
        local_sim = pair[i - 1] if i - 1 < len(pair) else 1.0
        score += 0.20 * (1.0 - local_sim)
        vicino = " ".join(blocchi[max(0, i - 1):min(len(blocchi), i + 1)])
        discourse, outro = _marker_score(vicino)
        score += discourse + outro
        candidati.append((score, i))

    # Soglia dinamica: prende i cambi più netti ma non forza un taglio ogni blocco.
    valori = [s for s, _ in candidati]
    media = sum(valori) / max(1, len(valori))
    deviazione = (sum((x - media) ** 2 for x in valori) / max(1, len(valori))) ** 0.5
    soglia = max(0.28, media + 0.55 * deviazione)

    scelti = [i for s, i in candidati if s >= soglia]
    # Aggiunge anche i minimi locali del vecchio TextTiling quando sono forti.
    for i in _trova_confini([1.0 - s for s in shift]):
        if i + 1 not in scelti and shift[i] >= 0.20:
            scelti.append(i + 1)

    # Impone una distanza minima in parole tra confini.
    validi: list[int] = []
    ultimo_word = 0
    words_per_block = [len(b.split()) for b in blocchi]
    block_word_starts = [0]
    for nwords in words_per_block[:-1]:
        block_word_starts.append(block_word_starts[-1] + nwords)
    for i in sorted(set(scelti)):
        word_pos = block_word_starts[min(i, len(block_word_starts) - 1)]
        if word_pos - ultimo_word >= SEMANTIC_MIN_WORDS:
            validi.append(i)
            ultimo_word = word_pos
    return validi


def _normalizza_confini_per_frasi(frasi: list[str], blocchi: list[str], confini_blocco: list[int]) -> list[int]:
    """Converte confini a indice di frase usando le parole reali dei blocchi."""
    if not confini_blocco:
        return []
    target: list[int] = []
    blocco_start = 0
    for bi, blocco in enumerate(blocchi):
        n = len(blocco.split())
        if bi in confini_blocco:
            target.append(blocco_start)
        blocco_start += n
    # Ricostruisci il bordo dal conteggio parole, poi trova la prima frase utile.
    cum_frasi = []
    total = 0
    for f in frasi:
        total += len(f.split())
        cum_frasi.append(total)
    risultati = []
    for word_target in target:
        idx = 0
        while idx < len(cum_frasi) and cum_frasi[idx] < word_target:
            idx += 1
        if 0 < idx < len(frasi):
            risultati.append(idx)
    return sorted(set(risultati))


def _segmenti_da_confini(frasi: list[str], confini_frase: list[int]) -> list[str]:
    segmenti: list[str] = []
    inizio = 0
    for fine in sorted(set(confini_frase)) + [len(frasi)]:
        if fine <= inizio:
            continue
        pezzo = " ".join(frasi[inizio:fine]).strip()
        if pezzo:
            segmenti.append(pezzo)
        inizio = fine
    return segmenti


def _forza_split_lunghi(segmenti: list[str], max_parole: int, min_parole: int) -> list[str]:
    """Hard cap vero, con taglio su frasi e target centrale invece di blocchi fissi."""
    risultato: list[str] = []
    for seg in segmenti:
        parole_tot = len(seg.split())
        # Un segmento sotto il cap assoluto ma molto sopra il target resta
        # comunque troppo grosso per la generazione Q&A: lo splittiamo in
        # parti vicine al target, sempre su confini di frase.
        if parole_tot <= min(max_parole, int(SEMANTIC_TARGET_WORDS * 1.45)):
            risultato.append(seg)
            continue

        frasi = _split_frasi(seg)
        parti: list[str] = []
        corrente: list[str] = []
        n = 0
        target = min(SEMANTIC_TARGET_WORDS, max_parole)
        for frase in frasi:
            nf = len(frase.split())
            # Se siamo oltre target e possiamo ancora creare una parte valida,
            # chiudiamo qui. Evitiamo parti troppo corte.
            if corrente and n >= target and n + nf <= max_parole:
                parti.append(" ".join(corrente))
                corrente, n = [], 0
            if nf > max_parole and not corrente:
                words = frase.split()
                for i in range(0, len(words), max_parole):
                    chunk = " ".join(words[i:i + max_parole])
                    if chunk:
                        risultato.append(chunk)
                continue
            if corrente and n + nf > max_parole:
                parti.append(" ".join(corrente))
                corrente, n = [], 0
            corrente.append(frase)
            n += nf
        if corrente:
            parti.append(" ".join(corrente))

        # Evita un ultimo frammento minuscolo: fondilo indietro se possibile.
        for parte in parti:
            if len(parte.split()) < min_parole and risultato:
                candidato = risultato[-1] + " " + parte
                if len(candidato.split()) <= max_parole * 1.05:
                    risultato[-1] = candidato
                else:
                    risultato.append(parte)
            else:
                risultato.append(parte)
    return risultato


def segmenta_semantico(
    testo: str,
    block_size: int = 4,
    min_parole: int = SEMANTIC_MIN_WORDS,
    target_parole: int = SEMANTIC_TARGET_WORDS,
) -> list[dict]:
    frasi = _split_frasi(testo)
    if not frasi:
        return []
    if len(frasi) < 3:
        return [{"titolo": None, "testo": testo.strip()}] if testo.strip() else []

    # Per la segmentazione vera usiamo blocchi a parole, che sono più stabili
    # dei blocchi a 4 frasi quando l'ASR produce frasi irregolari.
    blocchi = _blocchi_per_parole(frasi, target_words=SEMANTIC_BLOCK_WORDS)
    if len(blocchi) < 3:
        return _forza_split_lunghi([" ".join(frasi)], MAX_PAROLE_DEFAULT, min_parole)

    confini_blocco = _scegli_confini(frasi, blocchi)
    confini_frase = _normalizza_confini_per_frasi(frasi, blocchi, confini_blocco)
    segmenti = _segmenti_da_confini(frasi, confini_frase)

    # Fonde i pezzi piccoli scegliendo il vicino meno penalizzante; il vecchio
    # algoritmo fonderva sempre a sinistra e poteva inglobare un cambio tematico.
    fusi: list[str] = []
    for seg in segmenti:
        if not fusi:
            fusi.append(seg)
            continue
        if len(fusi[-1].split()) < min_parole:
            candidato_sx = fusi[-1] + " " + seg
            if len(candidato_sx.split()) <= MAX_PAROLE_DEFAULT * 1.05:
                fusi[-1] = candidato_sx
            else:
                fusi.append(seg)
        else:
            fusi.append(seg)

    if len(fusi) == 1 and len(fusi[0].split()) <= MAX_PAROLE_DEFAULT:
        # Non forziamo uno split arbitrario: l'unità è abbastanza piccola.
        pass

    fusi = _forza_split_lunghi(fusi, max_parole=MAX_PAROLE_DEFAULT, min_parole=min_parole)
    return [{"titolo": None, "testo": s} for s in fusi if s.strip()]


# ---------------------------------------------------------------------------
# Orchestrazione
# ---------------------------------------------------------------------------

def segmenta_file(path: Path) -> list[dict]:
    testo = path.read_text(encoding="utf-8")
    if ha_marcatori(testo) and densita_titoli_sufficiente(testo):
        risultato = segmenta_strutturato(testo)
    else:
        risultato = segmenta_semantico(testo)

    risultato = _applica_soglia_minima(risultato)
    for u in risultato:
        u.update(_metadati_unita(u["testo"], ha_titolo=u.get("titolo") is not None))
    return risultato


class SegmentationService:
    def __init__(self, config: ExtractConfig):
        self.config = config

    def _salva(self, sorgente: Path, unita: list[dict], sottocartella: str) -> Path:
        cartella_out = self.config.cartella_segmenti / sottocartella
        cartella_out.mkdir(parents=True, exist_ok=True)
        output = cartella_out / f"{sorgente.stem}.json"
        tmp = output.with_name(output.name + ".tmp")
        tmp.write_text(json.dumps(unita, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(output)
        return output

    def esegui(self, forza: bool = False) -> None:
        totale = 0
        if self.config.cartella_testo.exists():
            libri = sorted(self.config.cartella_testo.glob("*.txt"))
            print(f"📚 Testi da segmentare (libri/dispense): {len(libri)}")
            for path in libri:
                try:
                    output = self.config.cartella_segmenti / "libri" / f"{path.stem}.json"
                    if output.exists() and not forza:
                        dati = json.loads(output.read_text(encoding="utf-8"))
                        if dati and all("fonte_tag" in u for u in dati):
                            print(f"⏭️ {path.name} → già segmentato e taggato")
                            totale += len(dati)
                            continue
                    unita = segmenta_file(path)
                    output = self._salva(path, unita, "libri")
                    print(f"✅ {path.name} → {len(unita)} unità → {output}")
                    totale += len(unita)
                except Exception as exc:
                    print(f"❌ Segmentazione fallita {path.name}: {exc}")
        if self.config.cartella_trascrizioni.exists():
            trascrizioni = sorted(self.config.cartella_trascrizioni.glob("*.txt"))
            print(f"🎧 Trascrizioni da segmentare (audio): {len(trascrizioni)}")
            for path in trascrizioni:
                try:
                    output = self.config.cartella_segmenti / "video" / f"{path.stem}.json"
                    if output.exists() and not forza:
                        dati = json.loads(output.read_text(encoding="utf-8"))
                        if dati and all("fonte_tag" in u for u in dati):
                            print(f"⏭️ {path.name} → già segmentato e taggato")
                            totale += len(dati)
                            continue
                    unita = segmenta_file(path)
                    output = self._salva(path, unita, "video")
                    print(f"✅ {path.name} → {len(unita)} unità → {output}")
                    totale += len(unita)
                except Exception as exc:
                    print(f"❌ Segmentazione fallita {path.name}: {exc}")
        print(f"\n💾 Totale unità tematiche generate: {totale}")
