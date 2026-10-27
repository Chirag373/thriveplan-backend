# Database design proposal

Status: Firebase-backed signup is implemented with User and UserPreferences.
Other app models remain proposals and their source files are placeholders.

Architecture: Expo -> Firebase Authentication -> Django REST API -> PostgreSQL
(SQLite for local development). Signup provisions local records by verified UID.
See README.md for the API contract and current limitations.

| App | Proposed models |
|---|---|
| accounts | User, UserPreferences |
| common | Shared timestamp and ownership base models |
| planner | Task, Subtask, Reminder |
| journal | JournalEntry, JournalTemplate |
| wellness | WellnessContent, DailyContent, ContentInteraction |
| rewards | PointTransaction |
| billing | SubscriptionPlan, Subscription, PaymentTransaction, BillingEvent |
| notifications | Notification, Device, NotificationDelivery |
| insights | Aggregate queries; no dedicated model initially |

Private records require ownership checks. Link Firebase identities by verified
UID. Use consistent task completion rules and local calendar dates for streaks.
Keep reward and billing events transactional and retry-safe. Define payment,
retention, and notification-delivery requirements before implementation. Habits,
standalone mood, and focused-time workflows still need further definition.

Signup has a new test suite. Historical tests for removed domain implementations
do not apply. Docker files remain removed.
