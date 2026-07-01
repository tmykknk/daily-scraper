---
name: daily-scraper
description: >
  楽天「靴」デイリーランキングTOP10を記録するスクレイパー(rakuten-shoes-ranking リポジトリ、
  scrape.py / pyproject.toml / uv.lock / .github/workflows/daily-scrape.yml)を編集・デバッグ・
  拡張するときは必ずこのスキルを使うこと。特に scrape.py 内の TODO_* セレクタの調査・更新、
  Playwright MCPを使ったDOM調査、Ruffによるエラーチェック、credentials.json や
  GOOGLE_CREDENTIALS_JSON など秘匿情報の取り扱いが絡む変更では、コードを一行でも書く前に
  このスキルを参照する。「セレクタが動かない」「TODOを埋めて」「ランキングページの構造を調べて」
  といった依頼にも適用する。
compatibility: uv, Ruff (Zedに設定済み), Playwright MCP
---

# 開発スキル

楽天市場「靴」デイリーランキングTOP10を毎日記録するスクレイパー(`rakuten-shoes-ranking`)の
開発・保守を行うためのスキル。このプロジェクトを触るときは、以下の3つのルールを必ず守ること。

1. セレクタ調査は Playwright MCP でDOMを直接見てから行う(推測で書かない)
2. コードを変更したら必ず Ruff でエラーチェックする
3. 秘匿情報(credentials.json, GOOGLE_CREDENTIALS_JSON など)は絶対に閲覧・出力・操作しない

---

## 0. プロジェクトの前提

- メインスクリプト: `scrape.py`
- 依存管理: `uv`(`pyproject.toml` / `uv.lock`)
- 対象ページ: `https://ranking.rakuten.co.jp/daily/558885/`(靴ジャンル・デイリー)

### セットアップ(.venvのアクティベート)

このプロジェクトを開いて作業を始める前に、必ず仮想環境を作成・アクティベートしておく:

```bash
source .venv/bin/activate    # Windowsは .venv\Scripts\activate
```

- `uv run ...` を使う分には自動的に`.venv`が使われるためアクティベート不要だが、
  Zedのインタプリタ選択・Ruffなどのlint/LSP連携が正しい依存関係を認識するために、
  Zedで作業する前には `.venv` をアクティベートしておく(またはZedのPython interpreter設定で
  `.venv/bin/python` を明示的に指定する)こと
- 新しいターミナル/セッションで作業を再開するたびに、まだアクティベートされていなければ
  `source .venv/bin/activate` を実行する
- `scrape.py` には以下のプレースホルダがあり、実DOMを見て埋める必要がある:
  - `TODO_TOP10_AREA_SELECTOR`(TOP10全体を囲む要素)
  - `TODO_ITEM_SELECTOR`(商品1件ごとの要素)
  - `TODO_NAME_SELECTOR` / `TODO_PRICE_SELECTOR` / `TODO_LINK_SELECTOR`

**注意**: 楽天のランキングページは、TOP3とTOP4〜10でマークアップ(HTML構造)が異なる場合がある。
「TOP10全体を囲む単一の親要素」が存在しないケースがあるため、
`TODO_TOP10_AREA_SELECTOR` を単純な1つのCSSセレクタで解決できるとは限らない。
詳しい調査手順は `references/selector-research.md` を参照。

---

## 1. セレクタ調査(Playwright MCP)

セレクタに関する作業(TODOを埋める・動かなくなったセレクタを直す・新しい項目を取得する等)は、
**必ず Playwright MCP で実際のDOMを取得してから**コードに反映する。記憶や一般的な楽天の知識から
セレクタを推測して書かない。

基本フロー:

1. Playwright MCPで `https://ranking.rakuten.co.jp/daily/558885/` を開く
2. ページのスナップショット/アクセシビリティツリーまたはDOM構造を取得する
3. TOP1〜TOP10に該当する要素を特定する
   - まず個々の商品アイテムの要素パターン(繰り返し構造)を見つける
   - 「TOP10をまとめて囲む1つの親要素」が無い場合は、`references/selector-research.md` の
     代替方針(スクショ用に個別要素のバウンディングボックスを合成する 等)を検討する
4. 商品名・価格・リンクそれぞれの子要素セレクタを特定する
5. 見つけたセレクタを実際に `page.locator(...)` で1件試し、要素数・取得値が想定通りか確認する
   (10件取れるか、価格が数値として妥当か、URLが商品ページになっているか)
6. `scrape.py` の該当 TODO を置き換える

セレクタは楽天側のマークアップ変更で壊れやすいため、**変更後は必ずローカルで一度実行して
10件のデータが正しく取れることを確認してから**コミットする。

詳細な調査手順・DOM構造の癖・代替アプローチは `references/selector-research.md` を参照すること。

---

## 2. エラーチェック(Ruff)

`scrape.py` やその他の `.py` ファイルを1文字でも変更したら、**作業完了とみなす前に必ず**
以下を実行し、エラー・警告がゼロであることを確認する(Zed側にもRuffは設定済みだが、
それとは別にコマンドラインでも必ず実行して確認すること)。

`.venv` が未アクティベートの場合は先に `source .venv/bin/activate` を実行してから進める
(セクション0参照)。

```bash
uv run ruff check .
uv run ruff format --check .
```

- `ruff check` でエラーが出た場合は修正して再実行し、クリーンになるまで繰り返す
- `ruff format --check` が差分を報告した場合は `uv run ruff format .` を実行して整形する
- 型やロジックに関わる変更をした場合は、可能であれば `uv run python scrape.py` を
  実際に動かして例外が出ないことも確認する(ただし secrets の扱いはセクション3に従うこと)

Ruffが未インストール/未検出の場合は `uv sync` で依存関係を再同期してから再実行する。

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
- [ ] `uv run ruff check .` がエラーなしで通るか
- [ ] `uv run ruff format --check .` が差分なしか
- [ ] `credentials.json` や `.env` の中身を一切閲覧・出力していないか
- [ ] シークレットの値を会話やログに出力していないか
- [ ] skills, README の更新が必要か
