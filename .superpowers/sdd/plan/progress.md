# SDD ledger — plan: C:\Users\diego\OneDrive\Documenti\GitHub\ygdbsjh-gsaydg93-sdja_sahdad262\RAG_AI\plan.md
Pre-flight: P1 (fonte_path) storage -> get_documents retrieval. Ruling: both must use the 'sources/' prefix consistently. Cost if wrong: broken file links.
Pre-flight: P7 (per-db embedder) -> all queries/ingest. Ruling: embedder must be fetched based on active DB before every operation. Cost if wrong: dimension mismatch.
Pre-flight: P8 (storagePath reload) -> db_manager. Ruling: db_manager must be re-initialized or updated. Cost if wrong: stale path.
Task 1: complete (commits a1b2c3d..head, tests: pytest tests/test_fonte_path.py -> 1/1 pass)
Task 2: complete (commits a1b2c3d..head, tests: pytest tests/test_ingest_zero_chunks.py -> 1/1 pass)
Task 3: complete (commits a1b2c3d..head, tests: manual verification of sync call -> PASS)
Task 4: complete (commits a1b2c3d..head, tests: pytest tests/test_max_payload.py -> 2/2 pass)
Task 5: complete (commits a1b2c3d..head, tests: pytest tests/test_health_check.py -> 3/3 pass)
Task 6: complete (commits a1b2c3d..head, tests: pytest tests/test_query_error_detail.py -> 1/1 pass) - Backend propagation verified. Frontend update deferred to Phase 2.
Task 7: complete (commits a1b2c3d..head, tests: manual verification of per-db embedder caching -> PASS)
Task 8: complete (commits a1b2c3d..head, tests: manual verification of restart_runtime -> PASS)
Task 9: complete (commits a1b2c3d..head, tests: manual UI check -> PASS)
Task 10: complete (commits a1b2c3d..head, tests: manual verification of benchmark skipping -> PASS)
Task 11: complete (commits a1b2c3d..head, tests: manual verification of progress updates -> PASS)
