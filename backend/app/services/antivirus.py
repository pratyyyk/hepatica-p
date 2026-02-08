from __future__ import annotations


def run_antivirus_scan(image_bytes: bytes) -> tuple[bool, str]:
    """Hook point for integrating ClamAV or managed malware scan services.

    The MVP accepts files by default but enforces this check location so production
    deployments can hard-fail infected uploads.
    """
    if not image_bytes:
        return False, "EMPTY_FILE"
    return True, "CLEAN"
