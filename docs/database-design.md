# Database design and implementation status

Architecture: Expo -> Django REST API -> PostgreSQL. Firebase manages app-user
identity; Django stores the unique Firebase UID and owns application permissions.

The folder structure is implemented. Domain models below are the proposed design,
except User/UserPreferences, which exist with an initial migration.

| App | Models | Status |
|---|---|---|
| accounts | User, UserPreferences | Implemented |
| common | TimestampedModel, OwnedModel | Abstract base models |
| planner | Task, Subtask, Reminder | Planned |
| journal | JournalEntry, JournalTemplate | Planned |
| wellness | WellnessContent, DailyContent, ContentInteraction | Planned |
| rewards | PointTransaction | Planned |
| billing | SubscriptionPlan, Subscription, PaymentTransaction, BillingEvent | Planned |
| notifications | Notification, Device, NotificationDelivery | Planned |
| insights | Aggregate queries across other apps | No dedicated model initially |

Use integer BigAutoField IDs to fit current numeric frontend task IDs. They are
identifiers, not authorization: every private query must enforce ownership.
Firebase UID remains a separate unique string, nullable for staff-only accounts.

Planner/dashboard share tasks. Store one canonical completion status and an
associated completed_at value; derive overdue from the due date/time. Subtasks
need explicit ordering. Reminder timing is independent of task due timing.

Journal drafts and published entries can share one table. Entries can reference
a template and an optional quote, preserving prompt text as a snapshot. Compute
streaks from distinct published local dates. Validate timezone identifiers.

Store wellness content centrally, with a content kind, common typed fields, and
validated type-specific metadata. Daily schedules reference shared content;
likes/bookmarks have a unique user/content pair.

Points use an append-only event ledger with retry-safe unique event keys. Define
award/reversal rules before implementation: current frontend points are samples.
Progress/charts aggregate source records rather than storing sample percentages.

Billing keeps provider IDs, verified events, amounts in minor units, and currency.
Select the provider/purchase flow before finalizing models. Define retention and
account deletion deliberately; do not casually cascade billing history. Never
store card numbers/CVV. Trial/premium access is controlled by server-side rules.

Separate notification inbox records, device tokens, and delivery attempts. A
saved alarm preference does not by itself schedule or play a device alarm.

Habits, standalone mood check-ins, and focused-time sessions remain future work:
the reviewed frontend has placeholder flows or sample metrics for these areas.
