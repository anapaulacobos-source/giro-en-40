from __future__ import annotations

import argparse
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Obtiene un refresh token de YouTube una sola vez.")
    parser.add_argument("--client-secrets", default="client_secrets.json")
    args = parser.parse_args()
    path = Path(args.client_secrets)
    if not path.exists():
        raise SystemExit(f"No existe {path}. Descarga primero el cliente OAuth tipo Aplicación de escritorio.")
    flow = InstalledAppFlow.from_client_secrets_file(str(path), SCOPES)
    credentials = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    print("\nGuarda estos valores como secretos de GitHub. No los publiques:\n")
    print(f"YOUTUBE_CLIENT_ID={credentials.client_id}")
    print(f"YOUTUBE_CLIENT_SECRET={credentials.client_secret}")
    print(f"YOUTUBE_REFRESH_TOKEN={credentials.refresh_token}")


if __name__ == "__main__":
    main()

