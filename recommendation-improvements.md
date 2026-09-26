# Backend Recommendation Algorithm Improvement Plan

This document records the backend recommendation improvement plan discussed during the recommendation tuning work. It is a project-level execution plan, not a replacement for the current implementation document in `django_backend/doc/recommendation.md`.

## Goals

- Improve recommendation quality without replacing the current `local_preference` strategy.
- Keep the algorithm understandable and debuggable for a single-user NAS deployment.
- Preserve explicit user blocklists as durable preference state.
- Allow recommendation history, snapshots, items, and feedback records to be cleared during experiments so recommendation effects can be validated from a clean baseline.
- Separate four user intents clearly:
  - Add to library implies `like`.
  - `like` does not imply add to library.
  - Blocklist implies `dislike`.
  - `dislike` does not imply blocklist.

## Current Baseline

The current recommendation path uses:

- Local actor / genre preference seeds derived from `AVResource`.
- Jable actor/model pages and genre tag/category pages as primary recall sources.
- Search fallback when mapped pages do not return enough candidates.
- Hot-board and latest-update discovery candidates.
- Candidate filtering for local existing resources and AVID blocklist entries.
- Recent recommendation avoidance using persisted `RecommendationSnapshot` and `RecommendationItem` history.
- Seed-level feedback learning through `RecommendationFeedback` and `RecommendationSeedProfile`.
- Diversity reranking across actor and genre seeds.

The baseline is good enough to iterate in place. The main weakness is not the absence of a recommender, but the lack of tight feedback semantics, measurable iteration loops, and clear separation between preference feedback and hard blocking.

## Design Principles

1. Keep hard filters explicit.
   AVID blocklist and actor/genre seed blocklist should remain durable, user-controlled filters. They should not be accidentally created by weak preference signals.

2. Treat feedback as learning signal.
   `like` and `dislike` should adjust future seed scoring, not mutate the library or resource blacklist by themselves.

3. Prefer seed-level learning first.
   Actor and genre signals are explainable, easy to aggregate, and align with the current local preference strategy.

4. Preserve auditability.
   Continue writing snapshots, items, matched seeds, score breakdowns, and feedback records so each recommendation can be explained and debugged.

5. Make experiments resettable.
   Recommendation history and feedback can be deleted during validation, while blocklists stay intact by default.

## Implementation Plan

### Phase 1: Metrics and Reset Loop

- Add a recommendation metrics endpoint that reports:
  - snapshot count
  - item count
  - distinct AVID count
  - repeat rate
  - `like` / `dislike` counts
  - AVID blocklist count
  - seed blocklist count
  - recent seed exposure
- Add a reset endpoint that clears recommendation experiment data:
  - `RecommendationSnapshot`
  - `RecommendationItem`
  - `RecommendationItemSeed`
  - `RecommendationFeedback`
  - non-blocking `RecommendationSeedProfile` state
- Keep durable blocklists by default:
  - `RecommendationAvidBlocklist`
  - `RecommendationSeedProfile.is_blocked=true`
- Allow an explicit full reset option for rare cases where blocklists should also be cleared.

### Phase 2: Feedback Semantics

- Support explicit feedback values:
  - `like`
  - `dislike`
  - `clear`
- Upsert `like` / `dislike` for the recommendation item identified by `snapshot_id + avid`.
- Delete the current item feedback when `clear` is submitted.
- Adjust `RecommendationSeedProfile.accepted_count` and `disliked_count` by diffing old and new feedback values.
- Do not write AVID blocklist records from `dislike`.
- Do not remove AVID blocklist records from `like`.
- Keep AVID blocklist writes behind the dedicated blocklist API.

### Phase 3: Frontend Intent Mapping

- Make "add to library" submit `like` after the resource add succeeds or is already present.
- Keep standalone `like` as feedback-only.
- Make "block" submit `dislike` and write the AVID blocklist.
- Keep standalone `dislike` as feedback-only.
- Make `like`, `dislike`, and `block` toggles:
  - clicking active `like` / `dislike` submits `clear`
  - clicking active block removes the AVID from the blocklist
- Keep the blacklist UI visually distinct from the preference feedback UI.

### Phase 4: Recall Improvements

- Prefer structured Jable mapping pages when available:
  - actor/model pages for actor seeds
  - tag/category pages for genre seeds
- Fall back to keyword search when structured pages fail or return too few candidates.
- Expand actor search keywords using known aliases, including normalized parenthetical aliases.
- Continue lowering the seed cutoff when high-ranked seeds do not produce enough fresh candidates.
- Use hot-board and latest-update pages as discovery sources so the system can surface items beyond the user's most obvious local clusters.

### Phase 5: Candidate Enrichment

- For discovery candidates, fetch detail metadata within a bounded `detail_enrichment_limit`.
- Extract actor and genre metadata from detail pages when available.
- If enriched actor / genre metadata matches current seeds, attach those matched seeds to the candidate.
- Let enriched discovery candidates receive the same seed-based scoring and explanation benefits as direct seed recall candidates.
- Treat enrichment failures as non-fatal; a failed detail page should not fail the whole recommendation request.

### Phase 6: Scoring and Ranking

- Keep the scoring model factor-based and explainable.
- Use these primary factors:
  - seed weight
  - multiple seed match bonus
  - source priority
  - novelty / recent recommendation penalty
  - lightweight popularity
  - seed-level feedback signal
- Use feedback only at the actor/genre seed level for now.
- Keep AVID-level hard filtering in the blocklist, not in weak feedback.
- Preserve score breakdowns and recommendation notes for frontend display.

### Phase 7: Diversity and Recent Exposure Control

- Apply actor and genre diversity reranking after initial score sorting.
- Penalize repeated exposure of the same seed in recent snapshots.
- Prefer fresh candidates over recently recommended candidates.
- If recent filtering leaves too few results, backfill with lower-ranked recent candidates rather than returning an unexpectedly small result set.

### Phase 8: Validation Workflow

- Before evaluating a new recommendation behavior, reset recommendation history while preserving blocklists.
- Generate several recommendation batches under the same parameter profile.
- Track:
  - repeat rate
  - number of distinct AVIDs
  - like / dislike ratio
  - blocked AVID count
  - recurring overexposed seeds
  - whether discovery candidates are meaningfully enriched
- Compare behavior before and after changes using the same local library and blacklist state.

## Data Retention Policy for Experiments

During recommendation tuning, it is acceptable to delete:

- recommendation snapshots
- recommendation items
- recommendation item seeds
- recommendation feedback
- non-blocking seed profile counters

The following should be preserved unless explicitly requested:

- AVID blocklist
- actor / genre seed blocklist
- local resource library
- actor / genre source mappings

This allows recommendation effects to be validated without losing durable user preference boundaries.

## Acceptance Criteria

- Repeated recommendations produce fewer duplicates across adjacent batches.
- Likes increase future ranking of related actor / genre seeds.
- Dislikes decrease future ranking of related actor / genre seeds without hiding the exact AVID permanently.
- Blocked AVIDs never appear in future recommendations.
- Clearing feedback reverses the seed-level learning effect.
- Resetting recommendation history preserves blocklists by default.
- Recommendation notes remain explainable enough to understand why an item appeared.

## Follow-Up Ideas

- Add per-seed performance summaries to the metrics endpoint.
- Add time decay for old feedback so stale preferences fade gradually.
- Add optional per-source quotas to avoid one discovery source dominating a batch.
- Add offline evaluation scripts that replay saved recommendation snapshots and feedback.
- Consider lightweight collaborative or embedding-based recall only after the current seed-based loop is measurable and stable.
