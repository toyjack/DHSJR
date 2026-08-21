#!/usr/bin/env python3
"""Invoke the installed atomic DHSJR staging promotion function."""

import argparse


CONFIRMATION = "IMPORT_PRODUCTION"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", default="DHSJR_data_all.tsv")
    parser.add_argument("--confirm", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit(f"Production promotion requires --confirm {CONFIRMATION}")

    from common import create_supabase_client
    from import_dhsjr import get_file_info

    _, expected_count = get_file_info(args.file)
    client = create_supabase_client()

    staging = (
        client.table("dhsjr_staging")
        .select("ID", count="exact")
        .limit(0)
        .execute()
    )
    if staging.count != expected_count:
        raise SystemExit(
            f"Staging has {staging.count:,} rows; expected {expected_count:,}"
        )

    result = client.rpc(
        "promote_dhsjr_staging",
        {"expected_count": expected_count, "confirmation": args.confirm},
    ).execute()
    print(f"Atomic production promotion completed: {result.data}")


if __name__ == "__main__":
    main()
