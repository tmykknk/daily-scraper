# 楽天デイリーランキング TOP10 自動記録

楽天市場のデイリーランキング TOP10 を毎日自動取得し、
- 商品名・価格・URL・順位をGoogleスプレッドシートに追記
- TOP10エリアのスクショ(WebP)をGoogleスプレッドシートと同じディレクトリのGoogle Driveフォルダに保存

する、GitHub Actions上で毎日1回動くポートフォリオ用サンプルです。

---

## 1. Google Cloud 側の準備

### 1-1. プロジェクト作成 & API有効化
1. [Google Cloud Console](https://console.cloud.google.com/) で新規プロジェクトを作成
2. 「APIとサービス」→「ライブラリ」から以下を有効化
   - Google Sheets API
   - Google Drive API

### 1-2. サービスアカウント作成
1. 「APIとサービス」→「認証情報」→「認証情報を作成」→「サービスアカウント」
2. 名前は任意(例: `rakuten-ranking-bot`)、ロールは特に付与不要
3. 作成後、サービスアカウントの「キー」タブから「鍵を追加」→ JSON形式でダウンロード
4. ダウンロードしたファイルを `credentials.json` としてプロジェクトルートに配置(**Gitにはコミットしない**)
5. JSON内の `client_email`(例: `xxx@xxx.iam.gserviceaccount.com`)をメモしておく

### 1-3. スプレッドシート & Driveフォルダの共有
1. 記録用のGoogleスプレッドシートを新規作成し、シート名を控える(デフォルト `シート1`)
   - 1行目にヘッダーを入れておくと分かりやすい:
     `取得日時 / 順位 / 商品名 / 価格 / 商品URL / スクショURL`
   - URLの `/d/xxxxx/edit` の `xxxxx` 部分が **SPREADSHEET_ID**
2. スプレッドシートと同じGoogle Drive上のディレクトリにスクショ保存用フォルダを新規作成
   - フォルダを開いた時のURL `/folders/xxxxx` の `xxxxx` が **DRIVE_FOLDER_ID**
3. スプレッドシートとDriveフォルダの両方を、手順1-2でメモした `client_email` に対して
   「編集者」権限で共有(サービスアカウントは自分のGoogleアカウントとは別のGoogleアカウント扱いなので、必ず共有操作が必要)

---

## 2. ローカルでの動作確認

[uv](https://docs.astral.sh/uv/)がインストールされている前提です(未導入の場合は `curl -LsSf https://astral.sh/uv/install.sh | sh`)。

```bash
cd rakuten-shoes-ranking

uv sync                      # pyproject.toml / uv.lock から依存関係を解決してインストール
source .venv/bin/activate    # 仮想環境をアクティベート

uv run playwright install chromium

export SPREADSHEET_ID="スプレッドシートのID"
export DRIVE_FOLDER_ID="DriveフォルダのID"

uv run python scrape.py
```

依存パッケージを追加・変更したいときは `uv add パッケージ名` / `uv remove パッケージ名` を使うと
`pyproject.toml` と `uv.lock` が自動で更新されます。

### セレクタの調査
`scrape.py` 内の以下の `TODO_...` 部分は、実際のページのDOM構造を見て埋めてください。
ブラウザの開発者ツール(検証)で楽天ランキングページを開き、TOP10を囲む親要素・商品1件ごとの要素・
商品名/価格/リンクの要素をそれぞれ特定します。

```python
area_selector = "TODO_TOP10_AREA_SELECTOR"   # TOP10全体を囲む要素
item_selector = "TODO_ITEM_SELECTOR"         # 商品1件ごとの要素
name = item.locator("TODO_NAME_SELECTOR")    # 商品名
price = item.locator("TODO_PRICE_SELECTOR")  # 価格
url = item.locator("TODO_LINK_SELECTOR")     # 商品リンク(href属性)
```

実行後、スプレッドシートに10行追記され、Driveフォルダに `YYMMDD.webp` が
保存されていれば成功です。

---

## 3. GitHub Actions での定期実行設定

### 3-1. リポジトリのSecrets登録
GitHubリポジトリの「Settings」→「Secrets and variables」→「Actions」で以下を登録:

| Secret名 | 値 |
|---|---|
| `GOOGLE_CREDENTIALS_JSON` | `credentials.json` の中身をbase64エンコードした文字列 |
| `SPREADSHEET_ID` | スプレッドシートID |
| `DRIVE_FOLDER_ID` | DriveフォルダID |

`GOOGLE_CREDENTIALS_JSON` の作り方:

```bash
base64 -i credentials.json | tr -d '\n'
```
→ 出力された文字列をそのままSecretの値として登録

### 3-2. 動作確認
1. リポジトリをGitHubにpush(`credentials.json` は `.gitignore` 済みなので含まれません)
2. 「Actions」タブ →「daily-scrape」ワークフローを選択 →「Run workflow」で手動実行
3. 成功すればスプレッドシートに行が追記され、Driveにスクショが保存される
4. 以降は毎日 JST 9:00 に自動実行されます(`cron: '0 0 * * *'`)

---

## ファイル構成

```
rakuten-shoes-ranking/
├── scrape.py                          # メインスクリプト
├── pyproject.toml                     # 依存パッケージ定義(uv)
├── uv.lock                            # ロックファイル(uv)
├── .gitignore
├── .github/workflows/daily-scrape.yml # 定期実行ワークフロー
└── README.md
```

## 補足

- スクショはPlaywrightで一旦PNG取得後、Pillowで `quality=70` のWebPに変換してファイルサイズを抑えています
- 対象エリアのみのスクショ(ページ全体ではない)なので、そもそものサイズも小さめです
- 楽天の利用規約・robots.txtの範囲内で、過度な頻度・負荷をかけないようご注意ください
