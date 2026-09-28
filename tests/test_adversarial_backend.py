"""Test avversari su punti del backend che potrebbero non funzionare.

Regola: nessuna modifica al programma. Un test rosso qui significa un
possibile bug/debolezza reale, non un errore del test. Nessuna scrittura su
config.json: config/salvaconfig sono isolati con monkeypatch.
"""

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from webapp.backend import main
from webapp.backend.main import app, mappa_chunk_item, _validate_settings

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isola_stato(monkeypatch):
    """Config e rate-limit isolati: nessuna scrittura su disco, nessun bucket residuo."""
    monkeypatch.setattr(main, "config", dict(main.config))
    monkeypatch.setattr(main, "salvaconfig", lambda cfg: None)
    main._rate_buckets.clear()
    yield
    main._rate_buckets.clear()


# ---------------------------------------------------------------- auth ----

def test_auth_senza_token_401(monkeypatch):
    main.config["apiToken"] = "segreto"
    assert client.get("/api/stats").status_code == 401


def test_auth_token_errato_401(monkeypatch):
    main.config["apiToken"] = "segreto"
    r = client.get("/api/stats", headers={"Authorization": "Bearer sbagliato"})
    assert r.status_code == 401


def test_auth_token_corretto_ok():
    main.config["apiToken"] = "segreto"
    r = client.get("/api/stats", headers={"Authorization": "Bearer segreto"})
    assert r.status_code == 200


def test_auth_schema_bearer_case_insensitive():
    main.config["apiToken"] = "segreto"
    r = client.get("/api/stats", headers={"Authorization": "bearer segreto"})
    assert r.status_code == 200


def test_auth_schema_basic_rifiutato():
    main.config["apiToken"] = "segreto"
    r = client.get("/api/stats", headers={"Authorization": "Basic segreto"})
    assert r.status_code == 401


def test_auth_token_in_query_string_non_accettato_su_endpoint_normali():
    """Il token via ?token= e' ammesso solo per lo stream SSE."""
    main.config["apiToken"] = "segreto"
    assert client.get("/api/stats?token=segreto").status_code == 401


def test_auth_token_solo_spazi_equivale_a_non_configurato():
    main.config["apiToken"] = "   "
    assert client.get("/api/stats").status_code == 200


def test_auth_endpoint_esenti_senza_token():
    main.config["apiToken"] = "segreto"
    for path in ("/api/health", "/api/auth/status", "/api/settings/defaults", "/api/settings"):
        assert client.get(path).status_code == 200, path


def test_auth_put_settings_richiede_token():
    main.config["apiToken"] = "segreto"
    assert client.put("/api/settings", json={"logLevel": "INFO"}).status_code == 401


def test_auth_delete_e_post_protetti():
    main.config["apiToken"] = "segreto"
    assert client.delete("/api/telemetry").status_code == 401
    assert client.post("/api/system/restart").status_code == 401
    assert client.post("/api/query", json={"query": "x"}).status_code == 401


def test_auth_path_con_slash_finale_non_bypassa():
    main.config["apiToken"] = "segreto"
    assert client.get("/api/stats/").status_code in (401, 404, 307)
    # /api/health/ non e' esente: non deve dare 200 senza token
    assert client.get("/api/health/").status_code != 200


def test_auth_status_riflette_configurazione():
    main.config["apiToken"] = "segreto"
    assert client.get("/api/auth/status").json() == {"configured": True}
    main.config["apiToken"] = ""
    assert client.get("/api/auth/status").json() == {"configured": False}


def test_get_settings_non_espone_mai_il_token(monkeypatch):
    monkeypatch.setattr(main, "caricaconfig", lambda: {**main.config, "apiToken": "segreto"})
    assert client.get("/api/settings").json()["apiToken"] == ""


def test_put_settings_risposta_non_espone_token(monkeypatch):
    monkeypatch.setattr(main, "caricaconfig", lambda: {**main.SETTINGS_DEFAULTS, "apiToken": "segreto"})
    r = client.put("/api/settings", json={"logLevel": "INFO", "apiToken": "segreto"},
                   headers={"Authorization": "Bearer segreto"})
    assert r.status_code == 200
    assert r.json()["apiToken"] == ""


