import os
import time
from pathlib import Path

from app.config import settings
from app.services.files import cleanup_expired_uploads


CLEANUP_INTERVAL_SECONDS = int(
    os.getenv("CLEANUP_INTERVAL_SECONDS", "300")
)


def main() -> None:
    upload_dir = Path(settings.storage_dir) / "uploads"

    print(f"Cleanup worker started; interval= {CLEANUP_INTERVAL_SECONDS} seconds; upload_dir= {upload_dir}")

    while True:
        try:
            removed_count = cleanup_expired_uploads(upload_dir=upload_dir)
            print("Cleanup completed; removed_sessions=%s", removed_count)
        except Exception as exc:
            print(exc)

        time.sleep(CLEANUP_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
