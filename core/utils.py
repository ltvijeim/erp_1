from typing import Any
import uuid

def clean_uuid_for_ltree(raw_uuid: uuid.UUID) -> str:
    """
    The ltree extension expects labels to match the regex ^[A-Za-z0-9_]{1,256}$.
    Raw UUIDs contain hyphens which are illegal in ltree.
    This utility strips hyphens to generate a clean, safe hexadecimal string.
    """
    return str(raw_uuid).replace('-', '')

def build_error_response(message: str, code: str, details: dict[str, Any] = None) -> dict[str, Any]:
    """
    Standardizes the error payload structure returned by all JsonResponse handlers
    across the 11 domain bounded contexts.
    """
    payload = {
        "error": {
            "code": code,
            "message": message
        }
    }
    if details:
        payload["error"]["details"] = details
    return payload