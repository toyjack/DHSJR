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

# Supabase の dhsjr テーブルに現在存在する列だけを送信する。
# TSV に追加された未マッピング列は、DB マイグレーションが完了するまで無視する。
IMPORT_FIELDS = frozenset({
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
})
REQUIRED_FIELDS = frozenset({"ID", "資料内漢字番号"})


def positive_int(value: str) -> int:
    """argparse用の正整数バリデータ。"""
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("1以上の整数を指定してください")
    return parsed


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
        type=positive_int,
        default=int(os.environ.get("BATCH_SIZE", str(DEFAULT_BATCH_SIZE))),
        help=f"バッチサイズ (デフォルト: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="インポート前のテーブルクリアをスキップする",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="TSVの事前検証だけを実行し、DBへ接続せず終了する",
    )
    return parser.parse_args()


def get_file_info(file_path: str) -> tuple[int, int]:
    """ファイルサイズとデータ行数を取得する"""
    file_size = os.path.getsize(file_path)
    with open(file_path, "r", encoding="utf-8-sig") as f:
        line_count = sum(1 for _ in f) - 1  # ヘッダーを除く
    return file_size, line_count


def process_row(row: Dict[str, str]) -> Dict[str, str | None]:
    """DB列だけを残し、空文字列・NULLをNoneに変換する。"""
    processed = {}
    for key, value in row.items():
        if key is None:
            continue
        key = key.lstrip("\ufeff")
        if key not in IMPORT_FIELDS:
            continue
        if isinstance(value, str):
            value = value.strip()
            if value == "" or value == "NULL":
                value = None
        processed[key] = value
    return processed


def preflight_validate_tsv(file_path: str) -> int:
    """DB接続前にTSVの構造・必須値・主キー重複を検証する。"""
    seen_ids: dict[str, int] = {}
    duplicate_ids: list[tuple[str, int, int]] = []
    malformed_lines: list[int] = []
    missing_required_values: list[tuple[int, str]] = []
    invalid_integer_values: list[tuple[int, str]] = []
    row_count = 0

    with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        fieldnames = {
            field.lstrip("\ufeff") for field in (reader.fieldnames or [])
        }
        missing_headers = sorted(REQUIRED_FIELDS - fieldnames)
        if missing_headers:
            raise ValueError(
                "必須TSV列がありません: " + ", ".join(missing_headers)
            )

        for line_number, row in enumerate(reader, start=2):
            row_count += 1
            if None in row or any(value is None for value in row.values()):
                malformed_lines.append(line_number)
                continue

            processed = process_row(row)
            for field in REQUIRED_FIELDS:
                if processed.get(field) is None:
                    missing_required_values.append((line_number, field))

            row_id = processed.get("ID")
            if row_id is not None:
                first_line = seen_ids.setdefault(row_id, line_number)
                if first_line != line_number:
                    duplicate_ids.append((row_id, first_line, line_number))

            character_number = processed.get("資料内漢字番号")
            if character_number is not None:
                try:
                    int(character_number)
                except (TypeError, ValueError):
                    invalid_integer_values.append(
                        (line_number, str(character_number))
                    )

    errors = []
    if row_count == 0:
        errors.append("TSVにデータ行がありません")
    if malformed_lines:
        errors.append(
            "列数が不正な行: "
            + ", ".join(map(str, malformed_lines[:10]))
        )
    if missing_required_values:
        examples = ", ".join(
            f"{line}:{field}"
            for line, field in missing_required_values[:10]
        )
        errors.append("必須値が空の行: " + examples)
    if invalid_integer_values:
        examples = ", ".join(
            f"{line}:{value}"
            for line, value in invalid_integer_values[:10]
        )
        errors.append("資料内漢字番号が整数でない行: " + examples)
    if duplicate_ids:
        examples = ", ".join(
            f"{row_id} ({first_line}, {duplicate_line})"
            for row_id, first_line, duplicate_line in duplicate_ids[:10]
        )
        errors.append("重複ID: " + examples)

    if errors:
        raise ValueError("\n".join(errors))

    return row_count


def read_tsv_in_batches(file_path: str, batch_size: int) -> Iterator[List[Dict]]:
    """TSV ファイルをバッチごとに読み込む"""
    with open(file_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter="\t")
        batch: list[Dict] = []

        ignored_fields = [
            field for field in (reader.fieldnames or [])
            if field.lstrip("\ufeff") not in IMPORT_FIELDS
        ]
        if ignored_fields:
            print(
                "ℹ️  DBに未マッピングのTSV列を無視します: "
                + ", ".join(ignored_fields)
            )
            print()

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
    """対象テーブルへのアクセスを確認してから全行を削除する。"""
    print(f"🗑️  テーブル {table_name} をクリア中...")
    try:
        supabase.table(table_name).select("ID", count="exact").limit(0).execute()
    except Exception as e:
        raise RuntimeError(
            f"テーブル {table_name} を確認できないため、インポートを中止します"
        ) from e
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

    # DBへ接続する前に、失敗要因を検出する
    print("🔎 TSV事前検証中...")
    try:
        validated_rows = preflight_validate_tsv(args.file)
    except ValueError as e:
        print(f"❌ TSV事前検証失敗:\n{e}")
        sys.exit(1)
    print(f"✅ TSV事前検証成功: {validated_rows:,} 行")
    print()

    if args.preflight_only:
        print("✅ 事前検証のみ完了しました。DBには接続していません")
        return

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