def test_put_settings_token_vuoto_non_cancella_token_esistente(monkeypatch):
    monkeypatch.setattr(main, "caricaconfig", lambda: {**main.SETTINGS_DEFAULTS, "apiToken": "segreto"})
    salvati = []
    monkeypatch.setattr(main, "salvaconfig", lambda cfg: salvati.append(cfg))
    r = client.put("/api/settings", json={"apiToken": ""}, headers={"Authorization": "Bearer segreto"})
    assert r.status_code == 200
    assert salvati[-1]["apiToken"] == "segreto"


# ----------------------------------------------------------- rate limit ----

def test_rate_limit_429_dopo_soglia():
    main.config["rateLimitMax"] = 3
    codici = [client.get("/api/stats").status_code for _ in range(5)]
    assert codici[:3] == [200, 200, 200]
    assert 429 in codici[3:]


def test_rate_limit_ha_header_retry_after():
    main.config["rateLimitMax"] = 1
    client.get("/api/stats")
    r = client.get("/api/stats")
    assert r.status_code == 429
    assert r.headers.get("Retry-After") == "60"


def test_rate_limit_health_esente():
    main.config["rateLimitMax"] = 1
    client.get("/api/stats")
    assert client.get("/api/health").status_code == 200


def test_rate_limit_conta_anche_richieste_non_autorizzate():
    """Un attaccante senza token non deve poter consumare all'infinito: le
    401 devono comunque contare nel bucket e diventare 429."""
    main.config["apiToken"] = "segreto"
    main.config["rateLimitMax"] = 3
    codici = [client.get("/api/stats").status_code for _ in range(6)]
    assert 429 in codici


def test_rate_limit_valore_zero_o_nullo_non_blocca_tutto():
    main.config["rateLimitMax"] = 0
    assert client.get("/api/stats").status_code == 200


# ---------------------------------------------------------- mappa_chunk ----

def test_mappa_chunk_tipo_fonte_none_non_crasha():
    item = mappa_chunk_item({"chunk_id": "x", "testo": "t", "tipo_fonte": None}, 0, {})
    assert item["docType"] == "Libro"


def test_mappa_chunk_testo_none_non_crasha():
    item = mappa_chunk_item({"chunk_id": "x", "testo": None, "tipo_fonte": "libro"}, 0, {})
    assert item["text"] in ("", None)


def test_mappa_chunk_sezione_none_usa_default():
    item = mappa_chunk_item({"chunk_id": "x", "testo": "t", "sezione": None}, 0, {})
    assert item["section"] == "Sezione Generale"


def test_mappa_chunk_fonte_titolo_none_usa_default():
    item = mappa_chunk_item({"chunk_id": "x", "testo": "t", "fonte_titolo": None}, 0, {})
    assert item["docTitle"] == "Sconosciuto"


def test_mappa_chunk_vettore_numpy():
    import numpy as np
    item = mappa_chunk_item({"chunk_id": "x", "testo": "t", "vector": np.zeros(8)}, 0, {})
    assert item["dimensions"] == "8d"


def test_mappa_chunk_vettore_vuoto_dimensions_none():
    item = mappa_chunk_item({"chunk_id": "x", "testo": "t", "vector": []}, 0, {})
    assert item["dimensions"] is None


def test_mappa_chunk_senza_chunk_id_usa_indice():
    item = mappa_chunk_item({"testo": "t"}, 4, {})
    assert item["id"] == "4"
    assert item["chunkNum"] == 5


def test_mappa_chunk_tipo_fonte_maiuscolo():
    item = mappa_chunk_item({"chunk_id": "x", "testo": "t", "tipo_fonte": "ARTICOLO"}, 0, {})
    assert item["docType"] == "Ricerca"


def test_mappa_chunk_snippet_esattamente_160_non_ha_puntini():
    item = mappa_chunk_item({"chunk_id": "x", "testo": "a" * 160}, 0, {})
    assert item["highlightSnippet"] == "a" * 160


# ------------------------------------------------------ _validate_settings ----

