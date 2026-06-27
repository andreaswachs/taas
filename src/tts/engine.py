import asyncio
import threading
import time
import uuid
from pathlib import Path
import logging
from enum import Enum

from pydantic import BaseModel

from ..db.schema import TtsRequestPayload
from ..api.config import get_settings

logger = logging.getLogger(__name__)


class AudioFormat(str, Enum):
    WAV = "wav"
    FLAC = "flac"
    OPUS = "opus"


class GenerationResult(BaseModel):
    task_id: str
    audio_data: bytes
    sample_rate: int
    format: AudioFormat
    duration_seconds: float


class KittenTTSModelWrapper:
    def __init__(self):
        self._model = None
        self._lock = asyncio.Lock()
        # Threading lock to serialize KittenTTS inference calls.
        # KittenTTS's internal espeak-ng phonemizer is not thread-safe,
        # so concurrent model.generate() calls corrupt global state.
        self._inference_lock = threading.Lock()
    
    async def get_model(self) -> any:
        if self._model is None:
            async with self._lock:
                if self._model is None:
                    from kittentts import KittenTTS
                    settings = get_settings()
                    
                    logger.info("Loading KittenTTS model", extra={"model": settings.kitten_model})
                    self._model = await asyncio.to_thread(KittenTTS, settings.kitten_model)
                    logger.info("KittenTTS model loaded", extra={"model": settings.kitten_model})
        
        return self._model
    
    def _generate_locked(self, text: str, voice: str, speed: float, clean_text: bool):
        """Run model.generate() under the inference lock.
        
        Must be called inside asyncio.to_thread() so the lock acquisition
        happens in the worker thread, avoiding event-loop blocking.
        """
        with self._inference_lock:
            return self._model.generate(
                text,
                voice=voice,
                speed=speed,
                clean_text=clean_text
            )
    
    async def generate_with_format(
        self, 
        payload: TtsRequestPayload, 
        format: AudioFormat = AudioFormat.WAV
    ) -> GenerationResult:
        logger.info(
            "Generating TTS",
            extra={
                "text_length": len(payload.text),
                "voice": payload.voice,
                "speed": payload.speed,
                "clean_text": payload.clean_text,
                "format": format.value,
            },
        )
        
        await self.get_model()
        task_id = str(uuid.uuid4())
        
        start_time = time.time()
        
        audio_array = await asyncio.to_thread(
            self._generate_locked,
            payload.text,
            voice=payload.voice,
            speed=payload.speed,
            clean_text=payload.clean_text
        )
        
        duration = time.time() - start_time
        
        audio_bytes = await self._audio_array_to_bytes(audio_array, format)
        result = GenerationResult(
            task_id=task_id,
            audio_data=audio_bytes,
            sample_rate=24000,
            format=format,
            duration_seconds=duration,
        )
        
        logger.info(
            "TTS generation completed",
            extra={
                "task_id": task_id,
                "duration": duration,
                "size_bytes": len(audio_bytes),
                "format": format.value,
            },
        )
        
        return result
    
    async def generate_to_file(
        self, 
        task_id: str,
        payload: TtsRequestPayload,
        file_path: Path
    ) -> str:
        logger.info("Generating TTS to file", extra={"task_id": task_id, "file_path": str(file_path)})
        
        await self.get_model()
        
        audio_array = await asyncio.to_thread(
            self._generate_locked,
            payload.text,
            voice=payload.voice,
            speed=payload.speed,
            clean_text=payload.clean_text
        )
        
        await self._write_audio_file(audio_array, file_path)
        
        logger.info("TTS generation completed to file", extra={"task_id": task_id, "file_path": str(file_path)})
        return str(file_path)
    
    async def _audio_array_to_bytes(self, audio_array: any, format: AudioFormat) -> bytes:
        logger.debug("Converting audio array to bytes", extra={"format": format.value})
        
        settings = get_settings()
        
        if format == AudioFormat.WAV:
            import soundfile as sf
            import io
            
            buffer = io.BytesIO()
            sf.write(buffer, audio_array, settings.sample_rate, subtype='FLOAT')
            return buffer.getvalue()
        
        elif format == AudioFormat.FLAC:
            import soundfile as sf
            import io
            
            buffer = io.BytesIO()
            sf.write(buffer, audio_array, settings.sample_rate, subtype='FLAC')
            return buffer.getvalue()
        
        else:
            raise ValueError(f"Unsupported audio format: {format}")
    
    async def _write_audio_file(self, audio_array: any, file_path: Path) -> None:
        logger.debug("Writing audio file", extra={"file_path": str(file_path)})
        
        settings = get_settings()
        
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        import soundfile as sf
        sf.write(str(file_path), audio_array, settings.sample_rate, subtype='FLOAT')
    
    async def generate_progress(
        self,
        payload: TtsRequestPayload,
        progress_callback,
        format: AudioFormat = AudioFormat.WAV
    ) -> GenerationResult:
        logger.info("Starting progress-based TTS generation", extra={"text_preview": payload.text[:100]})
        
        await self.get_model()
        task_id = str(uuid.uuid4())
        start_time = time.time()
        
        try:
            audio_array = await asyncio.to_thread(
                self._generate_locked,
                payload.text,
                voice=payload.voice,
                speed=payload.speed,
                clean_text=payload.clean_text
            )
        except Exception as e:
            logger.error("TTS generation failed", extra={"error": str(e), "task_id": task_id})
            await progress_callback("Error", str(e), task_id)
            raise
        
        await progress_callback("Processing", "Model inference complete", task_id)
        
        audio_bytes = await self._audio_array_to_bytes(audio_array, format)
        duration = time.time() - start_time
        
        await progress_callback("Converting", "Audio format conversion", task_id)
        
        result = GenerationResult(
            task_id=task_id,
            audio_data=audio_bytes,
            sample_rate=24000,
            format=format,
            duration_seconds=duration,
        )
        
        await progress_callback("Complete", f"Generated {len(audio_bytes)} bytes", task_id)
        
        logger.info("Progress-based TTS generation completed", extra={"task_id": task_id, "duration": duration})
        return result
