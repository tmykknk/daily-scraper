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


### 1-4. マイドライブへ保存する場合のOAuth設定

サービスアカウントはマイドライブ上のフォルダに対して編集者権限を持っていても、
サービスアカウント自身にDriveストレージ容量がないため、ファイル作成時に
`storageQuotaExceeded` で失敗します。個人Googleアカウントのマイドライブへ保存する場合は、
ユーザーOAuth認証を使ってください。

1. Google Cloud ConsoleでOAuth同意画面を設定
2. 「認証情報」→「認証情報を作成」→「OAuth クライアント ID」→「デスクトップアプリ」を作成
3. ダウンロードしたJSONを `oauth_client.json` としてローカルに保存(**Gitにはコミットしない**)
4. 以下で `token.json` を生成

```bash
uv run python generate_token.py
```

Googleの認証画面でアクセスエラーになる場合は、以下を確認してください。

- OAuthクライアントIDの種類が「デスクトップアプリ」になっているか
- OAuth同意画面が「テスト」の場合、`generate_token.py` でログインするGoogleアカウントを
  OAuth同意画面の「テストユーザー」に追加しているか
- 個人利用で自分のGoogleアカウントだけ使う場合、アプリを外部公開する必要はありません。
  「テスト」状態のまま、使うアカウントをテストユーザーに追加すれば認証できます。
- WebアプリのOAuthクライアントを使う場合、承認済みリダイレクトURIに `http://localhost:8080/` を追加しているか

5. `.env` に以下を設定

```bash
# マイドライブへ保存する場合はコメントアウトせず oauth のまま使う
GOOGLE_AUTH_MODE=oauth
GOOGLE_OAUTH_TOKEN_PATH=token.json
```

`GOOGLE_AUTH_MODE=oauth` は、マイドライブへ保存する場合は必須です。
コメントアウトするとデフォルトの `service_account` 扱いになり、マイドライブへのアップロードは
`storageQuotaExceeded` で失敗します。共有ドライブ + サービスアカウントで運用する場合だけ
`GOOGLE_AUTH_MODE=service_account` に変更してください。

GitHub ActionsでOAuthを使う場合は、`token.json` の中身をGitHub Secretsの
`GOOGLE_OAUTH_TOKEN_JSON` に登録します。このSecretがある場合、ワークフローはOAuthを使います。

---

## 2. ローカルでの動作確認

[uv](https://docs.astral.sh/uv/)がインストールされている前提です(未導入の場合は `curl -LsSf https://astral.sh/uv/install.sh | sh`)。

```bash
cd daily-scraper

uv sync                      # pyproject.toml / uv.lock から依存関係を解決してインストール
source .venv/bin/activate    # 仮想環境をアクティベート

uv run playwright install chrome

# export で指定するか、同じ内容を .env に書いてください
export SPREADSHEET_ID="スプレッドシートのID"
export DRIVE_FOLDER_ID="DriveフォルダのID"
export SCRAPER_BROWSER_CHANNEL="chrome"  # 通常Chromeを使う
export SCRAPER_HEADLESS="true"           # 動的UAとwebdriver無効化でheadless実行

uv run python scrape.py
```

依存パッケージを追加・変更したいときは `uv add パッケージ名` / `uv remove パッケージ名` を使うと
`pyproject.toml` と `uv.lock` が自動で更新されます。
ローカル実行時は `python-dotenv` により、プロジェクトルートの `.env` も自動で読み込まれます。

### 取得ロジック
現在の `scrape.py` は固定の `TODO_*` セレクタではなく、商品リンク
`a[href*='item.rakuten.co.jp']` を起点に、近い親要素から商品名・価格・URLを抽出します。
TOP10スクショは、抽出した10商品の表示範囲を合成した `clip` で撮影します。

楽天ランキングページは素の Playwright headless だと `403` を返すことがあります。
このため、`scrape.py` では通常ChromeのメジャーバージョンからUser-Agentを動的に作り、
`navigator.webdriver` を無効化し、広告・計測系URLを遮断して headless 実行します。
`SCRAPER_BROWSER_CHANNEL=chrome` を指定すると、Playwright同梱ChromiumではなくOSに入っている
通常Chromeを使います。

DOM抽出だけを副作用なしで確認する場合は、以下を実行します。

```bash
SCRAPER_BROWSER_CHANNEL=chrome SCRAPER_HEADLESS=true \
  uv run python - <<'PY'
import scrape

_, products = scrape.scrape_top10()
for product in products:
    print(product["rank"], product["price"], product["url"])
PY
```

実行後、スプレッドシートに10行追記され、Driveフォルダに `YYMMDD.webp` が
保存されていれば成功です。

### 開発時チェック
型診断と整形/リントは `pyright` と `ruff` で確認します。

```bash
uv run pyright
uv run ruff check .
uv run ruff format --check .
```

Zedでは `.zed/settings.json` により、Python保存時に Ruff formatter と Ruff code actions
(import整理・自動修正)が実行される設定です。型診断は `pyrightconfig.json` の設定で行います。

---

## 3. GitHub Actions での定期実行設定

### 3-1. リポジトリのSecrets登録
GitHubリポジトリの「Settings」→「Secrets and variables」→「Actions」で以下を登録:

| Secret名 | 値 |
|---|---|
| `GOOGLE_CREDENTIALS_JSON` | サービスアカウントを使う場合のみ。`credentials.json` の中身をbase64エンコードした文字列 |
| `GOOGLE_OAUTH_TOKEN_JSON` | マイドライブへ保存する場合。`token.json` の中身 |
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
4. ワークフローでは通常Chromeを headless で起動します
5. 以降は毎日 JST 9:00 に自動実行されます(`cron: '0 0 * * *'`)

---

## ファイル構成

```
daily-scraper/
├── scrape.py                          # メインスクリプト
├── pyproject.toml                     # 依存パッケージ定義(uv)
├── uv.lock                            # ロックファイル(uv)
├── pyrightconfig.json                 # Pyright型診断設定
├── .zed/settings.json                 # Zed保存時整形/言語サーバ設定
├── .agents/skills/daily-scraper/      # Codex用プロジェクトスキル
├── .gitignore
├── .github/workflows/daily-scrape.yml # 定期実行ワークフロー
└── README.md
```

## 補足

- スクショはPlaywrightで一旦PNG取得後、Pillowで `quality=70` のWebPに変換してファイルサイズを抑えています
- 対象エリアのみのスクショ(ページ全体ではない)なので、そもそものサイズも小さめです
- 楽天の利用規約・robots.txtの範囲内で、過度な頻度・負荷をかけないようご注意ください