@pytest.mark.parametrize("chiave,valore", [
    ("chunkSize", True),          # bool non e' un int valido
    ("chunkSize", 512.0),         # float rifiutato
    ("chunkSize", "512"),         # stringa rifiutata
    ("chunkSize", 0),
    ("chunkSize", -1),
    ("chunkOverlap", 100),
    ("chunkOverlap", -1),
    ("portNumber", 0),
    ("portNumber", 65536),
    ("topKCandidates", 0),
    ("topNRerank", 1001),
    ("rateLimitMax", 0),
    ("maxPayloadMB", 0),
    ("workerConcurrency", 65),
])
def test_validate_settings_rifiuta_valori_invalidi(chiave, valore):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        _validate_settings({chiave: valore})
    assert exc.value.status_code == 400


def test_validate_settings_metrica_e_algoritmo_invalidi():
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        _validate_settings({"distanceMetric": "Manhattan"})
    with pytest.raises(HTTPException):
        _validate_settings({"indexAlgorithm": "HNSW"})


def test_validate_settings_none_su_campo_numerico_rifiutato():
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        _validate_settings({"chunkSize": None})


def test_validate_settings_topN_maggiore_di_topK_incoerente():
    """topNRerank > topKCandidates non ha senso (si rerankano meno candidati
    di quelli richiesti): ci si aspetta un 400."""
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        _validate_settings({"topKCandidates": 5, "topNRerank": 50})


def test_validate_settings_ollama_url_non_stringa_rifiutato():
    """ollamaUrl=123 farebbe crashare `.rstrip('/')` all'avvio/alla query."""
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        _validate_settings({"ollamaUrl": 123})


def test_validate_settings_ollama_url_schema_non_http_rifiutato():
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        _validate_settings({"ollamaUrl": "file:///etc/passwd"})


def test_validate_settings_chiavi_sconosciute_non_persistite():
    out = _validate_settings({"chiaveInventata": "x"})
    assert "chiaveInventata" not in out


def test_validate_settings_cors_non_stringa_rifiutato():
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        _validate_settings({"corsOrigins": ["http://a"]})


def test_put_settings_invalido_non_modifica_config_in_memoria():
    prima = dict(main.config)
    r = client.put("/api/settings", json={"chunkSize": -5})
    assert r.status_code == 400
    assert main.config == prima


# ------------------------------------------------------------- upload ----

@pytest.fixture
def cattura_ingest(monkeypatch):
    """Intercetta l'avvio del job: nessuna ingestione reale, restituisce i file salvati."""
    catturati = {}

    def fake_to_thread(func, job_id, saved_files, *a, **kw):
        catturati["files"] = saved_files

        async def _noop():
            return None
        return _noop()

    def fake_schedule(coro):
        coro.close()

    monkeypatch.setattr(main.asyncio, "to_thread", fake_to_thread)
    monkeypatch.setattr(main, "_schedule_ingestion_task", fake_schedule)
    return catturati


def _post_files(files, **data):
    return client.post("/api/ingest", files=files, data=data)


def test_ingest_senza_file_400():
    assert client.post("/api/ingest").status_code == 400


def test_ingest_path_arbitrario_vietato():
    r = client.post("/api/ingest", data={"path": "/etc"})
    assert r.status_code == 400


def test_ingest_solo_estensioni_non_supportate_400(cattura_ingest):
    r = _post_files([("files", ("a.exe", b"MZ", "application/octet-stream"))])
    assert r.status_code == 400


def test_ingest_fallito_non_lascia_job_pending_orfani(cattura_ingest):
    """Un ingest rifiutato (400) non deve lasciare un job 'pending' per sempre."""
    prima = {k for k, v in main.ingestion_jobs.items() if v["status"] == "pending"}
    _post_files([("files", ("a.exe", b"MZ", "application/octet-stream"))])
    dopo = {k for k, v in main.ingestion_jobs.items() if v["status"] == "pending"}
    assert dopo == prima


