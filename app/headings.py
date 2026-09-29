from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

import pymupdf as fitz  # type: ignore

import re

def e_rumore(linea: str) -> bool:
    linea = linea.strip()
    if not linea:
        return True
    return bool(re.match(r"^(?:www\.|https?://|page\s+\d+$|pagina\s+\d+$|\d+$)", linea, re.I))

CAMPIONE_PAGINE_DEFAULT = 40
SOGLIA_RATIO_BOILERPLATE = 0.3
ZONA_HEADER_FOOTER = 0.12  # percentuale altezza pagina considerata header/footer


@dataclass(frozen=True)
class StatisticheFont:
    body_size: float
    h1_threshold: float
    h2_threshold: float


def _righe_pagina(page: "fitz.Page") -> list[dict]:
    """Estrae le righe della pagina con testo, dimensione font dominante
    (pesata per numero di caratteri, non il max) se contengono bold, e
    posizione verticale (y0). La dimensione dominante evita che un singolo
    simbolo di formula grande (∑, ∫) inline in una riga di testo normale
    (es. "...cioè mtot = ∑...") faccia salire la size dell'intera riga."""
    righe = []
    try:
        blocchi = page.get_text("dict")["blocks"]
    except Exception:
        return righe
    for blocco in blocchi:
        for line in blocco.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            testo = "".join(s.get("text", "") for s in spans).strip()
            if not testo:
                continue
            pesi: Counter[float] = Counter()
            n_char_tot = 0
            n_char_bold = 0
            for s in spans:
                n_char = len(s.get("text", ""))
                if n_char:
                    pesi[round(s.get("size", 0.0), 1)] += n_char
                    n_char_tot += n_char
                    if "bold" in (s.get("font", "") or "").lower():
                        n_char_bold += n_char
            size_dominante = pesi.most_common(1)[0][0] if pesi else 0.0
            bold_ratio = n_char_bold / n_char_tot if n_char_tot else 0.0
            y0 = line.get("bbox", [0, 0, 0, 0])[1]
            righe.append({"testo": testo, "size": size_dominante, "bold": bold_ratio >= 0.9, "y0": y0})
    return righe


def calcola_statistiche_font(doc: "fitz.Document", campione_pagine: int = CAMPIONE_PAGINE_DEFAULT) -> StatisticheFont:
    """Soglie derivate dal documento stesso (niente valori fissi globali):
    la dimensione più frequente = corpo del testo, le dimensioni superiori
    presenti nel documento = candidati H1/H2."""
    sizes: Counter[float] = Counter()
    n = min(campione_pagine, len(doc))
    for i in range(n):
        for riga in _righe_pagina(doc[i]):
            sizes[round(riga["size"], 1)] += len(riga["testo"])
    if not sizes:
        return StatisticheFont(body_size=10.0, h1_threshold=14.0, h2_threshold=12.0)
    body_size = sizes.most_common(1)[0][0]
    superiori = sorted((s for s in sizes if s > body_size), reverse=True)
    h1 = superiori[0] if superiori else body_size + 4
    h2 = superiori[1] if len(superiori) > 1 else body_size + 2
    return StatisticheFont(body_size=body_size, h1_threshold=h1 - 0.5, h2_threshold=h2 - 0.5)


def rileva_righe_boilerplate(doc: "fitz.Document", campione_pagine: int = CAMPIONE_PAGINE_DEFAULT, soglia_ratio: float = SOGLIA_RATIO_BOILERPLATE) -> set[str]:
    """Righe (testo normalizzato) che ricorrono su una quota significativa
    delle pagine campionate in posizione di header/footer: watermark,
    footer di download, intestazioni istituzionali ripetute. Complementa
    (non sostituisce) il filtro a frequenza già presente in ocr.py, che
    resta utile per boilerplate non posizionato (es. watermark centrale).
    """
    n = min(campione_pagine, len(doc))
    if n == 0:
        return set()
    conteggi: Counter[str] = Counter()
    for i in range(n):
        page = doc[i]
        altezza = page.rect.height
        for riga in _righe_pagina(page):
            if riga["y0"] < altezza * ZONA_HEADER_FOOTER or riga["y0"] > altezza * (1 - ZONA_HEADER_FOOTER):
                chiave = re.sub(r"\s+", " ", riga["testo"]).strip().lower()
                if chiave:
                    conteggi[chiave] += 1
    return {testo for testo, c in conteggi.items() if c >= 2 and c / n >= soglia_ratio}


