---
name: daily-scraper
description: >
  楽天「靴」デイリーランキングTOP10を記録するスクレイパー(daily-scraper リポジトリ、
  scrape.py / pyproject.toml / uv.lock / .github/workflows/daily-scrape.yml)を編集・デバッグ・
  拡張するときは必ずこのスキルを使うこと。特に scrape.py 内の抽出ロジックやDOM調査、
  Playwright MCPを使った確認、Pyright/Ruffによるエラーチェック、credentials.json や
  GOOGLE_CREDENTIALS_JSON など秘匿情報の取り扱いが絡む変更では、コードを一行でも書く前に
  このスキルを参照する。「セレクタが動かない」「ランキングページの構造を調べて」
  といった依頼にも適用する。
compatibility: uv, Ruff/Pyright (Zedに設定済み), Playwright MCP
---

# 開発スキル

楽天市場「靴」デイリーランキングTOP10を毎日記録するスクレイパー(`daily-scraper`)の
開発・保守を行うためのスキル。このプロジェクトを触るときは、以下の3つのルールを必ず守ること。

1. セレクタ調査は Playwright MCP でDOMを直接見てから行う(推測で書かない)
2. コードを変更したら必ず Pyright と Ruff でエラーチェックする
3. 秘匿情報(credentials.json, GOOGLE_CREDENTIALS_JSON など)は絶対に閲覧・出力・操作しない

---

## 0. プロジェクトの前提

- メインスクリプト: `scrape.py`
- 依存管理: `uv`(`pyproject.toml` / `uv.lock`)
- 型診断: `pyrightconfig.json` / `uv run pyright`
- 整形・リント: Ruff / `uv run ruff ...` / `.zed/settings.json` の保存時整形
- 対象ページ: `https://ranking.rakuten.co.jp/daily/558885/`(靴ジャンル・デイリー)

### セットアップ(.venvのアクティベート)

このプロジェクトを開いて作業を始める前に、必ず仮想環境を作成・アクティベートしておく:

```bash
source .venv/bin/activate    # Windowsは .venv\Scripts\activate
```

- ローカル実行時は `python-dotenv` により、プロジェクトルートの `.env` が自動で読み込まれる。
  ただし `.env` の中身は絶対に読まない・出力しない。
- マイドライブ配下へDriveアップロードする場合、サービスアカウントはストレージ容量を持たないため
  `storageQuotaExceeded` になる。`GOOGLE_AUTH_MODE=oauth` と `token.json` を使う。
  この行はコメントアウトしない。共有ドライブ + サービスアカウント運用時だけ `service_account` に変更する。
- OAuth同意画面が「テスト」の場合、`generate_token.py` でログインするGoogleアカウントを
  OAuth同意画面の「テストユーザー」に追加する。個人利用なら外部公開は不要。
- `uv run ...` を使う分には自動的に`.venv`が使われるためアクティベート不要だが、
  Zedのインタプリタ選択・Ruffなどのlint/LSP連携が正しい依存関係を認識するために、
  Zedで作業する前には `.venv` をアクティベートしておく(またはZedのPython interpreter設定で
  `.venv/bin/python` を明示的に指定する)こと
- 新しいターミナル/セッションで作業を再開するたびに、まだアクティベートされていなければ
  `source .venv/bin/activate` を実行する
- 現在の `scrape.py` は固定の `TODO_*` セレクタではなく、商品リンク
  `a[href*='item.rakuten.co.jp']` を起点に近い親要素から商品名・価格・URLを抽出する。
- 固定の `BROWSER_USER_AGENT` は使わない。通常ChromeのメジャーバージョンからUser-Agentを動的に作る。
- `SCRAPER_BROWSER_CHANNEL=chrome` をデフォルトにし、OSに入っている通常Chromeを使う。
- `SCRAPER_HEADLESS=true` をデフォルトにし、`navigator.webdriver` 無効化と広告・計測系URL遮断で
  楽天が素の headless Chromium に返す `403` を避ける。
- TOP10スクショは、抽出した10商品の表示範囲を合成した `clip` で撮影する。

**注意**: 楽天のランキングページは、TOP3とTOP4〜10でマークアップ(HTML構造)が異なる場合がある。
「TOP10全体を囲む単一の親要素」が存在しないケースがあるため、
単純な1つのCSSセレクタでTOP10全体を解決できるとは限らない。
また、素の Playwright `headless=True` では楽天側から `403` を返されることがあるため、
DOM調査時は `SCRAPER_BROWSER_CHANNEL=chrome SCRAPER_HEADLESS=true` で実装と同じ条件を使う。
それでも失敗する場合のみ、`SCRAPER_HEADLESS=false` / `headless=False` で通常表示できるか切り分ける。
CIでは通常Chromeを headless で起動する。

---

## 1. セレクタ調査(Playwright MCP)

