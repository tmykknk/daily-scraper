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

商品リンクを起点に実DOMからTOP10の商品情報とスクリーンショット範囲を取得します。
"""

import json
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from google.auth.credentials import Credentials
from google.oauth2.credentials import Credentials as OAuthCredentials
from google.oauth2.service_account import (
    Credentials as ServiceAccountCredentials,
)
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from gspread.auth import authorize
from gspread.utils import ValueInputOption
from PIL import Image
from playwright.sync_api import ViewportSize, sync_playwright

# ---- 設定 -------------------------------------------------------------

load_dotenv()


def required_env(name: str) -> str:
    """必須環境変数を取得する。"""
    value = os.environ.get(name)
    if value is None:
        raise RuntimeError(f"required environment variable is missing: {name}")
    return value


RANKING_URL = (
    "https://ranking.rakuten.co.jp/daily/558885/"  # 靴ジャンル デイリー
)
TOP_N = 10
VIEWPORT = ViewportSize(width=1600, height=2400)
BROWSER_CHANNEL = os.environ.get("SCRAPER_BROWSER_CHANNEL", "chrome")
HEADLESS = os.environ.get("SCRAPER_HEADLESS", "true").lower() in {
    "1",
    "true",
    "yes",
}
BLOCKED_URL_KEYWORDS = (
    "analytics",
    "doubleclick",
    "adsystem",
    "googlesyndication",
    "tagmanager",
    "metrics",
    "facebook",
    "twitter",
    "beacon",
    "logs",
)

AUTH_MODE = os.environ.get("GOOGLE_AUTH_MODE", "service_account")
CREDENTIALS_PATH = os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json")
OAUTH_TOKEN_PATH = os.environ.get("GOOGLE_OAUTH_TOKEN_PATH", "token.json")
SPREADSHEET_ID = required_env("SPREADSHEET_ID")
DRIVE_FOLDER_ID = required_env("DRIVE_FOLDER_ID")
SHEET_NAME = os.environ.get("SHEET_NAME", "シート1")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

JST = timezone(timedelta(hours=9))


def load_google_credentials() -> Credentials:
    """Google API用の認証情報を読み込む。"""
    if AUTH_MODE == "service_account":
        return ServiceAccountCredentials.from_service_account_file(
            CREDENTIALS_PATH, scopes=SCOPES
        )

    if AUTH_MODE == "oauth":
        return OAuthCredentials.from_authorized_user_file(
            OAUTH_TOKEN_PATH, scopes=SCOPES
        )

    raise RuntimeError(
        "GOOGLE_AUTH_MODE must be either 'service_account' or 'oauth'."
    )


# ---- スクレイピング -----------------------------------------------------


def chrome_major_version() -> str:
    """インストール済みChrome/Chromiumのメジャーバージョンを取得する。"""
    for command in (
        ["google-chrome", "--version"],
        ["chromium-browser", "--version"],
    ):
        try:
            output = subprocess.check_output(command, text=True)
        except (OSError, subprocess.SubprocessError):
            continue

        if match := re.search(r"(\d+)\.", output):
            return match.group(1)

    return "130"


def chrome_user_agent() -> str:
    """楽天のheadless判定を避けるため、通常Chrome相当のUAを返す。"""
    major = chrome_major_version()
    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 "
        "Safari/537.36"
    )


def browser_launch_options() -> dict:
    """Playwrightのブラウザ起動オプションを返す。"""
    options = {
        "headless": HEADLESS,
        "args": [
            "--window-size=1600,2400",
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-extensions",
            "--dns-prefetch-disable",
            "--disable-blink-features=AutomationControlled",
            "--disable-background-networking",
            "--disable-renderer-backgrounding",
            "--disable-background-timer-throttling",
            "--disable-features=Translate,NewTabPageTriggerOutcome",
        ],
    }
    if BROWSER_CHANNEL:
        options["channel"] = BROWSER_CHANNEL
    return options


def block_tracking_requests(route):
    """広告・計測系URLを遮断し、それ以外のリクエストは通す。"""
    url = route.request.url.lower()
    if any(keyword in url for keyword in BLOCKED_URL_KEYWORDS):
        route.abort()
    else:
        route.continue_()


def scrape_top10():
    """ランキングページを開き、TOP10のスクショと商品情報を取得する。"""
    tmp_png = "/tmp/ranking_area.png"

    with sync_playwright() as p:
        browser = p.chromium.launch(**browser_launch_options())
        context = browser.new_context(
            locale="ja-JP",
            user_agent=chrome_user_agent(),
            viewport=VIEWPORT,
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        page = context.new_page()
        page.set_default_timeout(12000)
        page.set_default_navigation_timeout(12000)
        page.route("**/*", block_tracking_requests)
        try:
            response = page.goto(RANKING_URL, wait_until="domcontentloaded")
            if response is None or not response.ok:
                status = response.status if response else "no response"
                raise RuntimeError(f"failed to load ranking page: {status}")

            page.wait_for_selector(
                "a[href*='item.rakuten.co.jp']", timeout=30000
            )

            result = page.evaluate(
                r"""
            (topN) => {
              const itemUrlPattern = /item\.rakuten\.co\.jp/;
              const pricePattern = /[0-9][0-9,]*円/;
              const productLinks = [];
              const seenUrls = new Set();

              const normalizeText = (text) =>
                (text || "").replace(/\s+/g, " ").trim();

              const cleanProductUrl = (href) => {
                const url = new URL(href);
                url.search = "";
                url.hash = "";
                return url.toString();
              };

              const productName = (link) => {
                const text = normalizeText(link.innerText);
                if (text) return text;

                const image = link.querySelector("img[alt]");
                const imageAlt = normalizeText(image?.getAttribute("alt"));
                if (imageAlt) return imageAlt;

                const nearbyImage = link.parentElement?.querySelector("img[alt]");
                return normalizeText(nearbyImage?.getAttribute("alt"));
              };

              const productContainer = (link) => {
                let current = link;
                let best = link;

                for (let i = 0; i < 8 && current; i += 1) {
                  const text = normalizeText(current.innerText);
                  const itemLinkCount = current.querySelectorAll(
                    "a[href*='item.rakuten.co.jp']"
                  ).length;

                  if (
                    pricePattern.test(text) &&
                    itemLinkCount <= 2 &&
                    current.getBoundingClientRect().height > 40
                  ) {
                    best = current;
                    break;
                  }

                  current = current.parentElement;
                }

                return best;
              };

              for (const link of document.querySelectorAll(
                "a[href*='item.rakuten.co.jp']"
              )) {
                const url = cleanProductUrl(link.href);
                if (!itemUrlPattern.test(url) || seenUrls.has(url)) continue;

                const name = productName(link);
                if (!name) continue;

                const container = productContainer(link);
                const price = normalizeText(container.innerText).match(pricePattern)?.[0];
                if (!price) continue;

                const box = container.getBoundingClientRect();
                if (box.width <= 0 || box.height <= 0) continue;

                seenUrls.add(url);
                productLinks.push({ name, price, url, box });
                if (productLinks.length >= topN) break;
              }

              if (productLinks.length < topN) {
                throw new Error(
                  `expected ${topN} ranking items, found ${productLinks.length}`
                );
              }

              const boxes = productLinks.map((product) => product.box);
              const padding = 12;
              const left = Math.max(0, Math.min(...boxes.map((box) => box.left)) - padding);
              const top = Math.max(0, Math.min(...boxes.map((box) => box.top)) - padding);
              const right = Math.min(
                document.documentElement.scrollWidth,
                Math.max(...boxes.map((box) => box.right)) + padding
              );
              const bottom = Math.min(
                document.documentElement.scrollHeight,
                Math.max(...boxes.map((box) => box.bottom)) + padding
              );

              return {
                products: productLinks.map((product, index) => ({
                  rank: index + 1,
                  name: product.name,
                  price: product.price,
                  url: product.url,
                })),
                clip: {
                  x: left + window.scrollX,
                  y: top + window.scrollY,
                  width: right - left,
                  height: bottom - top,
                },
              };
            }
            """,
                TOP_N,
            )

            page.screenshot(path=tmp_png, clip=result["clip"], full_page=True)
            products = result["products"]
        finally:
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
    try:
        uploaded = (
            service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id, webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )
    except HttpError as exc:
        status = getattr(exc.resp, "status", None)
        if status == 404:
            raise RuntimeError(
                "Google Drive upload failed: DRIVE_FOLDER_ID was not found "
                "or is not shared with the service account."
            ) from None
        reason = ""
        try:
            payload = json.loads(exc.content.decode("utf-8"))
            reason = payload["error"]["errors"][0].get("reason", "")
        except (AttributeError, IndexError, KeyError, TypeError, ValueError):
            pass

        if status == 403 and reason == "storageQuotaExceeded":
            raise RuntimeError(
                "Google Drive upload failed: service accounts cannot create "
                "files in My Drive because they do not have storage quota. "
                "Use a shared drive, or set GOOGLE_AUTH_MODE=oauth and use "
                "OAuth user credentials."
            ) from None
        if status == 403:
            raise RuntimeError(
                "Google Drive upload failed: the credential does not have "
                "permission to create files in DRIVE_FOLDER_ID."
            ) from None
        raise RuntimeError(
            f"Google Drive upload failed with HTTP status {status}."
        ) from None
    return uploaded["webViewLink"]


# ---- スプレッドシート書き込み --------------------------------------------


def write_to_sheet(creds: Credentials, rows: list):
    gc = authorize(creds)
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(SHEET_NAME)
    ws.append_rows(rows, value_input_option=ValueInputOption.user_entered)


# ---- メイン処理 ---------------------------------------------------------


def main():
    now = datetime.now(JST)
    date_str = now.strftime("%y%m%d")  # YYMMDD
    webp_path = None

    try:
        tmp_png, products = scrape_top10()
        webp_path = convert_to_webp(tmp_png, date_str)

        creds = load_google_credentials()

        screenshot_url = upload_to_drive(creds, webp_path, f"{date_str}.webp")

        rows = [
            [
                now.strftime("%Y-%m-%d %H:%M:%S"),
                p["rank"],
                p["name"],
                p["price"],
                p["url"],
                screenshot_url,
            ]
            for p in products
        ]
        write_to_sheet(creds, rows)

        print("Done. Recorded result and uploaded screenshot.")
    finally:
        if webp_path and os.path.exists(webp_path):
            os.remove(webp_path)


if __name__ == "__main__":
    main()
