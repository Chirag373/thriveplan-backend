# Activity completion and rewards

All routes require `Authorization: Bearer <Firebase ID token>`. Backend only. The mobile app still needs session and completion integration. Journal/task reward rules are also implemented on their existing save endpoints, as described below.

## Routes

Each activity has two POST endpoints. Start a session when the user begins, then submit completion when they finish.

| Activity | Start | Complete |
| --- | --- | --- |
| Breathing | `/api/v1/rewards/breathing/sessions/` | `/api/v1/rewards/breathing/sessions/{id}/complete/` |
| Puzzles | `/api/v1/rewards/puzzles/sessions/` | `/api/v1/rewards/puzzles/sessions/{id}/complete/` |
| Knowledge quiz | `/api/v1/rewards/quizzes/sessions/` | `/api/v1/rewards/quizzes/sessions/{id}/complete/` |
| Workout | `/api/v1/rewards/workouts/sessions/` | `/api/v1/rewards/workouts/sessions/{id}/complete/` |
| Reading | `/api/v1/rewards/reading/sessions/` | `/api/v1/rewards/reading/sessions/{id}/complete/` |

`GET /api/v1/rewards/puzzles/` and `GET /api/v1/rewards/quizzes/` return versioned definitions and stable target IDs, without solutions or quiz answer keys. These match the current app catalog (three each of Sudoku, Patches, Zip, Queens, and quiz rounds). Never change the meaning of an existing catalog ID. New content needs a new ID/version.

## Start request

```json
{"request_id": "f132e27d-95cb-45d8-aa45-d65a9385e209", "target_id": "guided-breathing-v1"}
```

Generate a UUID once per session and retain it for retries. Returns 201 when created, 200 on a matching retry. A reused UUID with a different owner, activity or target returns 400. Retrying does not reset the timer.

Targets and requirements

- Breathing uses `guided-breathing-v1`, with a 60-second minimum.
- Puzzles and quizzes use IDs from the catalog, such as `zip-v1-1` and `quiz-v1-1`.
- Workouts use an active workout `WellnessContent` ID as a string. Minimum duration is the content's `duration_seconds`, defaulting to 600 seconds if unset. Durations of 24 hours or more are unsupported.
- Reading uses an active book `WellnessContent` ID as a string, with a 300-second minimum.

The start response includes `id`, `activity`, `target_id`, `started_at`, `minimum_seconds`, `completed_at`, `reward_date`, `reward_timezone`, `points_awarded`, `reward_reason`, `score`, and `already_completed`.

## Completion request

Breathing, workout, reading

```json
{"confirmed": true}
```

Puzzles and quizzes

```json
{"answers": [0, 8, 11, 19, 22]}
```

- Queens expects selected queen cell indices (zero based), in any order.
- Zip expects ordered cell indices covering every cell and visiting checkpoints in order.
- Sudoku expects all 81 digits in row-major order, preserving clues.
- Patches expects one clue label per cell in row-major order, with labels starting at 1 in catalog clue order. Each region must be a valid rectangle satisfying its clue area and shape.
- Quizzes expect one zero-based option index per question in catalog order. Complete rounds earn points regardless of accuracy. `score` reports the number correct.

The server validates game answers against its own definitions. Timed sessions require elapsed server time and explicit confirmation. Elapsed time does not prove active participation, external-link watching, or physical exercise. The frontend must run a guided/tracked session before submitting confirmation. Sessions expire after 24 hours. Clients cannot supply timestamps, reward amounts, or a reward timezone.

A successful completion returns 200 and the session fields. `reward_reason` is `awarded`, `daily_limit`, or `already_solved`. Repeated completion returns the original result with `already_completed: true`, without another ledger transaction. `points_awarded` is the original session award, not a new award on each retry. Only show a reward toast once per session. Refresh `/api/v1/rewards/summary/` after completion.

Invalid/incomplete solutions, short sessions, expired sessions, unconfirmed sessions, or unsupported fields return 400 without completing the session. Missing or another user's sessions return 404. Authentication failures return 401.

## Reward rules

- Breathing earns 5 points once per day.
- Each unique puzzle earns 5 points on its first validated completion, subject to the shared games cap.
- Quiz completion earns 5 points once per day.
- Puzzles and quizzes together earn at most 10 points per day.
- Workouts earn 10 points once per day.
- Reading earns 5 points once per day.

Completed puzzles are consumed even when the daily cap prevents an award. Replaying that puzzle on a later day does not earn points. Quiz rounds can be repeated on later days, but each day still has the quiz and shared games limits.

Daily caps use the server's fixed `REWARDS_TIME_ZONE` (UTC by default), at completion time. Set `Asia/Kolkata` before rollout if that is the desired reward day. Do not change it mid-rollout without reconciling stored reward dates. Summary accepts a display timezone independently, so request the reward timezone for a matching daily display.

Completion records, caps and ledger writes run in a database transaction with a user row lock. Production concurrent requests require PostgreSQL row-lock semantics. SQLite is suitable for local development but does not implement `select_for_update`. No cross-activity streak or milestone bonuses are introduced.

Apply schema with `python manage.py migrate` before using these routes.

## Journal and task rewards

- `POST /api/v1/journal/entries/` awards 10 points on the first successful save per server reward day. Typed, template and voice entries share this allowance. Editing an entry does not award points. Deleting entries does not delete ledger records or reset the daily allowance. Client-supplied entry dates do not control the reward date.
- `PATCH /api/v1/planner/tasks/{id}/` awards 5 points on the first transition to `Completed` (including `completed: true`), up to 25 task points per server reward day. First completions at the cap are still recorded and cannot earn points by reopening later. Subtasks do not award points.
- Task creation does not award points, including tasks created as completed. The migration marks currently completed tasks as already completed without retroactive rewards. Historical completions of tasks already reopened before this migration cannot be inferred from the old schema.
- Journal and task representations now include `points_awarded`, the amount granted by that request, defaulting to zero for reads, edits, or repeated completions. Frontend reward messaging must use this server value. The frontend has not been modified.
- A journal POST retry across a reward-day boundary is indistinguishable from a fresh entry because the existing save API has no idempotency key. It can create another entry and use that new day's allowance. Same-day retries cannot earn extra points.

Both save and reward operations commit atomically. The ledger is retained when an entry or task is deleted. Daily limits use the same fixed `REWARDS_TIME_ZONE` as other activities. Task rewards use per-user row locking before locking the task. Production concurrency guarantees require PostgreSQL.
