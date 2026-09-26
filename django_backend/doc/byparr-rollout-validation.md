# Byparr rollout validation and rollback record

Date: 2026-09-26. Status: **local development switched; production rollout gate not yet met**. This record distinguishes completed local checks from production acceptance.

## Deployment state

- Source release: `v3.0.4`; published container tag: `3.0.4`; deployed Compose image: `ghcr.io/thephaseless/byparr@sha256:874f719518f617d03a60e03411fc5d090647e1a877041e81f8dc965927c7deb6` (Linux amd64).
- Topology: Django on the host, Byparr in Docker, control API on `127.0.0.1:8192`. Browser exit used Docker's default network; Django's configured direct-request proxy was not passed into Byparr. The optional `BYPARR_PROXY_SERVER` is unset.
- The trial container was stopped and removed after P1; `docker compose -f django_backend/scripts/byparr/compose.yaml up -d` started `nassav-byparr-byparr-1`. `/docs` returned HTTP 200, Docker health became `healthy`, restart count was 0. A post-start memory snapshot was about 94 MiB. This is not a peak measurement.
- Local `config/config.yaml` now enables `BrowserFetch` with `provider: byparr`, `url: http://127.0.0.1:8192`, and `timeout_ms: 60000`. MissAV uses `browser_first`; Jable uses `direct_first`. The user reported local operation normal. This ignored configuration is not committed; the tracked template still defaults to disabled.

## Checks performed

| Check                                                               | Result                                                                                                                                                                                                                        |
| ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| P1 fixed image and control protocol                                 | Passed; details in [trial record](byparr-trial-results.md)                                                                                                                                                                    |
| MissAV current detail through Byparr and Source structure validator | Passed once after implementation (`IPZZ-912`)                                                                                                                                                                                 |
| Jable current detail through Byparr and Source structure validator  | Passed once after implementation (`JUR-466`)                                                                                                                                                                                  |
| Explicit online test run                                            | `2 passed` in 76.71 s, serial                                                                                                                                                                                                 |
| Related offline regression                                          | `56 passed, 2 skipped` in the final related regression run; includes SourceManager injection, redirected direct pages, and isolated lookup failure state                                                                      |
| Full `uv run pytest tests/ -v`                                      | `234 passed, 14 skipped, 7 failed` in 66.26 s. All seven failures were existing translator tests requiring unavailable Ollama; no migration test failed. Existing live resource/debug tests were made opt-in before this run. |
| `pre-commit run -a`                                                 | Passed all hooks after staging and formatting                                                                                                                                                                                 |
| Database schema                                                     | Unchanged; no migration added                                                                                                                                                                                                 |

The original P1 detail probe found an old MissAV URL that returned `status=200` but an ordinary homepage without the UUID marker. This negative case is in the [trial record](byparr-trial-results.md), and the offline tests now reject challenge/invalid pages on both paths. HTML success does not establish playback-list or media-download success.

## Remaining P4/P5 gate

The [migration plan](byparr-migration-plan.md) calls for at least three valid details per source, four list/search/pagination pages, two time periods, a measured positive sample rate and hot-request P95, negative false-positive checks, serial and concurrency-two resource measurements, Cookie API and download regression, and a live configuration rollback rehearsal. These are **not complete**. The existing two online checks are insufficient to claim a success rate. Production task pause, staged source enablement, coordinated process restarts, and 24-hour observation have not begun.

## Configuration and rollback procedure

Before a production switch, save the target machine's `django_backend/config/config.yaml` outside Git and record the running Web/task process versions. Enable `BrowserFetch` with the tested address, then restart every process holding Source instances after draining in-flight tasks. The local development switch does not replace this production procedure.

For a direct-only rollback, set `BrowserFetch.Enable: false` and restart those processes; restore the saved configuration if a full configuration rollback is needed. Check Source logs, Cookie API, and task completion/failure feedback before resuming jobs. Only after no process uses Byparr, stop it with `docker compose -f django_backend/scripts/byparr/compose.yaml down`. The production rollback procedure has been documented but **not rehearsed**.

## Risks and follow-up

- The local configuration backup is outside Git; keep a separate backup on each production host before changing it.
- A single MissAV browser request took 63.99 s, close to the 70 s control read budget. Three candidates plus direct fallbacks can exceed a Web/task deadline; inspect caller and reverse-proxy limits before enabling.
- Browser concurrency and memory peaks are unmeasured. No cross-process limit has been added; begin online acceptance serially.
- Cookie acquisition and complete media downloads remain unverified online. Do not infer either from successful HTML parsing.
