from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.common.whisper import TranscriptionUnavailable, transcribe
from apps.journal.models import JournalEntry


class TranscriptionTests(TestCase):
    url = "/api/v1/journal/transcriptions/"

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(firebase_uid="transcribe-user", name="Alex")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def audio(self, name="recording.m4a", content=b"audio"):
        return SimpleUploadedFile(name, content, content_type="audio/mp4")

    @patch("apps.common.whisper.transcribe")
    def test_success_does_not_save_journal(self, provider):
        provider.return_value = {"text": "Hello world", "language": "en", "duration_seconds": 2.5}
        response = self.client.post(
            self.url, {"audio": self.audio(), "language": "en"}, format="multipart"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, provider.return_value)
        self.assertEqual(provider.call_args.kwargs["language"], "en")
        self.assertEqual(JournalEntry.objects.count(), 0)
        self.assertEqual(response["Cache-Control"], "private, no-store")

    @patch("apps.common.whisper.transcribe")
    def test_validation_does_not_run_inference(self, provider):
        for data in [
            {},
            {"audio": self.audio(content=b"")},
            {"audio": self.audio(name="file.exe")},
            {"audio": self.audio(), "language": "english"},
            {"audio": self.audio(), "owner": "other"},
        ]:
            self.assertEqual(self.client.post(self.url, data, format="multipart").status_code, 400)
        provider.assert_not_called()

    @override_settings(WHISPER_MAX_UPLOAD_BYTES=3)
    def test_size_limit(self):
        self.assertEqual(
            self.client.post(self.url, {"audio": self.audio()}, format="multipart").status_code, 400
        )

    def test_authentication_and_method(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(
            APIClient().post(self.url, {"audio": self.audio()}, format="multipart").status_code, 401
        )

    @override_settings(WHISPER_ENABLED=False)
    def test_disabled_engine(self):
        self.assertEqual(
            self.client.post(self.url, {"audio": self.audio()}, format="multipart").status_code, 503
        )

    @patch(
        "apps.common.whisper.transcribe",
        return_value={"text": "", "language": "en", "duration_seconds": 1},
    )
    def test_rate_limit(self, provider):
        for _ in range(5):
            self.assertEqual(
                self.client.post(self.url, {"audio": self.audio()}, format="multipart").status_code,
                200,
            )
        self.assertEqual(
            self.client.post(self.url, {"audio": self.audio()}, format="multipart").status_code, 429
        )
        self.assertEqual(provider.call_count, 5)

    @override_settings(WHISPER_ENABLED=True)
    @patch("apps.common.whisper._get_model")
    @patch("apps.common.whisper._decode_audio")
    def test_lazy_segments_are_consumed_and_tempfile_closed(self, decode, model):
        files = []

        def decoded(recording):
            files.append(recording)
            return "samples", 2.123

        decode.side_effect = decoded
        model.return_value.transcribe.return_value = (
            iter([SimpleNamespace(text=" Hello "), SimpleNamespace(text="world ")]),
            SimpleNamespace(language="en"),
        )
        fake_av = SimpleNamespace(error=SimpleNamespace(FFmpegError=OSError))
        with patch.dict("sys.modules", {"av": fake_av}):
            result = transcribe(audio=self.audio())
        self.assertEqual(
            result, {"text": "Hello world", "language": "en", "duration_seconds": 2.12}
        )
        self.assertTrue(files[0].closed)
        model.return_value.transcribe.assert_called_once_with(
            "samples", language=None, vad_filter=True
        )

    @override_settings(WHISPER_ENABLED=True)
    @patch("apps.common.whisper._decode_audio")
    def test_bad_audio_and_lock_released(self, decode):
        decode.side_effect = OSError("decoder details must not leak")
        fake_av = SimpleNamespace(error=SimpleNamespace(FFmpegError=OSError))
        with patch.dict("sys.modules", {"av": fake_av}):
            with self.assertRaises(ValidationError):
                transcribe(audio=self.audio())
            decode.side_effect = None
            decode.return_value = ("samples", 1)
            with (
                patch("apps.common.whisper._get_model", side_effect=RuntimeError("missing model")),
                self.assertRaises(TranscriptionUnavailable),
            ):
                transcribe(audio=self.audio())
