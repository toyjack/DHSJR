#!/usr/bin/env python3
"""Compare two DHSJR tables through the read-only PostgREST API."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


IMPORT_FIELDS = (
    "ID",
    "資料番号",
    "資料名",
    "資料内漢字番号",
    "資料内漢語番号",
    "単字_見出し",
    "単字_出現形",
    "漢語_見出し",
    "漢語_出現形",
    "漢語_alphabet",
    "語種",
    "漢語内位置",
    "単字長",
    "声点",
    "声点型",
    "仮名注",
    "仮名型",
    "反切",
    "類音",
    "節博士",
    "その他",
    "出現位置",
    "備考",
)


def load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE entries without printing their values."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


class PostgrestReader:
    def __init__(self, base_url: str, service_key: str, retries: int = 3) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Accept": "application/json",
            # Some reverse proxies reject urllib's default Python-urllib agent.
            "User-Agent": "DHSJR-read-only-table-compare/1.0",
        }
        self.retries = retries

    def _get(self, table: str, start: int, end: int, exact_count: bool = False):
        query = urlencode({"select": ",".join(IMPORT_FIELDS), "order": "ID.asc"})
        request = Request(
            f"{self.base_url}/rest/v1/{table}?{query}",
            headers={
                **self.headers,
                "Range": f"{start}-{end}",
                **({"Prefer": "count=exact"} if exact_count else {}),
            },
            method="GET",
        )
        for attempt in range(1, self.retries + 1):
            try:
                with urlopen(request, timeout=60) as response:
                    return json.load(response), response.headers.get("Content-Range")
            except (HTTPError, URLError, TimeoutError) as exc:
                if attempt == self.retries:
                    raise RuntimeError(
                        f"Failed to read {table} rows {start}-{end}"
                    ) from exc
                time.sleep(attempt * 2)
        raise AssertionError("unreachable")

    def count(self, table: str) -> int:
        _, content_range = self._get(table, 0, 0, exact_count=True)
        if not content_range or "/" not in content_range:
            raise RuntimeError(f"No exact count returned for {table}")
        return int(content_range.rsplit("/", 1)[1])

    def read_all(self, table: str, batch_size: int, workers: int) -> dict[str, dict]:
        count = self.count(table)
        ranges = [
            (start, min(start + batch_size - 1, count - 1))
            for start in range(0, count, batch_size)
        ]
        rows_by_id: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._get, table, start, end): (start, end)
                for start, end in ranges
            }
            completed = 0
            for future in as_completed(futures):
                rows, _ = future.result()
                for row in rows:
                    row_id = row["ID"]
                    if row_id in rows_by_id:
                        raise RuntimeError(f"Duplicate ID in {table}: {row_id}")
                    rows_by_id[row_id] = row
                completed += 1
                if completed % 50 == 0 or completed == len(ranges):
                    print(
                        f"  {table}: {min(completed * batch_size, count):,}/{count:,}",
                        file=sys.stderr,
                    )
        if len(rows_by_id) != count:
            raise RuntimeError(
                f"{table}: fetched {len(rows_by_id):,} unique IDs, expected {count:,}"
            )
        return rows_by_id


def compare_rows(
    staging: dict[str, dict[str, Any]], production: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    staging_ids = set(staging)
    production_ids = set(production)
    added_ids = sorted(staging_ids - production_ids)
    removed_ids = sorted(production_ids - staging_ids)
    changed_ids: list[str] = []
    field_changes: Counter[str] = Counter()

    for row_id in sorted(staging_ids & production_ids):
        staging_row = staging[row_id]
        production_row = production[row_id]
        changed_fields = [
            field
            for field in IMPORT_FIELDS
            if staging_row.get(field) != production_row.get(field)
        ]
        if changed_fields:
            changed_ids.append(row_id)
            field_changes.update(changed_fields)

    return {
        "staging_rows": len(staging),
        "production_rows": len(production),
        "added_count": len(added_ids),
        "added_ids": added_ids,
        "removed_count": len(removed_ids),
        "removed_ids": removed_ids,
        "changed_row_count": len(changed_ids),
        "changed_ids": changed_ids,
        "field_change_counts": {
            field: field_changes[field] for field in IMPORT_FIELDS
        },
    }


def summary_report(report: dict[str, Any], sample_size: int = 20) -> dict[str, Any]:
    """Keep console output useful without emitting thousands of changed IDs."""
    summary = {key: value for key, value in report.items() if key != "changed_ids"}
    summary["changed_id_sample"] = report["changed_ids"][:sample_size]
    summary["changed_ids_truncated"] = len(report["changed_ids"]) > sample_size
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staging-table", default="dhsjr_staging")
    parser.add_argument("--production-table", default="dhsjr")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.batch_size <= 0 or args.batch_size > 1000:
        raise SystemExit("--batch-size must be between 1 and 1000")
    if args.workers <= 0 or args.workers > 16:
        raise SystemExit("--workers must be between 1 and 16")

    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env")
    base_url = os.environ.get("SUPABASE_URL_ENV")
    service_key = os.environ.get("SUPABASE_SERVICE_KEY_ENV")
    if not base_url or not service_key:
        raise SystemExit(
            "SUPABASE_URL_ENV and SUPABASE_SERVICE_KEY_ENV are required"
        )

    reader = PostgrestReader(base_url, service_key)
    print("Reading staging table...", file=sys.stderr)
    staging = reader.read_all(args.staging_table, args.batch_size, args.workers)
    print("Reading production table...", file=sys.stderr)
    production = reader.read_all(args.production_table, args.batch_size, args.workers)
    report = compare_rows(staging, production)
    print(json.dumps(summary_report(report), ensure_ascii=False, indent=2))
    if args.output:
        args.output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Full report written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
