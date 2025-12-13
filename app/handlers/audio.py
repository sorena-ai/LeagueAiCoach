from typing import Tuple

from fastapi import HTTPException, UploadFile


def detect_audio_format(data: bytes) -> str:
    """
    Detect audio format from magic bytes.

    Returns MIME type string like 'audio/wav', 'audio/mp4', etc.
    """
    # WAV: RIFF....WAVE
    if data[:4] == b'RIFF' and data[8:12] == b'WAVE':
        return "audio/wav"

    # MP3: ID3 or FF FB/FF F3/FF F2
    if data[:3] == b'ID3' or (data[0] == 0xFF and data[1] in [0xFB, 0xF3, 0xF2]):
        return "audio/mp3"

    # MP4/M4A: ftyp
    if data[4:8] == b'ftyp':
        return "audio/mp4"

    # AAC: FF F1 or FF F9
    if data[:2] == b'\xFF\xF1' or data[:2] == b'\xFF\xF9':
        return "audio/aac"

    # OGG: OggS
    if data[:4] == b'OggS':
        return "audio/ogg"

    # FLAC: fLaC
    if data[:4] == b'fLaC':
        return "audio/flac"

    return None


async def validate_and_process_audio(file: UploadFile, max_size_bytes: int) -> Tuple[bytes, str]:
    """
    Validate and process uploaded audio file.

    Supports: WAV, MP3, MP4, AAC, OGG, FLAC (formats compatible with Gemini)

    Args:
        file: The uploaded audio file
        max_size_bytes: Maximum allowed file size in bytes

    Returns:
        Tuple of (audio_bytes, mime_type)

    Raises:
        HTTPException: If validation fails
    """
    # Check file exists
    if not file:
        raise HTTPException(status_code=400, detail="No audio file provided")

    # Read file content
    audio_data = await file.read()

    # Check file size
    if len(audio_data) > max_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Audio file too large. Max size: {max_size_bytes / (1024 * 1024):.1f}MB",
        )

    # Check if file is not empty
    if len(audio_data) == 0:
        raise HTTPException(status_code=400, detail="Audio file appears to be empty")

    # Detect actual audio format from magic bytes
    detected_format = detect_audio_format(audio_data)

    if not detected_format:
        raise HTTPException(
            status_code=400,
            detail="Unsupported audio format. Supported formats: WAV, MP3, MP4, AAC, OGG, FLAC",
        )

    return audio_data, detected_format
