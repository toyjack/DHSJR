# TSV Data Import Guide

このプロジェクトは、dataフォルダ内のすべてのTSVファイルをPostgreSQLデータベースに自動的にインポートするGitHub Actionを提供します。

## 自動インポート

GitHub Actionは以下の場合に自動的に実行されます：

1. `data/**/*.tsv` ファイルが変更され、mainブランチにプッシュされた時
2. 手動でワークフローを実行した時（GitHub Actionsタブから）

## ローカルでのインポート

ローカル環境でデータをインポートする場合：

### 1. 環境変数の設定

`.env` ファイルを作成し、PostgreSQLの接続情報を設定します：

```bash
DATABASE_URL="postgresql://username:password@localhost:5432/dhsjr"
```

### 2. 依存関係のインストール

```bash
npm install
```

### 3. Prisma Clientの生成

```bash
npx prisma generate
```

### 4. データベースのセットアップ

```bash
npx prisma db push
```

### 5. TSVデータのインポート

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
