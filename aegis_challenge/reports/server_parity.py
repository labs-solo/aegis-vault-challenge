from __future__ import annotations

import json

from aegis_challenge.leaderboard import write_server_parity_report


def main() -> int:
    print(json.dumps(write_server_parity_report("reports/leaderboard"), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