def _sembra_titolo_testuale(testo: str) -> bool:
    """Un titolo vero è testo, non un simbolo matematico isolato. In molti
    PDF tecnici i simboli di sommatoria/integrale (∑, ∫) sono tipografati
    in un font più grande del corpo per ragioni di leggibilità — stessa
    dimensione di un vero titolo, ma non lo sono. Richiediamo una quota
    minima di caratteri alfabetici e almeno 2 parole alfabetiche.

    Filtro anti-frammento (verificato su appunti-di-chimica-organica.pdf:
    elimina falsi positivi come "forza di legame." o "regole di
    costruzione)."): un titolo vero comincia quasi sempre con una
    maiuscola o una cifra. Un frammento bold a metà frase, tipico
    dell'enfasi dentro un paragrafo, comincia con una minuscola perché è
    la continuazione della frase precedente."""
    alfabetici = len(re.findall(r"[A-Za-zÀ-ÿ]", testo))
    if len(testo) == 0 or alfabetici / len(testo) < 0.5:
        return False
    parole_alfa = [p for p in re.findall(r"[A-Za-zÀ-ÿ]+", testo) if len(p) >= 2]
    if len(parole_alfa) < 2:
        # Titoli tecnici del tipo "Chapter 1", "3. Introduction" o
        # "Appendix A" sono validi anche con una sola parola alfabetica.
        if not (len(parole_alfa) == 1 and re.search(r"\d|[A-Za-zÀ-ÿ]$", testo)):
            return False
    primo_carattere_alfa = next((c for c in testo if c.isalpha()), "")
    if primo_carattere_alfa and not primo_carattere_alfa.isupper() and not testo[0].isdigit():
        return False
    return True


def estrai_testo_con_intestazioni(page: "fitz.Page", stats: StatisticheFont, boilerplate: set[str]) -> str:
    """Sostituisce testo_sicuro() quando servono i marcatori di titolo.
    Applica lo stesso filtro rumore di ocr.e_rumore riga per riga, scarta
    il boilerplate posizionale rilevato a livello di documento, e prefissa
    ##H1##/##H2## alle righe il cui font supera le soglie del documento
    E che assomigliano a un titolo testuale (non un simbolo di formula
    grande). Le righe con lo stesso font del corpo (liste puntate,
    esercizi, frammenti di formule spezzate) non ricevono mai un
    marcatore, quindi non possono essere confuse con titoli veri in fase
    di segmentazione.
    """
    righe_out = []
    for riga in _righe_pagina(page):
        testo = riga["testo"]
        if e_rumore(testo):
            continue
        chiave = re.sub(r"\s+", " ", testo).strip().lower()
        if chiave in boilerplate:
            continue
        n_parole_riga = len(testo.split())
        e_grande = riga["size"] >= stats.h1_threshold or riga["size"] >= stats.h2_threshold
        e_bold_breve = riga["bold"] and n_parole_riga <= 20 and riga["size"] >= stats.body_size
        if (e_grande or e_bold_breve) and _sembra_titolo_testuale(testo):
            if riga["size"] >= stats.h1_threshold:
                righe_out.append(f"##H1## {testo}")
            else:
                righe_out.append(f"##H2## {testo}")
        else:
            righe_out.append(testo)
    return "\n".join(righe_out)
