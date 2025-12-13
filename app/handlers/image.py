from typing import Tuple

from fastapi import HTTPException, UploadFile


async def validate_and_process_image(file: UploadFile, max_size_bytes: int) -> Tuple[bytes, str]:
    """
    Validate and process uploaded image file.

    Args:
        file: The uploaded image file
        max_size_bytes: Maximum allowed file size in bytes

    Returns:
        Tuple of (image_bytes, mime_type)

    Raises:
        HTTPException: If validation fails
    """
    # Check file exists
    if not file:
        raise HTTPException(status_code=400, detail="No image file provided")

    # Check content type
    allowed_types = ["image/png", "image/jpeg", "image/jpg"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid image format. Expected PNG or JPEG, got {file.content_type}",
        )

    # Read file content
    image_data = await file.read()

    # Check file size
    if len(image_data) > max_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Image file too large. Max size: {max_size_bytes / (1024 * 1024):.1f}MB",
        )

    # Check if file is not empty
    if len(image_data) == 0:
        raise HTTPException(status_code=400, detail="Image file appears to be empty")

    # Validate image format by checking magic bytes
    try:
        # PNG magic bytes: 89 50 4E 47 0D 0A 1A 0A
        if image_data[:8] == b'\x89PNG\r\n\x1a\n':
            mime_type = "image/png"
        # JPEG magic bytes: FF D8 FF
        elif image_data[:3] == b'\xff\xd8\xff':
            mime_type = "image/jpeg"
        else:
            raise HTTPException(
                status_code=400,
                detail="Invalid image format. File does not match PNG or JPEG format",
            )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing image file: {str(e)}")

    return image_data, mime_type
