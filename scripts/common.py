# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "supabase>=2.25.0",
#     "python-dotenv>=1.0.0",
# ]
# ///
"""DHSJR 共通ユーティリティモジュール"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import Client, create_client


def load_env() -> None:
    """プロジェクトルートの .env ファイルを読み込む"""
    project_root = Path(__file__).resolve().parent.parent
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def create_supabase_client() -> Client:
    """Supabase クライアントを作成する

    環境変数 SUPABASE_URL_ENV と SUPABASE_SERVICE_KEY_ENV が必要。
    .env ファイルがあれば自動的に読み込む。
    """
    load_env()

    url = os.environ.get("SUPABASE_URL_ENV")
    key = os.environ.get("SUPABASE_SERVICE_KEY_ENV")

    if not url or not key:
        print("❌ エラー: 環境変数 SUPABASE_URL_ENV と SUPABASE_SERVICE_KEY_ENV を設定してください")
        sys.exit(1)

    return create_client(url, key)
