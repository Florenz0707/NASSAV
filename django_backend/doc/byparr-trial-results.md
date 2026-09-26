# Byparr P0–P1 trial record

Date: 2026-09-26. Branch: `enhancement/byparr-migration`. Baseline commit: `3ebd92d`.
The migration plan was initially untracked; the incorrect image tag in it was corrected from `v3.0.4` to `3.0.4` before the trial commit.

## Environment and image

- Django runs on the host; Byparr runs in Docker and exposes `127.0.0.1:8192`.
- Host architecture: x86_64. Available memory at start: approximately 12 GiB. Trial shared memory: 512 MiB.
- No running FlareSolverr container or listener on ports 8191/8192 was found. The locally cached old image was `ghcr.io/flaresolverr/flaresolverr:latest`, image ID `7962759d99d7`. Existing runtime config enables the old browser and a separate direct-request proxy. No service startup parameters or old logs were available to record.
- The upstream source release is `v3.0.4`, while its [image publishing workflow](https://raw.githubusercontent.com/ThePhaseless/Byparr/v3.0.4/.github/workflows/docker-publish.yml) generates the image tag `3.0.4`. Pulling `v3.0.4` returned `not found`; pulling `3.0.4` succeeded.
- Pulled `ghcr.io/thephaseless/byparr:3.0.4`, Linux amd64, digest `sha256:874f719518f617d03a60e03411fc5d090647e1a877041e81f8dc965927c7deb6`. The Compose file pins that digest.
- The trial container `nassav-byparr-trial` was healthy with zero restarts at inspection. Memory after the serial requests was about 110 MiB; this is a snapshot, not a peak. Browser exit used the container's default network path; host direct-request proxy settings were not injected into Byparr.

## Serial protocol and page probes

All probes used `POST /v1`, `cmd=request.get`, `maxTimeout=60000`, `returnOnlyCookies=false`, and a 70-second control read timeout. Results below are one request per row, with no success-rate claim. API HTTP 200 and reported target status 200 alone were not treated as evidence of valid content.

| Page                                            | Result                    | Elapsed | Structural evidence                                 |
| ----------------------------------------------- | ------------------------- | ------: | --------------------------------------------------- |
| `https://example.com/`                          | `ok`, HTML                |  5.53 s | 559 characters                                      |
| MissAV home                                     | `ok`, HTML                | 61.07 s | 382,211 characters; home title                      |
| Jable home                                      | `ok`, HTML                | 29.77 s | 124,728 characters; video links                     |
| MissAV `snos-116` old test URL                  | **Invalid business page** | 47.46 s | 154,429 characters but no required UUID marker      |
| Jable `jur-466` detail                          | Valid detail              | 27.62 s | `var hlsUrl` found                                  |
| Jable `JUR-466` search                          | Search HTML               | 16.58 s | 10 video-link matches; full list parser not checked |
| MissAV current homepage link `ipzz-912`         | Valid detail              | 63.99 s | Required UUID marker found                          |
| MissAV existing Source candidate `/cn/ipzz-912` | Valid detail              | 39.76 s | Required UUID marker found                          |

The old MissAV sample returned an ordinary home title, no `surrit`, and no UUID marker despite `solution.status=200` and an unchanged final URL. This confirms that content validation must reject it. A current homepage link supplied a parseable positive sample. The 63.99-second request approached the 70-second control budget, so broader sampling and caller timeout checks remain necessary.

## Gate and remaining validation

The minimum P1 gate passed for one current MissAV detail and one Jable detail; the control protocol also worked. This permits implementation of the offline adapters. It does **not** satisfy P4/P5 rollout acceptance: three valid details per source, list and pagination coverage, two time periods, 20 timed requests, concurrent requests, resource peaks, cookie handling, download regression, and rollback rehearsal are still outstanding. Current runtime config was not switched.
