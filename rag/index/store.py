"""Store LanceDB per i chunk indicizzati.

Storage su disco (non in RAM, coerente col vincolo 8GB RAM), embedded
(nessun server separato). Una sola tabella "chunks": i filtri per fonte/
tipo/sezione si fanno con predicati SQL su questa tabella, non con tabelle
separate.

Upsert idempotente: chunk_id e' deterministico (vedi common/schema.py), un
re-ingest della stessa fonte sovrascrive invece di duplicare.
"""

from __future__ import annotations

from pathlib import Path

import lancedb
import pyarrow as pa

from rag.common.schema import Chunk

DB_PATH_DEFAULT = "rag/index/store/lancedb"
TABELLA = "chunks"


def _schema(dimensione_embedding: int) -> pa.Schema:
    return pa.schema(
        [
            pa.field("chunk_id", pa.string()),
            pa.field("testo", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), dimensione_embedding)),
            pa.field("fonte_titolo", pa.string()),
            pa.field("tipo_fonte", pa.string()),
            pa.field("sezione", pa.string()),
            pa.field("posizione", pa.string()),
            pa.field("fonte_path", pa.string()),
            pa.field("lingua", pa.string()),
        ]
    )


def connetti(db_path: str = DB_PATH_DEFAULT) -> lancedb.DBConnection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return lancedb.connect(db_path)


def apri_o_crea_tabella(
    db: lancedb.DBConnection, dimensione_embedding: int
) -> lancedb.table.Table:
    if TABELLA in db.list_tables():
        return db.open_table(TABELLA)
    return db.create_table(TABELLA, schema=_schema(dimensione_embedding))


def upsert_chunks(
    tabella: lancedb.table.Table,
    chunks: list[Chunk],
    embeddings: list[list[float]],
) -> int:
    """Inserisce i chunk con i rispettivi embedding. Sovrascrive per chunk_id
    (merge_insert): un secondo ingest della stessa fonte non duplica.
    """
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"chunks ({len(chunks)}) ed embeddings ({len(embeddings)}) devono avere la stessa lunghezza"
        )
    if not chunks:
        return 0

    record = [
        {**c.to_record(), "vector": emb} for c, emb in zip(chunks, embeddings)
    ]
    # to_record() porta anche il campo "testo"/"chunk_id" gia' nel formato
    # atteso dallo schema; "vector" viene aggiunto qui perche' non fa parte
    # del dataclass Chunk (e' calcolato a valle, in fase di indicizzazione).

    (
        tabella.merge_insert("chunk_id")
        .when_matched_update_all()
        .when_not_matched_insert_all()
        .execute(record)
    )
    return len(record)


def conta_chunk(tabella: lancedb.table.Table) -> int:
    return tabella.count_rows()


if __name__ == "__main__":
    import shutil
    import tempfile

    from rag.common.schema import TipoFonte

    tmp = tempfile.mkdtemp()
    try:
        db = connetti(tmp)
        tabella = apri_o_crea_tabella(db, dimensione_embedding=4)

        chunk_prova = Chunk(
            testo="Il legame ionico nasce da trasferimento di elettroni.",
            fonte_titolo="Chimica Generale",
            tipo_fonte=TipoFonte.LIBRO,
            sezione="Cap. 2",
        )
        embedding_finto = [0.1, 0.2, 0.3, 0.4]

        n = upsert_chunks(tabella, [chunk_prova], [embedding_finto])
        assert n == 1
        assert conta_chunk(tabella) == 1, "primo insert: atteso 1 riga"

        # re-insert dello stesso chunk_id: non deve duplicare
        n = upsert_chunks(tabella, [chunk_prova], [embedding_finto])
        assert conta_chunk(tabella) == 1, "re-insert stesso chunk_id: atteso ancora 1 riga (upsert, non duplicato)"

        # chunk diverso: deve aggiungere una riga
        chunk_2 = Chunk(
            testo="La teoria VSEPR predice la geometria molecolare.",
            fonte_titolo="Chimica Generale",
            tipo_fonte=TipoFonte.LIBRO,
            sezione="Cap. 2",
        )
        upsert_chunks(tabella, [chunk_2], [embedding_finto])
        assert conta_chunk(tabella) == 2, "chunk nuovo: atteso 2 righe totali"

        print("OK — schema, upsert idempotente e conteggio verificati (2 righe attese, 2 ottenute)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
