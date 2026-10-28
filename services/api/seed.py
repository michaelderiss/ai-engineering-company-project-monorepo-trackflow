from __future__ import annotations

import sys

from services.api.database import seed_suppliers


def main() -> int:
    try:
        inserted = seed_suppliers()
    except (OSError, ValueError, KeyError, TypeError):
        print("Could not seed suppliers. Check database access and stored data, then try again.", file=sys.stderr)
        return 1
    print(f"Seeder finished. Inserted {inserted} supplier records.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
