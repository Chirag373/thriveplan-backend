# ThrivePlan backend

Django REST API with Firebase Authentication. Currently implements signup, login, forgot-password, and the current-user profile.
The Expo frontend has been inspected but is not connected to this API yet.

## Run locally (no Docker)

```sh
uv sync
cp .env.example .env
# Edit .env: set Firebase project ID and GOOGLE_APPLICATION_CREDENTIALS.
uv run python manage.py migrate
uv run python manage.py runserver
```

Use a Firebase service account or Application Default Credentials belonging to the
configured project. Keep credential JSON files outside the repository. Enable the
required sign-in providers in Firebase Console. Local development uses SQLite;
production uses PostgreSQL with `DJANGO_SETTINGS_MODULE=config.settings.production`,
a strong `DJANGO_SECRET_KEY`, `DATABASE_URL`, and explicit `DJANGO_ALLOWED_HOSTS`.
Run migrations against the intended database before starting the server.

## Signup

`POST /api/v1/accounts/signup/`

```http
Authorization: Bearer <Firebase ID token>
Content-Type: application/json

{"name": "Alex Smith"}
```

The mobile app first creates/authenticates the Firebase user and obtains an ID
token. Email/password and password confirmation belong to that client flow;
phone sign-in requires Firebase OTP. Google and Apple require their Firebase
provider setup. The backend does not receive passwords or trust client-supplied
contact details, UIDs, verification flags, or roles.

```json
{
  "user": {
    "id": 1,
    "name": "Alex Smith",
    "email": "alex@example.com",
    "email_verified": false,
    "phone_number": "",
    "onboarding_completed": false
  },
  "created": true,
  "next_step": "preferences"
}
```

Returns 201 on creation; 200 on retry for an existing active UID. Retries preserve
profile values. UID is the identity key; accounts are never merged by email.
An authenticated Firebase user can provision a profile before email verification;
`email_verified` is reported honestly and must not be treated as true by later
features. No trial, subscription, or rewards are granted by signup.

Errors: 400 invalid body; 401 missing/invalid/expired/revoked token or anonymous
identity; 403 locally deactivated account; 429 throttled; 503 Firebase unavailable.
Token verification includes revocation and Firebase-disabled-account checks on
every request. Existing email/phone metadata is not refreshed by signup retries.
The response uses `next_step` for client navigation and does not issue a new token
or Django session. Protected endpoints use the shared FirebaseAuthentication DRF adapter.

The current form's fields are `name`, `contact`, `password`, and `confirmation`.
After Firebase signup, submit only `name` here, then route to preferences on
success. If the API fails after Firebase signup, retry with the existing Firebase
identity instead of creating another Firebase account. Preferences saving and
email-verification UI are separate future work.

## Login

`POST /api/v1/accounts/login/`

```http
Authorization: Bearer <Firebase ID token>
Content-Type: application/json

{}
```

The frontend signs in with Firebase first, then sends its ID token here. Django
verifies that token, finds the existing local account by Firebase UID, checks
that it is active, runs the post-auth workflow, and records `last_login`.
Returns 200 with `user` (the same fields as signup) and `next_step`:
`preferences` for incomplete onboarding, otherwise `home`.

An unknown UID returns 404 with `{"detail": "Complete signup before logging in."}`;
finish the signup endpoint first. Login never creates a local user or links
accounts by email. It repairs missing preferences without changing existing
profile or onboarding values. Firebase remains responsible for token refresh and
remember-me persistence; this endpoint issues no Django session or token.

Only an empty body or `{}` is accepted. Passwords, email, UID, and other body fields
are rejected with 400. Invalid/revoked tokens return 401, deactivated local users
403, rate limiting 429, and Firebase unavailability 503. Login has its own
10 requests/minute throttle. The frontend is not wired to this endpoint yet.

## Forgot password

`POST /api/v1/accounts/forgot-password/` (no authentication required)

```json
{"email": "alex@example.com"}
```

Returns 200 with the same message for eligible, unknown, or suppressed accounts:

```json
{"detail": "If an eligible account exists, you will receive a password reset email."}
```

