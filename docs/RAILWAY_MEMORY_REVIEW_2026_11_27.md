# Railway process memory — 27 November 2026

The owner confirmed one replica each for API, worker and beat, using the repository Procfile commands. The screenshot shows accumulated RAM costs of $1.2300 (worker), $0.7301 (API), $0.5433 (beat), $0.1120 (Redis), not instantaneous GB of occupied RAM. CPU costs are small by comparison. Increasing task intervals does not remove the always-running Python process baseline.

## Decision and deployed configuration requirement

Use one API worker with eight threads at the current small deployment size. Keep Celery prefork, concurrency one, acknowledgements, prefetch, every task and all job schedules unchanged. Do not combine beat/worker or enable service sleeping for financial jobs.

The Procfile web command now defaults to:

```sh
gunicorn run:app --bind 0.0.0.0:$PORT --workers ${WEB_CONCURRENCY:-1} --threads ${GUNICORN_THREADS:-8} --timeout 120
```

If Railway's Custom Start Command is a copied literal containing `--workers 2 --threads 4`, replace it with this command: editing a repository file cannot rewrite Railway dashboard settings. If the service actually reads Procfile, the new default takes effect on deployment. No Railway management connection is available here; the running process count and production savings cannot be certified from a successful deployment status. Optional rollback/growth settings are `WEB_CONCURRENCY=2`, `GUNICORN_THREADS=4`. These names now have an explicit effect through shell expansion in the Procfile command. Use a full Python/Gunicorn restart after changes.

## Local comparison

The existing full Flask application ran under Gunicorn with local-only benchmark networking and dummy service configuration. The real public messages endpoint and a temporary local-only 30 ms simulated I/O endpoint were exercised at concurrency 8 and 16, 288 requests per case. Each profile completed 1,152 successful requests and recovered after terminating a worker process. No production user, order, money, provider send, live API request or database mutation was part of these tests.

| Profile | Ready process-tree PSS | Loaded process-tree PSS | Result |
|---|---:|---:|---|
| Existing 2 workers × 4 threads | 91.12 MiB | 98.82 MiB | Baseline |
| 1 worker × 8 threads | 54.88 MiB | 60.04 MiB | About 39% lower loaded API memory |
| 2 workers × 4 threads with preload | 59.47 MiB | 100.73 MiB | Startup savings disappeared under load; rejected |

The one-worker profile retained eight simultaneous I/O slots. At concurrency 8, simulated I/O p95 was 38 ms versus 59 ms; actual large-catalog p95 was 114 ms versus 83 ms. Large-catalog maximum throughput fell from about 168 to 104 requests/second. This is a measured CPU-bound tradeoff, not a claim of equivalent peak throughput or faster production pages. Account creation frequency is not request-rate telemetry; production request-rate and latency measurements are still needed to establish capacity. Retain the two-worker override if CPU-heavy traffic or tail latency requires it.

This test is a local process comparison, not Railway billing acceptance, a full payment journey, or a database/production concurrency test. At the screenshot's cost mix the API saving alone would imply roughly an 11% reduction in total RAM cost if it transferred directly; it does not promise a 39% reduction in the entire bill. Long-lived worker memory and different provider accounting may change that result. [Raw bounded results](evidence/railway-memory-2026-11-27/local-benchmark.json).
