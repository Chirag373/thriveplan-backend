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