The backend calls Firebase `accounts:sendOobCode` with `PASSWORD_RESET`; Firebase
sends the email and its hosted action page lets the user choose a new password.
Django does not generate, store, or return reset tokens or passwords, and does
not require a local user record. Account-specific suppression is intentionally
not exposed. A 200 response does not guarantee email delivery.

Set `FIREBASE_WEB_API_KEY` to the Web API key of the same project configured by
`FIREBASE_PROJECT_ID`. Enable Firebase Email/Password authentication and configure
the password-reset email template/action handler in Firebase Console. The API
uses the hosted Firebase handler; it accepts no client-provided redirect URL.
Enable Firebase email enumeration protection. Phone-only users use phone OTP;
this endpoint accepts email only. The frontend's existing forgot-password screen
still needs the API call connected.

Invalid input returns 400, throttling 429 (5/minute per IP), and missing
configuration, network failure or upstream service/configuration errors return
503 without exposing upstream details. Requests have bounded connection/read
timeouts and do not follow redirects. The same deployment rate-limit/cache
considerations described below apply. Unit tests mock the HTTP call: no real
reset emails were sent or delivery verified.

Reference: [Firebase password reset REST API](https://firebase.google.com/docs/reference/rest/auth/#section-send-password-reset-email).

## Current user

`GET /api/v1/accounts/me/`

Send `Authorization: Bearer <Firebase ID token>` with no request body.
Returns 200 with `user` (id, name, email, email_verified, phone_number,
onboarding_completed) and `next_step` (`home` or `preferences`), matching the
login response. Contact fields are the stored local profile snapshot; this read
does not synchronize Firebase metadata.

The Firebase DRF authentication adapter verifies every token, including revocation,
and selects the local account by UID. The endpoint reads only: it does not create
accounts/preferences, change last_login, or update profile fields on GET. Missing
preferences are represented as incomplete onboarding. Responses use
`Cache-Control: private, no-store`. Query parameters cannot select another user.

Missing/invalid tokens return 401, locally disabled accounts 403, unknown UIDs
404 (complete signup), and Firebase unavailability 503. POST/PUT/DELETE are
not implemented; PATCH is documented below. The frontend can call this on app startup after restoring its
Firebase session; frontend integration remains pending.

## Profile and preferences updates

Both endpoints require `Authorization: Bearer <Firebase ID token>` and JSON.

`PATCH /api/v1/accounts/me/`

```json
{"name": "Alex Smith"}
```

Returns 200 with `user` and `next_step`, matching GET /me/. Name is trimmed,
required, nonblank, and limited to 150 characters. Identity/contact fields cannot
be edited here; Firebase owns them.

`PATCH /api/v1/accounts/me/preferences/`

```json
{"profession": "student", "focus_areas": ["planning", "journaling"]}
```

Returns 200 with `preferences` (profession, focus_areas, onboarding_completed)
and `next_step`. Either field may be sent independently; omitted fields retain
their existing values. Focus areas replace the previous list. Professions:
`student`, `professional`, `entrepreneur`, `personal`. Focus areas: `planning`,
`journaling`, `habits`, `mindfulness`; choose 1–4 unique values.

Onboarding is completed automatically when the saved name, profession, and focus
areas are present. Clients cannot set onboarding_completed directly. Empty
requests, unknown fields, invalid choices, and duplicate/empty focus lists return
400 without writes. Updates use transactions and lock the user's row. Only the
verified UID's own profile can be changed; invalid tokens return 401 and inactive
accounts 403. Missing preferences are created when saving preferences. No trial
or subscription is created. Frontend wiring remains pending; its free-trial page
is a separate UI flow and is not a billing entitlement.

## Plane pattern

Reference: [Plane signup endpoint](https://github.com/makeplane/plane/blob/preview/apps/api/plane/authentication/views/app/email.py)
and [credential provider](https://github.com/makeplane/plane/blob/preview/apps/api/plane/authentication/provider/credentials/email.py).

- `accounts/views.py`: `SignUpAuthEndpoint`, `SignInAuthEndpoint`, and `ForgotPasswordAuthEndpoint`, validation and HTTP responses.
- `accounts/authentication.py`: `FirebaseProvider.authenticate`, identity verification.
- `accounts/services.py`: transactional user provisioning and `post_user_auth_workflow`.
- `accounts/serializers.py`: request validation and explicit public response fields.
- `accounts/models.py`: local user and preferences; unusable Django passwords.

This is an original implementation following Plane's endpoint/provider/workflow
separation. Plane uses credential providers, Django sessions and redirects; this
API uses Firebase identity and JSON for the mobile client. It does not reproduce
Plane's entire adapter hierarchy or copy its implementation.

## Validation and deployment limits

```sh
uv run python manage.py test apps.accounts
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run ruff check apps/accounts config manage.py
```

Tests mock Firebase verification; real-project credentials and a live Firebase
integration check are still required. Tests use SQLite; run them against an
isolated PostgreSQL test database before deployment. The default DRF throttle is
10 requests/minute per direct client IP, using process-local cache. Configure a
shared cache, trusted proxy/IP handling, and ingress rate limits when deploying
multiple workers. DRF throttles alone are not abuse protection. HTTPS is required;
configure HTTPS termination/forwarded headers only for a trusted reverse proxy.
Other app folders remain empty scaffolding. Docker is not required or included.

## Task list

`GET /api/v1/planner/tasks/` requires a Firebase Bearer token.
Optional filters: `date=2026-10-27`, `status=Pending` (or `In Progress`, `Completed`,
`Overdue`), and `completed=true|false`. Filters are combined. Pagination uses
`page` and `page_size` (default 20, maximum 100). Returns
`{"count": 0, "next": null, "previous": null, "results": []}` for an empty list.
Unknown, repeated or invalid filters return 400; nonexistent pages return 404.

Each result includes id, title, notes, status, date (YYYY-MM-DD), time (e.g.
`9:00 AM`), category, reminder, completed, period, dashboard, and subtasks
(id/title/completed). Completion is derived from status. Tasks are sorted by date,
time, then ID; only the authenticated user's tasks and their subtasks are returned.
Date/time are the task's local scheduled wall time; no timezone conversion or
automatic overdue calculation is implemented. Reminder is a saved preference;
notification delivery is not yet implemented. Artwork remains a frontend asset
mapping and is not returned. The frontend is not connected yet.

Task/Subtask models and the initial planner migration are included. Run migrations
on deployment. Task mutation endpoints are documented below.
Tests use an isolated SQLite database and mocked Firebase identity; PostgreSQL
and live Firebase integration still need deployment validation.

## Task creation, editing and deletion

All require a Firebase Bearer token and operate only on the authenticated user's
tasks. Missing tasks and other users' tasks both return 404.

`POST /api/v1/planner/tasks/` — returns 201 with the task object.

```json
{"title": "Morning workout", "date": "2026-10-28", "time": "7:00 AM", "category": "Health", "reminder": true}
```

Title, date, and time are required. Optional fields: notes, category, status,
completed, reminder, dashboard, and period. Times accept `HH:MM` (24-hour) or
`h:mm AM/PM`, and responses use the frontend's 12-hour format. New tasks default
to Pending, no reminder, dashboard=true, and no subtasks. POST is not idempotent;
repeating a successful request creates another task.

`PATCH /api/v1/planner/tasks/{id}/` — returns 200 with the updated task.
Send only fields to change, e.g. `{"completed": true}` or
`{"title": "Evening workout", "time": "18:30"}`. Omitted fields are preserved.
Completed=true sets status=Completed; completed=false without a status sets
Pending. If both are supplied, they must agree. Status alone also determines
completed in responses. Empty patches, unknown fields, invalid dates/times, and
blank titles return 400 without changing the task. Owner, ID, artwork, and nested
subtask writes are not accepted. Use the subtask endpoints documented below.

`DELETE /api/v1/planner/tasks/{id}/` — returns 204 with no body. Permanently deletes
the task and its subtasks in a transaction; repeated deletion returns 404.
Updates use row locks and transactions. Reminder delivery, automatic overdue
updates, frontend wiring, and rewards on completion are not implemented here.

## Shared email module

All apps import email helpers from `apps.common.mail`:

```python
from apps.common.mail import send_email

send_email(
    to="user@example.com",
    subject="Welcome to ThrivePlan",
    text="Your account is ready.",
    html="<p>Your account is ready.</p>",  # optional
)
```

`send_email` handles one recipient, plain text, optional HTML and reply_to, and
central sender/backend configuration. It raises MailDeliveryError for transport
failures. Invalid input raises ValidationError/ValueError. Calls are synchronous;
when depending on a database write, call through transaction.on_commit. Escape
untrusted content before using it in HTML. No welcome/reminder/billing emails are
automatically sent by this change.

`send_password_reset_email(email=...)` lives in the same shared module and keeps
Firebase's email delivery and generic account-existence behavior. The forgot-
password endpoint maps delivery failures to a generic HTTP 503. Firebase reset
emails use Firebase's sender/templates, not the SMTP settings.

For general email, local settings default to console output (no actual delivery).
Set EMAIL_BACKEND to django.core.mail.backends.smtp.EmailBackend, configure
DEFAULT_FROM_EMAIL and EMAIL_HOST/PORT/HOST_USER/HOST_PASSWORD for your provider,
and choose either EMAIL_USE_TLS or EMAIL_USE_SSL. EMAIL_TIMEOUT defaults to 10
seconds. `.env.example` contains these options. Tests use in-memory delivery and
mock Firebase HTTP; SMTP credentials and actual delivery have not been tested.

## Subtask mutations

All require a Firebase Bearer token. Parent tasks must belong to the authenticated
user, and subtask IDs must belong to the task in the URL. Unknown, foreign, or
mismatched resources return 404.

- POST `/api/v1/planner/tasks/{task_id}/subtasks/` with
  `{"title": "Research topic"}` returns 201 with `{id, title, completed}`.
  Title is required; completed is optional and defaults to false. New subtasks
  append to the parent's ordered list.
- PATCH `/api/v1/planner/tasks/{task_id}/subtasks/{id}/` with
  `{"completed": true}` or `{"title": "Updated title"}` returns 200 with the
  updated subtask. Omitted fields are preserved.
- DELETE `/api/v1/planner/tasks/{task_id}/subtasks/{id}/` returns 204 without a
  body. The parent task and sibling subtasks remain; repeated deletion returns 404.

Titles are trimmed, nonblank and at most 255 characters. Empty patches and
unknown fields (including task, owner, id, position) return 400. Mutations are
transactional and lock the parent row. Completing subtasks does not automatically
complete their parent or grant rewards. Task lists already include subtasks;
there is no separate subtask list endpoint or frontend integration yet.

## Journal entries

All endpoints require a Firebase Bearer token and scope entries to that user.

- GET `/api/v1/journal/entries/`: paginated `{count, next, previous, results}`,
  newest date/ID first. Optional `mood`, `page`, and `page_size` (20 default,
  100 maximum); invalid/unknown/repeated filters return 400.
- POST `/api/v1/journal/entries/`: creates an entry and returns 201.
- PATCH `/api/v1/journal/entries/{id}/`: edits supplied fields only; returns 200.
- DELETE `/api/v1/journal/entries/{id}/`: permanently removes the entry; returns
  204 without a body. Unknown or foreign IDs return 404 for updates/deletion.

Example create body:

```json
{"thoughts": "Today I made time for myself.", "mood": "Good", "date": "2026-10-27T10:00:00+05:30"}
```

Responses contain `{id, mood, thoughts, date}`, matching the frontend store.
Thoughts are required on creation, trimmed, nonblank, and limited to 10,000
characters. Mood may be Great, Good, Okay, Low, Stressed, or null (default).
Date is an ISO timestamp with a timezone offset or Z; omitted creation dates
use the server's current time. Responses normalize timestamps to UTC. Multiple
entries per day are allowed. PATCH can explicitly clear mood with null.
Empty patches, unknown fields, invalid moods/dates, and blank thoughts return 400.

Updates/deletes are transactional; responses disable caching. Frontend wiring,
journal templates, persistent drafts, voice transcription, and reward points
are not implemented. Run the journal migration on deployment. POST is not
idempotent: retrying a successful create can produce another entry.

## Journal template catalog

GET `/api/v1/journal/templates/` requires a Firebase Bearer token. Returns an
unpaginated array of active shared templates in display order. Each item contains
`id` (stable slug), `title`, `description`, `prompt`, `icon`, and `colors`.
The migration seeds the frontend's eight templates: my-day, gratitude, wins,
mood, goals, reflection, self-care, weekend. Text, line breaks, icons, and colors
match the existing frontend catalog. An empty active catalog returns `[]`.

Templates are database content, not private journal entries. Inactive templates
are excluded. This endpoint is read-only and does not create entries or reward
points. Template editing is not exposed through the API. Frontend wiring
remains pending. Apply migrations on deployment to install the catalog. Rollback
of the seed migration preserves content; rollback of the model migration drops
the table. Reapplying seeds does not overwrite existing template edits.


GET `/api/v1/journal/templates/{id}/` returns one active template with the same
fields as a catalog item. IDs are slugs, for example
`/api/v1/journal/templates/gratitude/`. Requires a Firebase Bearer token.
Missing and inactive templates both return 404. POST/PUT/PATCH/DELETE are not
allowed. This read does not create a journal entry. Frontend wiring is pending.

## Daily wellness

GET `/api/v1/wellness/daily/` requires a Firebase Bearer token. Optional query
parameters are `date=2026-10-28` and `timezone=Asia/Kolkata`. Without date, the
current day in the supplied IANA timezone is used (UTC by default). An explicit
date selects that calendar day directly. Invalid, unknown, or repeated query
parameters return 400.

```json
{"date": "2026-10-28", "timezone": "UTC", "quote": null, "song": null, "books": [], "workout": null, "joke": null}
```

Populated slots contain id, kind, title, description, body, creator,
duration_seconds, media_url, and image_url. `body` contains quote/joke text;
`creator` represents the author/artist; durations are seconds. Books are ordered
by their selection position. This maps to the frontend's four wellness screens
and joke section; artwork and book-cover styling remain frontend concerns.
Favorites and playback/workout progress are not included yet.

WellnessContent stores reusable content; DailyContent schedules a content item
for a date and slot. There is one quote/song/workout/joke per day and multiple
ordered books. Only active content matching its slot kind is returned. Missing
content returns null or an empty books list, with HTTP 200. Content is shared
between authenticated users; GET does not create records or choose random items.

No demo content is published automatically. Populate selections through trusted
backend code, calling full_clean before saving, for example in manage.py shell:

```python
from apps.wellness.models import WellnessContent, DailyContent

content = WellnessContent(kind="quote", title="Daily reflection", body="Your approved text", creator="Your source")
content.full_clean()
content.save()
selection = DailyContent(date="2026-10-28", kind="quote", content=content)
selection.full_clean()
selection.save()
```

There is no public publishing endpoint. The local migration has created the
schema; apply it on deployment as well. Frontend integration, favorites, content
publishing UI, and live media integrations are separate work.

## Wellness favorites

All endpoints require a Firebase Bearer token.

- GET `/api/v1/wellness/favorites/`: returns the user's saved active content in
  `{count, next, previous, results}`. Newest favorites first. Optional `kind`
  (quote/song/book/workout/joke), `page`, and `page_size` (default 20, max 100).
- POST `/api/v1/wellness/favorites/` with `{"content_id": 1}`: returns 201 for a
  new favorite or 200 with the same record on a duplicate save. Database
  uniqueness prevents duplicate user/content pairs. Missing or inactive content
  returns 404. The content ID comes from the daily endpoint's content objects.
- DELETE `/api/v1/wellness/favorites/{id}/`: use the favorite record's ID, not
  content ID. Returns 204 without a body. Missing/foreign favorites return 404;
  repeated deletion returns 404. Deletion preserves the content and other users'
  favorites. A user's favorite can still be removed if its content is inactive.

Favorite records contain `id`, nested `content` (same fields as daily content),
and `created_at`. Inactive content is hidden from lists without deleting saved
records. Invalid/unknown fields and invalid/repeated list filters return 400.
No client-supplied owner is accepted. Favorites are distinct from likes and
workout progress. The frontend still needs API integration. Apply the favorite
migration on deployment; local SQLite tests do not validate PostgreSQL lock
behavior under concurrent load.

## Insights summary

GET `/api/v1/insights/summary/` requires a Firebase Bearer token. Defaults to all
currently stored records owned by that user. Optional `start_date` and `end_date`
must be supplied together as YYYY-MM-DD; both days are included. Optional
`timezone` is an IANA name (UTC default), for example:
`?start_date=2026-10-01&end_date=2026-10-31&timezone=Asia/Kolkata`.

Returns start_date/end_date (null for all-time), timezone, and:

- tasks: total, completed, pending (all unfinished), not_started (Pending status),
  in_progress, overdue, and completion_percentage (0–100, rounded to 2 decimals).
- journal: total_entries, moods (counts for Great/Good/Okay/Low/Stressed), and
  unrecorded_mood (null mood count).

Empty data returns zero counts/percentage. Tasks are filtered by scheduled date,
not creation or completion timestamp. Status reflects the current saved state;
this is not historical completion-event reporting. Journal timestamps are
filtered from local midnight through the exclusive next-day midnight, including
DST boundaries. Mood counts describe journal entries, not distinct days or
medical assessments. No points, streaks, focused-time metrics, or sample values
are fabricated. Deleted records are excluded. The frontend still needs wiring.

Invalid ranges/timezones, unknown or repeated filters return 400. Response caching
is disabled. This endpoint only queries existing task/journal tables and needs
no new model or migration. Multi-query aggregates are not a transactional snapshot
under concurrent writes; PostgreSQL load/concurrency validation remains pending.

## Productivity charts

GET `/api/v1/insights/productivity/` requires a Firebase Bearer token. Accepts
`start_date`, `end_date` (inclusive YYYY-MM-DD, supplied together), and `timezone`
(IANA name, UTC default). Without dates, returns today and the previous six days
in that timezone. Explicit ranges are limited to 366 days. Timezone chooses the
default current day; task scheduled dates are already calendar dates and are
not converted.

Returns start_date, end_date, timezone, summary, and days. Each day contains date,
total, completed, pending (all unfinished statuses), and completion_percentage.
Days are ascending and include zero-filled dates. Summary contains the same
counts and percentage for the whole range. The overall percentage is completed
/ total * 100, not the average of daily percentages. Empty totals yield 0.0.

Statistics use current saved task statuses grouped by scheduled date. They do
not record when tasks were completed, focused time, or historical status changes.
Only the authenticated user's tasks are counted. Invalid/unknown/repeated filters
return 400. GET is read-only, disables caching, and performs one grouped task
query. No migration is needed. Frontend chart integration remains pending.

## Notification inbox

All require a Firebase Bearer token and operate on the authenticated user's inbox.

- GET `/api/v1/notifications/`: paginated `{count, next, previous, results}`,
  newest first. Optional category (Tasks/Mindfulness/System), unread=true|false,
  page, page_size (20 default, max 100). Unknown/repeated/invalid filters return 400.
- PATCH `/api/v1/notifications/{id}/` with `{"unread": false}`: returns 200 with
  the updated notification. Repeated calls preserve the first read timestamp.
  Only marking read is supported; unread=true and other fields return 400.
- POST `/api/v1/notifications/read-all/` with `{}` or an empty body: returns
  `{"updated": 3}`. Updates only this user's unread records created at or before
  the operation's cutoff. Retrying with nothing left returns updated=0.

Notifications contain id, title, message, category, icon, destination, target_id,
created_at, read_at, and unread. Frontend Today/Yesterday/time labels should be
derived from created_at in the user's timezone. target_id is optional and supplied
by trusted notification producers; destination resource APIs must still enforce
ownership. Missing/foreign notifications return 404. Reads disable caching and
do not mark records read automatically. There is no public create/delete API.

The schema is migrated locally but no sample notifications are generated. Future
trusted jobs should validate records with full_clean(), verify target ownership,
and create them for the intended recipient. This change does not implement push
delivery, scheduled reminder jobs, notification settings, or frontend wiring.

## Notification preferences

GET and PATCH `/api/v1/accounts/me/notification-preferences/` require a Firebase
Bearer token. Responses contain `{"daily_reminders": true, "weekly_summary": false}`
with the user's saved values. Defaults match the frontend toggles. GET returns
defaults without writing if the user has no preferences row.

PATCH accepts either or both fields, for example `{"daily_reminders": false}`.
Omitted fields and onboarding preferences are preserved. Empty bodies, unknown
fields, and invalid/null booleans return 400. Updates are transactional and lock
the authenticated user's row. Only that user's settings can be changed; invalid
tokens return 401 and deactivated users 403. Successful GET/PATCH return 200 and
use private/no-store caching. The migration adds defaults to existing accounts.

These APIs persist preferences only. They do not schedule reminders, send weekly
summaries, change OS notification permissions, or delete inbox items. Future
delivery jobs must consult these settings. Frontend integration remains pending.

## Expo Push device registration

POST `/api/v1/notifications/devices/` requires a Firebase Bearer token:

```json
{
  "installation_id": "349de830-a346-45eb-ae63-bdaf38998498",
  "push_token": "ExpoPushToken[example-token]",
  "platform": "android"
}
```

Use a UUID generated and persisted by the mobile app for each installation (not
a hardware ID). platform is android or ios. Send an ExpoPushToken or legacy
ExponentPushToken from the app's Expo project, not a Firebase Auth token, FCM
registration token, or APNs device token. The example token above is illustrative.

Returns 201 when created or 200 when refreshing the same user's installation.
The response contains id, installation_id, platform, created_at, updated_at;
push tokens and owner IDs are not exposed. Resubmit after token changes.
Installation IDs and tokens are globally unique. A conflicting token or an
installation owned by another account returns 409 without transferring ownership.
Concurrent duplicates are protected by unique constraints; retry on a 409 caused
by a registration race. Registration is limited to 10/minute per authenticated
user using the current DRF cache configuration.

DELETE `/api/v1/notifications/devices/{id}/` removes only the authenticated user's
registration and returns 204 without a body. Missing/foreign IDs return 404;
repeated deletion also returns 404. Persist the returned record ID and unregister
BEFORE Firebase logout or account switching. The backend does not automatically
transfer registrations on shared devices. Failed offline logout/unregistration
requires retry or future recovery support before reliable account switching.

This stores tokens only. Token format validation does not prove device ownership,
project membership, OS permission, or deliverability. No push messages are sent.
Frontend token acquisition/refresh listeners, Expo project credentials, delivery
jobs, receipt processing, invalid-token cleanup, and stale-registration cleanup
remain pending. Before enabling delivery, use generic notification text and fetch
private content only after Firebase authentication; never put journal text or
other private records in push payloads. Delivery jobs must honor notification
preferences and active account status. Apply the device migration on deployment.

## Task reminder schedules

All require a Firebase Bearer token and parent-task ownership.

- POST `/api/v1/planner/tasks/{task_id}/reminders/` with
  `{"scheduled_at": "2026-11-01T09:00:00+05:30"}` creates a schedule (201).
  The time must be in the future and include an explicit timezone offset or Z.
  Repeating the same task/time while still future returns the existing record
  (200). Completed tasks reject scheduling. Maximum 20 stored schedules per task.
- GET `/api/v1/planner/tasks/{task_id}/reminders/` returns an array ordered by
  scheduled_at then ID. Records contain id, task_id, scheduled_at (UTC), created_at.
  Empty tasks return `[]`. The list includes elapsed schedules, since delivery
  and expiry cleanup are not implemented yet.
- DELETE `/api/v1/planner/tasks/{task_id}/reminders/{id}/` cancels by deleting the
  schedule (204). Missing, foreign, or mismatched parent/reminder IDs return 404.

Creating a schedule enables the task's reminder flag. Cancelling the final
schedule clears it. Completing a task or PATCHing reminder=false cancels all its
schedules; deleting a task cascades schedules. Reopening a task does not restore
cancelled schedules. Setting reminder=true alone still does not choose a time.
Editing task date/time does not shift explicit reminder times; cancel and recreate
them if needed. Mutations lock the parent row and are transactional.

These endpoints store schedules only: no notification is sent when a time passes.
A future worker must implement delivery/expiry state, safe claiming, retries,
notification preferences, active-user checks, and device delivery. It must share
the parent locking/cancellation rules to coordinate with task updates. Frontend
integration remains pending. Apply the reminder migration on deployment.
