from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

OAUTH_CLIENT_PATH = "oauth_client.json"
TOKEN_PATH = "token.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def main():
    flow = InstalledAppFlow.from_client_secrets_file(OAUTH_CLIENT_PATH, SCOPES)
    creds = flow.run_local_server(
        host="localhost",
        port=8080,
        authorization_prompt_message=(
            "Open this URL in your browser and authorize access:\n{url}\n"
        ),
        success_message="OAuth token generated. You can close this tab.",
        open_browser=True,
    )
    Path(TOKEN_PATH).write_text(creds.to_json())
    print(f"wrote {TOKEN_PATH}")


if __name__ == "__main__":
    main()
