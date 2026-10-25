"""Bounded, one-shot provider connectivity probe.

Makes at most one minimal request per configured provider, applies the timeouts
inherited from the production adapters, performs no retries, and never prints
API keys, request URLs, or authorization headers. Credentials are loaded only
from the uncommitted ``code/.env`` file.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_CODE_DIR = Path(__file__).resolve().parents[1]
if str(_CODE_DIR) not in sys.path:
    sys.path.insert(0, str(_CODE_DIR))

from ghostdata.runtime.providers import (  # noqa: E402
    PROVIDERS,
    ProviderRouter,
    RuntimeModelError,
)

_ENV_PATH = _CODE_DIR / ".env"


def _key_present(config) -> bool:
    return bool(os.environ.get(config.api_key_env))


def main() -> int:
    load_dotenv(_ENV_PATH, override=False)

    print("Provider credential presence (values are never printed):")
    for name, config in PROVIDERS.items():
        print(f"  {name}: {'present' if _key_present(config) else 'absent'}")

    if not any(_key_present(config) for config in PROVIDERS.values()):
        print("No provider credentials available; skipping live requests.")
        return 0

    print("\nIssuing at most one minimal request per configured provider...")
    router = ProviderRouter()
    messages = [{"role": "user", "content": "Hello"}]
    try:
        response = router.complete(messages)
        print(f"Usable response from {response.provider} ({response.model}):")
        print(f"  {response.text[:80]}")
        print("Live provider result: usable response received.")
    except RuntimeModelError as exc:
        print("No usable live response received.")
        for failure in str(exc).split("; "):
            print(f"  {failure}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
