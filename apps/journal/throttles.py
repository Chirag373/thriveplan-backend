from rest_framework.throttling import UserRateThrottle


class JournalTranscriptionThrottle(UserRateThrottle):
    scope = "journal_transcription"
