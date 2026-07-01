"""
楽天市場「靴」デイリーランキング TOP10 を毎日記録するスクリプト。

処理の流れ:
  1. Playwrightでランキングページを開く
  2. TOP10が表示されているエリアだけをスクリーンショット(PNG)
  3. Pillowで軽量なWebPに変換してPNGは削除
  4. Google Driveの指定フォルダにWebPをアップロード
  5. TOP10の商品名・価格・URLを抽出
  6. Googleスプレッドシートに1行ずつ追記(スクショのリンクも含む)

事前準備(README.md参照):
  - Google Cloud サービスアカウントを作成し credentials.json を配置
  - 対象スプレッドシート/Driveフォルダをサービスアカウントに共有
  - 環境変数 SPREADSHEET_ID / DRIVE_FOLDER_ID を設定

セレクタは実際のDOM構造を確認して下記のTODO部分を埋めてください。
"""

import os
from datetime import datetime, timedelta, timezone

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from PIL import Image
from playwright.sync_api import sync_playwright

# ---- 設定 -------------------------------------------------------------

RANKING_URL = (
    "https://ranking.rakuten.co.jp/daily/558885/"  # 靴ジャンル デイリー
)
TOP_N = 10

CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json")
SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
DRIVE_FOLDER_ID = os.environ["DRIVE_FOLDER_ID"]
SHEET_NAME = os.environ.get("SHEET_NAME", "シート1")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

JST = timezone(timedelta(hours=9))


# ---- スクレイピング -----------------------------------------------------


def scrape_top10():
    """ランキングページを開き、TOP10のスクショと商品情報を取得する。"""
    tmp_png = "/tmp/ranking_area.png"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 2400})
        page.goto(RANKING_URL, wait_until="networkidle")

        # TODO: TOP10の商品リストを囲んでいる親要素のセレクタに置き換える
        # 例: page.locator("div.rnkRanking_rankList") のような要素
        area_selector = "TODO_TOP10_AREA_SELECTOR"
        area = page.locator(area_selector)
        area.screenshot(path=tmp_png)

        # TODO: 商品1件ごとの要素セレクタに置き換える
        item_selector = "TODO_ITEM_SELECTOR"
        items = area.locator(item_selector)

        products = []
        for i in range(min(TOP_N, items.count())):
            item = items.nth(i)

            # TODO: それぞれの子要素セレクタを実際のDOMに合わせて調整
            name = item.locator("TODO_NAME_SELECTOR").inner_text().strip()
            price = item.locator("TODO_PRICE_SELECTOR").inner_text().strip()
            url = item.locator("TODO_LINK_SELECTOR").get_attribute("href")

            products.append(
                {"rank": i + 1, "name": name, "price": price, "url": url}
            )

        browser.close()

    return tmp_png, products


# ---- スクショ圧縮(WebP変換) --------------------------------------------


def convert_to_webp(png_path: str, date_str: str) -> str:
    """PNGをファイルサイズの小さいWebPに変換する。"""
    webp_path = f"/tmp/{date_str}.webp"
    img = Image.open(png_path).convert("RGB")
    img.save(webp_path, "WEBP", quality=70, method=6)
    os.remove(png_path)
    return webp_path


# ---- Google Drive アップロード ------------------------------------------


def upload_to_drive(creds: Credentials, local_path: str, filename: str) -> str:
    service = build("drive", "v3", credentials=creds)
    file_metadata = {"name": filename, "parents": [DRIVE_FOLDER_ID]}
    media = MediaFileUpload(local_path, mimetype="image/webp")
    uploaded = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id, webViewLink")
        .execute()
    )
    return uploaded["webViewLink"]


# ---- スプレッドシート書き込み --------------------------------------------


def write_to_sheet(creds: Credentials, rows: list):
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(SHEET_NAME)
    ws.append_rows(rows, value_input_option="USER_ENTERED")


# ---- メイン処理 ---------------------------------------------------------


def main():
    now = datetime.now(JST)
    date_str = now.strftime("%y%m%d")  # YYMMDD

    tmp_png, products = scrape_top10()
    webp_path = convert_to_webp(tmp_png, date_str)

    creds = Credentials.from_service_account_file(
        CREDENTIALS_PATH, scopes=SCOPES
    )

    screenshot_url = upload_to_drive(creds, webp_path, f"{date_str}.webp")

    rows = [
        [
            now.isoformat(),
            p["rank"],
            p["name"],
            p["price"],
            p["url"],
            screenshot_url,
        ]
        for p in products
    ]
    write_to_sheet(creds, rows)

    os.remove(webp_path)
    print(f"done: {len(rows)} rows written, screenshot: {screenshot_url}")


if __name__ == "__main__":
    main()