セレクタに関する作業(動かなくなった抽出ロジックを直す・新しい項目を取得する等)は、
**必ず Playwright MCP またはローカル Playwright で実際のDOMを取得してから**コードに反映する。
記憶や一般的な楽天の知識からセレクタやDOM構造を推測して書かない。

基本フロー:

1. Playwright MCPで `https://ranking.rakuten.co.jp/daily/558885/` を開く
2. MCPが `403` / `502` でDOMを取得できない場合は、ローカル Playwright の `headless=False` で
   同じURLを開き、通常表示できるか切り分ける
3. ページのスナップショット/アクセシビリティツリーまたはDOM構造を取得する
4. TOP1〜TOP10に該当する要素を特定する
   - まず商品リンク `a[href*='item.rakuten.co.jp']` の出現順と重複を確認する
   - 商品名・価格がリンク自身または近い親要素から取得できるか確認する
   - 「TOP10をまとめて囲む1つの親要素」が無い場合は、スクショ用に個別要素の
     バウンディングボックスを合成する方針を検討する
5. 見つけた抽出方法を実際に `page.locator(...)` / `page.evaluate(...)` で試し、
   要素数・取得値が想定通りか確認する(10件取れるか、価格が数値として妥当か、URLが商品ページになっているか)
6. `scrape.py` の抽出ロジックに反映する
7. Google APIの副作用を避けてDOM抽出だけ確認する場合は、`scrape.scrape_top10()` だけを呼び出す

セレクタは楽天側のマークアップ変更で壊れやすいため、**変更後は必ずローカルで一度実行して
10件のデータが正しく取れることを確認してから**コミットする。

調査結果は `scrape.py` の抽出ロジックに反映し、必要に応じて README も更新すること。

---

## 2. エラーチェック(Pyright / Ruff)

`scrape.py` やその他の `.py` ファイルを1文字でも変更したら、**作業完了とみなす前に必ず**
以下を実行し、エラー・警告がゼロであることを確認する(Zed側にも Pyright / Ruff は設定済みだが、
それとは別にコマンドラインでも必ず実行して確認すること)。

`.venv` が未アクティベートの場合は先に `source .venv/bin/activate` を実行してから進める
(セクション0参照)。

```bash
uv run pyright
uv run ruff check .
uv run ruff format --check .
```

- `pyright` で型エラーが出た場合は修正して再実行し、クリーンになるまで繰り返す
- `ruff check` でエラーが出た場合は修正して再実行し、クリーンになるまで繰り返す
- `ruff format --check` が差分を報告した場合は `uv run ruff format .` を実行して整形する
- 型やロジックに関わる変更をした場合は、可能であれば `uv run python scrape.py` を
  実際に動かして例外が出ないことも確認する(ただし secrets の扱いはセクション3に従うこと)

Pyright/Ruffが未インストール/未検出の場合は `uv sync` で依存関係を再同期してから再実行する。

---

## 3. 秘匿情報の取り扱い(絶対厳守)

このプロジェクトでは以下を**絶対に行わない**:

- `credentials.json` の中身を読む・`cat`する・`view`する・ログや会話に出力する
- `credentials.json` の中身を編集する、または中身に基づいてコードを書く(キーの値をハードコードする等)
- `GOOGLE_CREDENTIALS_JSON`(GitHub Secrets)や、その他APIキー・トークン類の値を
  出力・表示・コピーする
- `.env` ファイルが存在する場合、その中身を読む・出力する

許可される操作:

- `credentials.json` や `.env` が**存在するかどうか**(パスの有無)だけを確認する
- 環境変数が**設定されているかどうか**(値ではなく有無)だけを確認する
  (例: `if os.environ.get("SPREADSHEET_ID"):` はOK。値をprintするのはNG)
- `scrape.py` 内で `CREDENTIALS_PATH` のようにファイルパスを扱うコード自体は編集してよい
  (パスを扱うのは可、中身を扱う/覗くのは不可)

デバッグ時に認証エラーが疑われる場合も、中身を確認するのではなく、
「ファイルが存在するか」「スプレッドシート/Driveがサービスアカウントに共有されているか」
「スコープ(SCOPES)が正しいか」といった**外形的なチェック**に留めること。

---

## 4. 変更後のチェックリスト

コード変更を終える前に、以下を上から順に確認する:

- [ ] セレクタ変更がある場合、Playwright MCPで実DOMを確認した上で反映したか
- [ ] `uv run pyright` がエラーなしで通るか
- [ ] `uv run ruff check .` がエラーなしで通るか
- [ ] `uv run ruff format --check .` が差分なしか
- [ ] `credentials.json` や `.env` の中身を一切閲覧・出力していないか
- [ ] シークレットの値を会話やログに出力していないか
- [ ] skills, README の更新が必要か
