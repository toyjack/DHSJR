# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "supabase>=2.25.0",
#     "python-dotenv>=1.0.0",
# ]
# ///
"""DHSJR データインポートツール

TSV ファイルを Supabase の dhsjr テーブルにインポートする。
デフォルトでインポート前にテーブルをクリアする（--no-clear で無効化可能）。
"""

import argparse
import csv
import os
import sys
import time
from typing import Dict, Iterator, List

from supabase import Client

from common import create_supabase_client

DEFAULT_FILE = "DHSJR_data_all.tsv"
DEFAULT_TABLE = "dhsjr"
DEFAULT_BATCH_SIZE = 1000
MAX_RETRIES = 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DHSJR データインポートツール")
    parser.add_argument(
        "-f", "--file",
        default=os.environ.get("TSV_FILE", DEFAULT_FILE),
        help=f"インポートする TSV ファイルパス (デフォルト: {DEFAULT_FILE})",
    )
    parser.add_argument(
        "-t", "--table",
        default=os.environ.get("TABLE_NAME", DEFAULT_TABLE),
        help=f"ターゲットテーブル名 (デフォルト: {DEFAULT_TABLE})",
    )
    parser.add_argument(
        "-b", "--batch-size",
        type=int,
        default=int(os.environ.get("BATCH_SIZE", str(DEFAULT_BATCH_SIZE))),
        help=f"バッチサイズ (デフォルト: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="インポート前のテーブルクリアをスキップする",
    )
    return parser.parse_args()


def get_file_info(file_path: str) -> tuple[int, int]:
    """ファイルサイズとデータ行数を取得する"""
    file_size = os.path.getsize(file_path)
    with open(file_path, "r", encoding="utf-8") as f:
        line_count = sum(1 for _ in f) - 1  # ヘッダーを除く
    return file_size, line_count


def process_row(row: Dict[str, str]) -> Dict[str, str | None]:
    """1行のデータをクリーニングする（空文字列・NULLをNoneに変換）"""
    processed = {}
    for key, value in row.items():
        if isinstance(value, str):
            value = value.strip()
            if value == "" or value == "NULL":
                value = None
        processed[key] = value
    return processed


def read_tsv_in_batches(file_path: str, batch_size: int) -> Iterator[List[Dict]]:
    """TSV ファイルをバッチごとに読み込む"""
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        batch: list[Dict] = []

        for row in reader:
            processed = process_row(row)
            if processed:
                batch.append(processed)

            if len(batch) >= batch_size:
                yield batch
                batch = []

        if batch:
            yield batch


def insert_batch(supabase: Client, table_name: str, batch: List[Dict]) -> None:
    """バッチデータを挿入する（リトライ付き）"""
    for attempt in range(MAX_RETRIES):
        try:
            supabase.table(table_name).insert(batch).execute()
            return
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait_time = (attempt + 1) * 2
                print(f"  ⚠️  挿入失敗、{wait_time}秒後にリトライ... エラー: {e}")
                time.sleep(wait_time)
            else:
                raise


def clear_table(supabase: Client, table_name: str) -> None:
    """テーブルの全行を削除する（テーブルが存在しない場合はスキップ）"""
    print(f"🗑️  テーブル {table_name} をクリア中...")
    try:
        supabase.table(table_name).select("ID", count="exact").limit(0).execute()
    except Exception:
        print(f"⏭️  テーブル {table_name} が存在しません。クリアをスキップします")
        return
    supabase.table(table_name).delete().gte("ID", "").execute()
    print(f"✅ テーブル {table_name} をクリアしました")


def main() -> None:
    args = parse_args()

    print("=" * 60)
    print("DHSJR データインポートツール")
    print("=" * 60)
    print()

    # ファイル確認
    if not os.path.exists(args.file):
        print(f"❌ エラー: ファイル {args.file} が見つかりません")
        sys.exit(1)

    file_size, line_count = get_file_info(args.file)
    print(f"📁 ファイル: {args.file}")
    print(f"📊 ファイルサイズ: {file_size / (1024 * 1024):.2f} MB")
    print(f"📝 データ行数: {line_count:,} 行")
    print(f"🎯 ターゲットテーブル: {args.table}")
    print(f"📦 バッチサイズ: {args.batch_size} 行/バッチ")
    print()

    # Supabase 接続
    print("🔌 Supabase に接続中...")
    supabase = create_supabase_client()
    print("✅ 接続成功")
    print()

    # テーブルクリア
    if not args.no_clear:
        clear_table(supabase, args.table)
        print()

    print("=" * 60)
    print("データインポート開始")
    print("=" * 60)
    print()

    total_rows = 0
    batch_count = 0
    start_time = time.time()

    try:
        for batch in read_tsv_in_batches(args.file, args.batch_size):
            batch_count += 1
            batch_len = len(batch)

            print(f"📦 バッチ {batch_count}: {batch_len} 行を処理中...")
            insert_batch(supabase, args.table, batch)

            total_rows += batch_len
            elapsed = time.time() - start_time
            speed = total_rows / elapsed if elapsed > 0 else 0
            progress = (total_rows / line_count * 100) if line_count > 0 else 0

            print(
                f"✅ 成功: {total_rows:,}/{line_count:,} 行 ({progress:.1f}%) | "
                f"速度: {speed:.0f} 行/秒"
            )
            print()

        elapsed_time = time.time() - start_time
        print("=" * 60)
        print("✨ インポート完了!")
        print("=" * 60)
        print(f"📊 総行数: {total_rows:,} 行")
        print(f"📦 総バッチ数: {batch_count}")
        print(f"⏱️  所要時間: {elapsed_time:.2f} 秒 ({elapsed_time / 60:.2f} 分)")
        if elapsed_time > 0:
            print(f"⚡ 平均速度: {total_rows / elapsed_time:.0f} 行/秒")
        print("=" * 60)

    except Exception as e:
        print()
        print("=" * 60)
        print(f"❌ エラー発生: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()