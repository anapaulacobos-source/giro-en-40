from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from content_engine import mark_used, select_next_story
from render_video import CONFIG, render_story
from youtube_upload import upload_video, write_metadata


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera el próximo Short de Giro en 40.")
    parser.add_argument("--output", default=str(ROOT / "output"))
    parser.add_argument("--no-upload", action="store_true", help="Genera sin subir a YouTube.")
    parser.add_argument("--silent", action="store_true", help="Prueba de video sin TTS ni conexión.")
    parser.add_argument("--keep-unused", action="store_true", help="No marca la historia como utilizada.")
    args = parser.parse_args()

    output_dir = Path(args.output).resolve()
    story = select_next_story()
    print(f"Historia seleccionada: {story['id']} — {story['title']}")
    render = render_story(story, output_dir, silent=args.silent)
    video_id = None
    should_upload = not args.no_upload and not args.silent and os.environ.get("UPLOAD_TO_YOUTUBE", "true").lower() == "true"
    if should_upload:
        video_id = upload_video(Path(render["video"]), story, CONFIG)
        print(f"Subida terminada: https://youtu.be/{video_id}")
    else:
        print(f"Video generado sin subir: {render['video']}")

    if not args.keep_unused:
        mark_used(story["id"], video_id)
    metadata = output_dir / "latest_metadata.json"
    write_metadata(metadata, story, render, video_id)
    print(json.dumps({"story_id": story["id"], **render, "video_id": video_id}, ensure_ascii=False))


if __name__ == "__main__":
    main()