def test_ingest_fallito_non_lascia_cartella_upload_orfana(cattura_ingest):
    db_root = Path(main.db_manager.get_info_for_id(main.db_manager.active_id)["path"]) / "sources"
    prima = set(db_root.glob("upload_*")) if db_root.exists() else set()
    _post_files([("files", ("a.exe", b"MZ", "application/octet-stream"))])
    dopo = set(db_root.glob("upload_*")) if db_root.exists() else set()
    assert dopo == prima


@pytest.mark.parametrize("nome", [
    "../../evil.json",
    "../evil.json",
    "/etc/evil.json",
    "..\\..\\evil.json",
    "a/../../evil.json",
])
def test_ingest_path_traversal_resta_dentro_batch_root(cattura_ingest, nome):
    r = _post_files([("files", (nome, b"[]", "application/json"))])
    if r.status_code == 400:
        return  # rifiuto esplicito (es. percorso assoluto): comportamento sicuro
    assert r.status_code == 200, r.text
    for p in cattura_ingest["files"]:
        assert ".." not in Path(p).parts
        assert "sources" in Path(p).parts
        assert Path(p).resolve().is_relative_to(
            Path(main.db_manager.get_info_for_id(main.db_manager.active_id)["path"]).resolve()
        )


def test_ingest_relative_paths_json_invalido_400(cattura_ingest):
    r = _post_files([("files", ("a.json", b"[]", "application/json"))], relativePaths="{non json")
    assert r.status_code == 400


def test_ingest_relative_paths_lunghezza_diversa_400(cattura_ingest):
    r = _post_files([("files", ("a.json", b"[]", "application/json"))],
                    relativePaths=json.dumps(["a.json", "b.json"]))
    assert r.status_code == 400


def test_ingest_relative_paths_non_lista_ignorato(cattura_ingest):
    r = _post_files([("files", ("a.json", b"[]", "application/json"))],
                    relativePaths=json.dumps({"a": 1}))
    assert r.status_code == 200


def test_ingest_nomi_duplicati_non_si_sovrascrivono(cattura_ingest):
    r = _post_files([
        ("files", ("dup.json", b"[1]", "application/json")),
        ("files", ("dup.json", b"[2]", "application/json")),
    ])
    assert r.status_code == 200
    nomi = [Path(p).name for p in cattura_ingest["files"]]
    assert len(set(nomi)) == 2


def test_ingest_estensione_maiuscola_accettata(cattura_ingest):
    r = _post_files([("files", ("A.JSON", b"[]", "application/json"))])
    assert r.status_code == 200


def test_ingest_estensione_doppia_pericolosa(cattura_ingest):
    """'file.json.exe' ha suffisso .exe: deve essere scartato."""
    r = _post_files([("files", ("file.json.exe", b"x", "application/octet-stream"))])
    assert r.status_code == 400


def test_ingest_payload_oltre_limite_413(cattura_ingest):
    main.config["maxPayloadMB"] = 0
    r = _post_files([("files", ("a.json", b"[]", "application/json"))])
    assert r.status_code == 413


def test_ingest_troppi_file_413(cattura_ingest, monkeypatch):
    monkeypatch.setattr(main, "MAX_INGEST_FILES", 2)
    files = [("files", (f"f{i}.json", b"[]", "application/json")) for i in range(3)]
    assert _post_files(files).status_code == 413


def test_ingest_file_singolo_campo_file(cattura_ingest):
    r = client.post("/api/ingest", files={"file": ("a.json", b"[]", "application/json")})
    assert r.status_code == 200


def test_ingest_chunk_size_zero_usa_default(cattura_ingest, monkeypatch):
    visti = {}

    def fake_schedule(coro):
        coro.close()

    monkeypatch.setattr(main, "_schedule_ingestion_task", fake_schedule)
    r = _post_files([("files", ("a.json", b"[]", "application/json"))], chunkSize="0")
    assert r.status_code == 200


def test_ingest_status_job_esistente_ha_campi_attesi(cattura_ingest):
    r = _post_files([("files", ("a.json", b"[]", "application/json"))])
    job_id = r.json()["jobId"]
    s = client.get(f"/api/ingest/status/{job_id}")
    assert s.status_code == 200
    for k in ("status", "chunksCreated", "filesTotal", "filesProcessed", "filesFailed"):
        assert k in s.json()
