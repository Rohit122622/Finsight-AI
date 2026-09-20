# FinSentry AI — Phase 7 KPI Report

**Generated:** 2026-09-20 (UTC)
**Environment:** Local development (Windows, Python 3.11, single-node). MongoDB Atlas (dev cluster), Redis 7 (local Docker `finsentry-redis`).
**Command used:** `python -m tests.test_kpi_measurement`

> **Integrity note.** Values below are **real measured results** from executed code. Each metric is explicitly labeled by measurement class. Nothing is fabricated. Uptime is **NOT YET MEASURED** and is not asserted as any percentage.

---

## 1. Measurement classes (do not conflate)

| Class | Meaning |
|---|---|
| **DETERMINISTIC TEST SET** | Measured by the RAG evaluation harness in `ExecutionMode.DETERMINISTIC_MOCK` on the fixed evaluation dataset (Acme Corp FY2024). Repeatable, no live LLM. **Not** production accuracy. |
| **REAL EXTRACTION BENCHMARK** | Executed extraction regression tests against the known Apple/BBBY ground truth. |
| **LOCAL INTEGRATION** | Real timing/execution on the local machine (e.g. report compile + PDF build). |
| **AUTOMATED TEST EXECUTION** | Pass/fail of the executed automated test suites (reliability of the code paths under test, not production traffic). |
| **NOT MEASURED / MANUAL PRODUCTION STEP** | Requires a live production observation window or infrastructure not available locally. |

---

## 2. Phase 7 KPI summary

| Metric | Environment | Population / Dataset | Samples | Measured Result | Target | Status | Class | Limitation |
|---|---|---|---|---|---|---|---|---|
| Extraction accuracy (answer) | Local | Acme FY2024 eval dataset | 25 | 100% | ≥ 90% | PASS | DETERMINISTIC TEST SET | Proxy via RAG answer accuracy on deterministic set; not production docs |
| Citation accuracy | Local | Acme FY2024 eval dataset | 25 | 100% (P 100% / R 100%) | ≥ 95% | PASS | DETERMINISTIC TEST SET | Deterministic set only |
| Hallucination rate | Local | Acme FY2024 eval dataset | 25 | 0% (0 detected) | < 2% | PASS | DETERMINISTIC TEST SET | Deterministic set only |
| Response latency (p95) | Local | Acme FY2024 eval dataset | 25 | 0.13 s (avg 0.12 s) | < 5 s | PASS | DETERMINISTIC TEST SET | No live-LLM network cost; deterministic mock timing |
| Report generation time | Local | 1 synthetic report | 1 | 0.018 s | < 30 s | PASS | LOCAL INTEGRATION | Compile + PDF build only (no live-LLM; report agent is zero-LLM by design) |
| Agent success rate | Local | Acme FY2024 eval dataset | 25 | 100% (25/25) | ≥ 98% | PASS | DETERMINISTIC TEST SET | Deterministic completions; see §4 for real test-execution reliability |
| **Uptime / availability** | — | — | 0 | **NOT YET MEASURED** | ≥ 99% | **NOT MEASURED** | MANUAL PRODUCTION STEP | Requires a continuous production observation window (see §5) |

**Aggregate (deterministic + local):** 6 PASS, 0 FAIL, 1 NOT MEASURED.

---

## 3. Real Apple / BBBY extraction benchmark (REAL EXTRACTION BENCHMARK)

Executed via `python -m pytest tests/test_extraction_agent.py -k "eps or leak or regression"` → **17 passed, 0 failed** (26 deselected by filter).

Verified ground-truth values (unchanged; extraction logic not modified):

| Company | Metric | Expected | Verified |
|---|---|---|---|
| Apple | FY2025 Revenue | 416,161 M | ✓ |
| Apple | FY2025 Net Income | 112,010 M | ✓ |
| Apple | FY2025 Diluted EPS | 7.46 | ✓ (diluted preferred over basic) |
| Apple | FY2024 Revenue | 391,035 M | ✓ |
| Apple | FY2024 Diluted EPS | 6.08 | ✓ |
| BBBY | FY2022 Revenue | 5,344.4 M | ✓ |
| BBBY | FY2022 Gross Profit | 1,207.9 M | ✓ |
| BBBY | FY2022 Net Income | −3,506.7 M | ✓ |
| BBBY | FY2022 Diluted EPS | unavailable | ✓ (not fabricated) |
| — | Cross-document leakage | none | ✓ (leakage-prevention tests pass) |

---

## 4. Agent success — automated test execution (AUTOMATED TEST EXECUTION)

Beyond the deterministic RAG proxy, the six agents' code paths are exercised by executed test suites. Reliability of those executed suites (not production traffic):

| Suite(s) | Result |
|---|---|
| Document / Extraction / Red Flag / Red Flag isolation / Comparison | 156 passed |
| Research agent | 13 passed |
| Reports (incl. per-company + combined) | passing |
| Extraction EPS/leak/regression | 17 passed |

> This is **automated test execution success**, not measured production reliability.

---

## 5. Uptime / availability — NOT YET MEASURED

Uptime is **not** claimed. There is no production deployment and no continuous observation window, so no percentage can be honestly reported.

A repeatable probe was implemented to **begin** accumulating real availability data once deployed:

- **Script:** `scripts/kpi_probe.py`
- **Probes:** FastAPI health (`/api/v1/health`), API (`/openapi.json`), Redis (`PING`), and (optional) Celery worker ping (`CELERY_INSPECT=1`).
- **Records per run:** ISO timestamp, overall `success`, and per-component `ok` + `response_ms`.
- **Usage:** `python scripts/kpi_probe.py --log` appends one JSON line to `kpi_probe_history.jsonl`; exit code is non-zero if the health liveness probe fails (suitable for cron/uptime alerting).

**Demonstration observation (local, backend running):**

```
health: ok (200, ~10 ms)   api: ok (200)   redis: ok (~112 ms)   celery_worker: no worker running at probe time
```

To derive uptime later: run the probe on a fixed interval in production and compute `successful_probes / total_probes` over the observation window. Do not report a percentage until sufficient observations exist.

---

## 6. Explicit limitations

- Deterministic-set metrics (extraction/citation/hallucination/latency/agent-success) reflect the fixed evaluation dataset and mock execution mode; they are **not** production accuracy or production latency.
- Report-generation timing is a local single-sample measurement of compile + PDF build.
- Uptime is unmeasured by design until a production observation window exists.
- No extraction, Red Flag, comparison, research/RAG, PDF encryption, or email behavior was modified to produce these numbers.
