from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path

from backend.config import load_env
from backend.server import build_snapshot


DEFAULT_OUTPUT = Path("public/api/v1/markets/seoul/snapshot.json")
REQUIRED_SECRETS = (
    "DATA_GO_KR_SERVICE_KEY",
    "ECOS_API_KEY",
    "HOUSTAT_API_KEY",
)


def validate_snapshot(snapshot: dict, require_live: bool = False) -> None:
    required = {"market", "score", "asOf", "history", "indicators", "dataMode"}
    missing = required - snapshot.keys()
    if missing:
        raise ValueError(f"Snapshot missing fields: {', '.join(sorted(missing))}")
    if not 0 <= int(snapshot["score"]) <= 100:
        raise ValueError("Snapshot score must be between 0 and 100")
    indicators = snapshot["indicators"]
    ids = {item.get("id") for item in indicators}
    expected = {"pir", "volume", "unpopular", "subscription", "rate", "supply"}
    if ids != expected:
        raise ValueError(f"Unexpected indicator ids: {sorted(ids)}")
    if not snapshot["history"] or len(snapshot["history"]) != len(snapshot.get("historyLabels", [])):
        raise ValueError("Composite history and labels must be non-empty and aligned")
    if require_live and snapshot["dataMode"] not in {"live", "partialLive"}:
        raise ValueError(f"Expected API-backed snapshot, got {snapshot['dataMode']}")
    if require_live and int(snapshot.get("liveIndicatorCount") or 0) < 5:
        raise ValueError("Production snapshot must contain at least five live indicators")


def export_snapshot(output: Path, month: str | None, require_live: bool) -> dict:
    snapshot = build_snapshot(month)
    snapshot["generatedAt"] = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    validate_snapshot(snapshot, require_live=require_live)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)
    return snapshot


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Export the GoJump static JSON API")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--month", help="MOLIT query month, YYYYMM")
    parser.add_argument("--require-live", action="store_true")
    args = parser.parse_args()
    if args.require_live:
        missing = [name for name in REQUIRED_SECRETS if not os.getenv(name)]
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
    snapshot = export_snapshot(args.output, args.month, args.require_live)
    print(
        f"Exported {args.output} "
        f"({snapshot['dataMode']}, score={snapshot['score']}, generatedAt={snapshot['generatedAt']})"
    )


if __name__ == "__main__":
    main()
