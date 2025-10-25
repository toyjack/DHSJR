# TSV Data Import Guide

このプロジェクトは、dataフォルダ内のすべてのTSVファイルをPostgreSQLデータベースに自動的にインポートするGitHub Actionを提供します。

## プロジェクト構成

すべてのインポート関連ファイルは `tsv-import/` フォルダに配置されています：
- `tsv-import/package.json` - Node.js依存関係
- `tsv-import/prisma/schema.prisma` - データベーススキーマ
- `tsv-import/scripts/import-tsv.js` - インポートスクリプト
- `.github/workflows/import-tsv.yml` - GitHub Action設定

## 自動インポート

### GitHub Secretsの設定

GitHub Actionを使用する前に、リポジトリのSecretsを設定する必要があります：

1. GitHubリポジトリページで `Settings` > `Secrets and variables` > `Actions` に移動
2. `New repository secret` をクリック
3. 以下のシークレットを追加：
   - **Name**: `DATABASE_URL`
   - **Value**: `postgresql://username:password@hostname:5432/database_name`
     - 例: `postgresql://myuser:mypassword@db.example.com:5432/dhsjr`

### 実行タイミング

GitHub Actionは以下の場合に自動的に実行されます：

1. `data/**/*.tsv` ファイルが変更され、mainブランチにプッシュされた時
2. 手動でワークフローを実行した時（GitHub Actionsタブから）

## ローカルでのインポート

ローカル環境でデータをインポートする場合：

### 1. 環境変数の設定

`tsv-import/.env` ファイルを作成し、PostgreSQLの接続情報を設定します：

```bash
DATABASE_URL="postgresql://username:password@localhost:5432/dhsjr"
```

### 2. tsv-importディレクトリに移動

```bash
cd tsv-import
```

### 3. 依存関係のインストール

```bash
npm install
```

### 4. Prisma Clientの生成

```bash
npx prisma generate
```

### 5. データベースのセットアップ

```bash
npx prisma db push
```

### 6. TSVデータのインポート

```bash
npm run import
```

## データモデル

データは以下のPrismaモデルに基づいてインポートされます：

- `character_id`: `資料番号` + `_` + `資料内漢字番号` で生成
- `word_id`: `資料番号` + `_` + `資料内漢語番号` で生成

### TSVファイルのカラムマッピング

| TSVカラム名 | データベースフィールド名 | 型 |
|-------------|------------------------|-----|
| 資料番号 | book_id | String |
| 資料名 | book_name | String |
| 資料内漢字番号 | index_in_book | Int |
| 資料内漢語番号 | word_index_in_book | Int |
| 単字_見出し | character | String |
| 単字_出現形 | character_original | String |
| 漢語_見出し | word | String |
| 漢語_出現形 | word_original | String |
| 漢語_alphabet | word_alphabet | String |
| 語種 | word_type | String |
| 漢語内位置 | pos_in_word | Int |
| 単字長 | len | String |
| 声点 | shoten | String |
| 声点型 | shoten_word | String |
| 仮名注 | kana | String |
| 仮名型 | word_kana | String |
| 反切 | fanqie | String |
| 類音 | ruion | String |
| 節博士 | hakase | String |
| その他 | etc | String |
| 出現位置 | position_in_book | String |
| 備考 | notes | String |

## 注意事項

- インポートスクリプトは既存のレコードを更新します（upsert動作）
- 空の値は`null`として保存されます
- `単字長`フィールドは"1、2"のような値が存在するため、String型として保存されます

## パフォーマンス最適化

インポートスクリプトは以下の最適化を実装しています：

### 実装された最適化

1. **バッチ処理** - 一度に2000レコードをまとめて挿入
2. **PostgreSQL UPSERT** - `ON CONFLICT` を使用した効率的な更新/挿入
3. **Raw SQL** - Prismaの raw SQL を使用して最大限のパフォーマンス
4. **進捗表示** - リアルタイムで処理状況を確認可能

### バッチサイズの調整

より高速な処理が必要な場合、`tsv-import/scripts/import-tsv.js` の `BATCH_SIZE` 定数を調整できます：

```javascript
const BATCH_SIZE = 2000; // デフォルト値
```

推奨値：
- **低メモリ環境**: 1000
- **標準環境**: 2000（デフォルト）
- **高性能環境**: 5000-10000

注意：バッチサイズを大きくしすぎると、PostgreSQLのパラメータ制限（最大65535個）に達する可能性があります。

### パフォーマンス比較

| 方法 | 約33万レコードの処理時間 | 速度 |
|------|------------------------|------|
| 旧方式（逐次upsert） | 数時間 | ~10-50 records/sec |
| 新方式（バッチSQL） | 数分 | ~1000-5000 records/sec |

改善率：**100-1000倍の高速化**
