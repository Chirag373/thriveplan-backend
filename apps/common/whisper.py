"""Local Whisper inference. Audio is never sent to an external transcription API."""

from functools import lru_cache
from tempfile import TemporaryFile
from threading import Lock

from django.conf import settings
from rest_framework.exceptions import APIException, ValidationError

_inference_lock = Lock()


class TranscriptionUnavailable(APIException):
    status_code = 503
    default_detail = "Transcription is temporarily unavailable. Please try again later."
    default_code = "transcription_unavailable"


@lru_cache(maxsize=1)
def _get_model():
    from faster_whisper import WhisperModel

    return WhisperModel(
        settings.WHISPER_MODEL,
        device=settings.WHISPER_DEVICE,
        compute_type=settings.WHISPER_COMPUTE_TYPE,
        local_files_only=True,
        cpu_threads=settings.WHISPER_CPU_THREADS,
    )


def _decode_audio(audio):
    import av
    import numpy as np

    chunks = []
    samples = 0
    with av.open(audio) as container:
        if not container.streams.audio:
            raise ValidationError({"audio": "The file contains no audio stream."})
        resampler = av.AudioResampler(format="flt", layout="mono", rate=16000)
        for frame in container.decode(audio=0):
            for output in resampler.resample(frame):
                samples += output.samples
                if samples > settings.WHISPER_MAX_SECONDS * 16000:
                    raise ValidationError({"audio": "The recording exceeds the duration limit."})
                chunks.append(output.to_ndarray().reshape(-1))
        for output in resampler.resample(None):
            samples += output.samples
            if samples > settings.WHISPER_MAX_SECONDS * 16000:
                raise ValidationError({"audio": "The recording exceeds the duration limit."})
            chunks.append(output.to_ndarray().reshape(-1))
    if not samples:
        raise ValidationError({"audio": "The recording is empty or cannot be decoded."})
    return np.concatenate(chunks), samples / 16000


def transcribe(*, audio, language=None):
    if not settings.WHISPER_ENABLED:
        raise TranscriptionUnavailable()
    if not _inference_lock.acquire(blocking=False):
        raise TranscriptionUnavailable("Transcription is busy. Please try again shortly.")
    try:
        try:
            import av
        except ImportError:
            raise TranscriptionUnavailable() from None
        # Anonymous temporary files are closed on both successful and failed requests.
        with TemporaryFile() as recording:
            for chunk in audio.chunks():
                recording.write(chunk)
            recording.seek(0)
            try:
                samples, duration = _decode_audio(recording)
            except (av.error.FFmpegError, ValueError, EOFError):
                raise ValidationError(
                    {"audio": "Upload a valid, decodable audio recording."}
                ) from None
            try:
                model = _get_model()
            except (ImportError, OSError, RuntimeError, ValueError):
                raise TranscriptionUnavailable() from None
            try:
                segments, info = model.transcribe(samples, language=language, vad_filter=True)
                text = " ".join(segment.text.strip() for segment in segments).strip()
            except ValueError:
                raise ValidationError({"language": "Unsupported transcription language."}) from None
            except RuntimeError:
                raise TranscriptionUnavailable() from None
        return {"text": text, "language": info.language, "duration_seconds": round(duration, 2)}
    finally:
        _inference_lock.release()
