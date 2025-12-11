import os
import csv
import sys
from supabase import create_client, Client
from typing import List, Dict
import time

# 配置
SUPABASE_URL = os.environ.get("SUPABASE_URL_ENV")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY_ENV")
TABLE_NAME = "dhsjr"
TSV_FILE = "DHSJR_data_all.tsv"
BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "1000"))

# TSV 文件的列名映射
COLUMN_MAPPING = {
    "ID": "ID",
    "資料番号": "資料番号",
    "資料名": "資料名",
    "資料内漢字番号": "資料内漢字番号",
    "資料内漢語番号": "資料内漢語番号",
    "単字_見出し": "単字_見出し",
    "単字_出現形": "単字_出現形",
    "漢語_見出し": "漢語_見出し",
    "漢語_出現形": "漢語_出現形",
    "漢語_alphabet": "漢語_alphabet",
    "語種": "語種",
    "漢語内位置": "漢語内位置",
    "単字長": "単字長",
    "声点": "声点",
    "声点型": "声点型",
    "仮名注": "仮名注",
    "仮名型": "仮名型",
    "反切": "反切",
    "類音": "類音",
    "節博士": "節博士",
    "その他": "その他",
    "出現位置": "出現位置",
    "備考": "備考"
}

def create_supabase_client() -> Client:
    """创建 Supabase 客户端"""
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("缺少 SUPABASE_URL 或 SUPABASE_SERVICE_KEY 环境变量")
    return create_client(SUPABASE_URL, SUPABASE_KEY)

def read_tsv_in_batches(file_path: str, batch_size: int):
    """分批读取 TSV 文件"""
    with open(file_path, 'r', encoding='utf-8') as tsvfile:
        # 使用 tab 作为分隔符
        reader = csv.DictReader(tsvfile, delimiter='\t')
        batch = []
        
        for row in reader:
            # 处理数据
            processed_row = process_row(row)
            if processed_row:  # 跳过空行
                batch.append(processed_row)
            
            if len(batch) >= batch_size:
                yield batch
                batch = []
        
        # 处理最后一批
        if batch:
            yield batch

def process_row(row: Dict) -> Dict:
    """处理单行数据"""
    processed = {}
    
    for original_key, db_key in COLUMN_MAPPING.items():
        value = row.get(original_key, '')
        
        # 数据清洗
        if isinstance(value, str):
            value = value.strip()
            # 空字符串转为 None
            if value == '' or value == 'NULL':
                value = None
        
        # 跳过 ID 列，让数据库自动生成
        if db_key != 'ID':
            processed[db_key] = value
    
    return processed

def insert_batch(supabase: Client, table_name: str, batch: List[Dict], retry_count: int = 3):
    """插入一批数据，带重试机制"""
    for attempt in range(retry_count):
        try:
            response = supabase.table(table_name).insert(batch).execute()
            return response
        except Exception as e:
            if attempt < retry_count - 1:
                wait_time = (attempt + 1) * 2
                print(f"  ⚠️  插入失败，等待 {wait_time} 秒后重试... 错误: {str(e)}")
                time.sleep(wait_time)
            else:
                print(f"  ❌ 重试失败: {str(e)}")
                raise e

def get_file_info(file_path: str):
    """获取文件信息"""
    import os
    file_size = os.path.getsize(file_path)
    
    # 计算行数
    with open(file_path, 'r', encoding='utf-8') as f:
        line_count = sum(1 for _ in f) - 1  # 减去表头
    
    return file_size, line_count

def main():
    print("=" * 60)
    print("DHSJR データインポートツール")
    print("=" * 60)
    print()
    
    # 检查文件
    if not os.path.exists(TSV_FILE):
        print(f"❌ エラー: ファイル {TSV_FILE} が見つかりません")
        sys.exit(1)
    
    file_size, line_count = get_file_info(TSV_FILE)
    file_size_mb = file_size / (1024 * 1024)
    
    print(f"📁 ファイル: {TSV_FILE}")
    print(f"📊 ファイルサイズ: {file_size_mb:.2f} MB")
    print(f"📝 データ行数: {line_count:,} 行")
    print(f"🎯 ターゲットテーブル: {TABLE_NAME}")
    print(f"📦 バッチサイズ: {BATCH_SIZE} 行/バッチ")
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
    print("=" * 60)
    print("データインポート開始")
    print("=" * 60)
    print()
    
    # 统计信息
    total_rows = 0
    batch_count = 0
    start_time = time.time()
    
    try:
        # 分批处理
        for batch in read_tsv_in_batches(TSV_FILE, BATCH_SIZE):
            batch_count += 1
            batch_size = len(batch)
            
            print(f"📦 バッチ {batch_count}: {batch_size} 行を処理中...")
            
            # 插入数据
            insert_batch(supabase, TABLE_NAME, batch)
            
            total_rows += batch_size
            elapsed = time.time() - start_time
            speed = total_rows / elapsed if elapsed > 0 else 0
            progress = (total_rows / line_count * 100) if line_count > 0 else 0
            
            print(f"✅ 成功: {total_rows:,}/{line_count:,} 行 ({progress:.1f}%) | "
                  f"速度: {speed:.0f} 行/秒")
            print()
        
        # 完成统计
        elapsed_time = time.time() - start_time
        print("=" * 60)
        print("✨ インポート完了!")
        print("=" * 60)
        print(f"📊 総行数: {total_rows:,} 行")
        print(f"📦 総バッチ数: {batch_count}")
        print(f"⏱️  所要時間: {elapsed_time:.2f} 秒 ({elapsed_time/60:.2f} 分)")
        print(f"⚡ 平均速度: {total_rows/elapsed_time:.2f} 行/秒")
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