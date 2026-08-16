from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
RETRIABLE_STATUS_CODES = {500, 502, 503, 504}


def _credentials() -> Credentials:
    required = ["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError(f"Faltan secretos de YouTube: {', '.join(missing)}")
    return Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        scopes=SCOPES,
    )


def upload_video(video_path: Path, story: dict[str, Any], config: dict[str, Any]) -> str:
    privacy = os.environ.get("YOUTUBE_PRIVACY", "private").strip().lower()
    if privacy not in {"private", "unlisted", "public"}:
        raise ValueError("YOUTUBE_PRIVACY debe ser private, unlisted o public.")
    tags = list(dict.fromkeys(config["default_tags"] + story.get("tags", [])))
    title = f"{story['title']} #Shorts"[:100]
    description = (
        f"{story['description']}\n\n"
        "Microhistoria de ficción original. ¿Qué habrías hecho tú? Cuéntalo en los comentarios.\n\n"
        "#Shorts #Microhistoria #FinalInesperado"
    )
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": str(config.get("category_id", "24")),
            "defaultLanguage": "es",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": False,
        },
    }
    youtube = build("youtube", "v3", credentials=_credentials(), cache_discovery=False)
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=MediaFileUpload(str(video_path), chunksize=-1, resumable=True),
        notifySubscribers=True,
    )
    response = None
    retries = 0
    while response is None:
        try:
            _, response = request.next_chunk()
        except HttpError as exc:
            if exc.resp.status not in RETRIABLE_STATUS_CODES or retries >= 6:
                raise
            delay = random.random() * (2**retries)
            time.sleep(delay)
            retries += 1
    return response["id"]


def write_metadata(path: Path, story: dict[str, Any], render: dict[str, Any], video_id: str | None) -> None:
    payload = {
        "story": story,
        "render": render,
        "youtube_video_id": video_id,
        "youtube_url": f"https://youtu.be/{video_id}" if video_id else None,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

