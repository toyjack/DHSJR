# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "supabase>=2.25.0",
#     "python-dotenv>=1.0.0",
# ]
# ///
"""DHSJR テーブルクリアツール

dhsjr テーブルの全データを削除する（テーブル構造は保持）。
"""

import argparse
import os
import sys

from common import create_supabase_client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DHSJR テーブルクリアツール")
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="確認プロンプトをスキップする",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("=" * 60)
    print("DHSJR テーブルクリアツール")
    print("=" * 60)
    print()

    # Supabase 接続
    print("🔌 Supabase に接続中...")
    supabase = create_supabase_client()
    print("✅ 接続成功")
    print()

    # 確認
    print("⚠️  警告: テーブル dhsjr の全データを削除します")
    print("   (表構造は保持されます)")
    print()

    is_ci = os.environ.get("CI", "false").lower() == "true"
    if not args.yes and not is_ci:
        confirm = input("続行しますか? (yes/no): ").strip().lower()
        if confirm not in ("yes", "y"):
            print("❌ キャンセルしました")
            sys.exit(0)
        print()

    # テーブルクリア
    try:
        print("🗑️  テーブル dhsjr をクリア中...")
        try:
            supabase.table("dhsjr").select("ID", count="exact").limit(0).execute()
        except Exception:
            print("⏭️  テーブル dhsjr が存在しません。クリアをスキップします")
        else:
            supabase.table("dhsjr").delete().gte("ID", "").execute()
            print("✅ テーブル dhsjr をクリアしました")
        print("✅ テーブル dhsjr をクリアしました")
        print()
        print("=" * 60)
        print("✨ クリア完了!")
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
