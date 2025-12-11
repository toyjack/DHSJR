# /// script
# requires-python = ">=3.14"
# dependencies = [
#     "supabase>=2.25.1",
# ]
# ///
import os
import sys
from supabase import create_client, Client

# 配置
SUPABASE_URL = os.environ.get("SUPABASE_URL_ENV")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY_ENV")

def create_supabase_client() -> Client:
    """创建 Supabase 客户端"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("缺少 SUPABASE_URL_ENV 或 SUPABASE_SERVICE_KEY_ENV 环境变量")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def clear_table(supabase: Client) -> None:
    """清空 dhsjr 表中的所有数据，但保留表结构"""
    try:
        print("🗑️  テーブル dhsjr をクリア中...")

        response = (
            supabase.rpc("truncate_dhsjr")
            .execute()
        )

        print("✅ テーブル dhsjr をクリアしました")

    except Exception as e:
        print(f"❌ クリアエラー: {str(e)}")
        raise e


def main():
    print("=" * 60)
    print("DHSJR テーブルクリアツール")
    print("=" * 60)
    print()

    # 创建 Supabase 客户端
    try:
        print("🔌 Supabase に接続中...")
        supabase = create_supabase_client()
        print("✅ 接続成功")
    except Exception as e:
        print(f"❌ Supabase 接続エラー: {str(e)}")
        sys.exit(1)

    print()

    # 确认操作
    print("⚠️  警告: テーブル dhsjr の全データを削除します")
    print("   (表構造は保持されます)")
    print()

    # 在 CI 环境中自动确认，在本地环境中需要用户确认
    is_ci = os.environ.get("CI", "false").lower() == "true"

    if not is_ci:
        confirm = input("続行しますか? (yes/no): ").strip().lower()
        if confirm not in ["yes", "y"]:
            print("❌ キャンセルしました")
            sys.exit(0)
        print()

    # 清空表
    try:
        clear_table(supabase)
        print()
        print("=" * 60)
        print("✨ クリア完了!")
        print("=" * 60)

    except Exception as e:
        print()
        print("=" * 60)
        print(f"❌ エラー発生: {str(e)}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
