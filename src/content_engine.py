from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STORIES_FILE = ROOT / "content" / "stories.json"
STATE_FILE = ROOT / "state" / "used.json"
GENERATED_DIR = ROOT / "content" / "generated"


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _slug(text: str) -> str:
    replacements = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")
    clean = text.translate(replacements).lower()
    clean = re.sub(r"[^a-z0-9]+", "-", clean).strip("-")
    return clean[:58] or hashlib.sha1(text.encode()).hexdigest()[:12]


def all_stories() -> list[dict[str, Any]]:
    stories = _load_json(STORIES_FILE, [])
    for path in sorted(GENERATED_DIR.glob("*.json")):
        generated = _load_json(path, None)
        if generated:
            stories.append(generated)
    return stories


def validate_story(story: dict[str, Any]) -> None:
    required = {"id", "title", "category", "scenes", "description", "tags"}
    missing = required - set(story)
    if missing:
        raise ValueError(f"Faltan campos en la historia: {sorted(missing)}")
    if not isinstance(story["scenes"], list) or not 5 <= len(story["scenes"]) <= 7:
        raise ValueError("La historia debe tener entre 5 y 7 escenas.")
    if any(not isinstance(scene, str) or not 6 <= len(scene.split()) <= 28 for scene in story["scenes"]):
        raise ValueError("Cada escena debe tener entre 6 y 28 palabras.")
    if not story["scenes"][-1].strip().endswith("?"):
        raise ValueError("La última escena debe ser una pregunta.")
    if len(story["title"]) > 82:
        raise ValueError("El título es demasiado largo.")


def _gemini_prompt(existing: list[dict[str, Any]]) -> str:
    recent = "\n".join(f"- {x['title']}: {x['scenes'][0]}" for x in existing[-18:])
    return f"""Crea UNA microhistoria de ficción original en español neutro para un YouTube Short de 35 a 50 segundos.

Audiencia: general, no específicamente infantil. Estilo: visual, sorprendente, cálido o intrigante, apto para anunciantes. Puede ser misterio suave, humor, emoción, fantasía, decisiones o ciencia ficción. Debe tener un giro claro, pero no uses violencia, crimen, sexo, política, salud, dinero fácil, personas reales, tragedias ni terror fuerte.

Entrega exclusivamente un objeto JSON válido con esta forma exacta:
{{
  "title": "máximo 70 caracteres",
  "category": "misterio|humor|emocion|fantasia|decision|ciencia-ficcion",
  "scenes": ["6 escenas; cada una entre 10 y 23 palabras; la primera es un gancho; la sexta es una pregunta para comentarios y termina en ?"],
  "description": "una frase sin hashtags",
  "tags": ["3 a 5 etiquetas breves"]
}}

Evita cualquier parecido con estas historias ya usadas:
{recent}

No agregues markdown, explicaciones ni campos adicionales."""


def _generate_with_gemini(existing: list[dict[str, Any]]) -> dict[str, Any]:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "Se terminaron las historias incluidas. Agrega historias a content/stories.json "
            "o configura GEMINI_API_KEY para crear borradores nuevos."
        )
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite").strip()
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{urllib.parse.quote(model)}:generateContent?key={urllib.parse.quote(api_key)}"
    )
    payload = {
        "contents": [{"parts": [{"text": _gemini_prompt(existing)}]}],
        "generationConfig": {
            "temperature": 1.15,
            "responseMimeType": "application/json",
            "maxOutputTokens": 1200,
        },
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:700]
        raise RuntimeError(f"Gemini devolvió HTTP {exc.code}: {detail}") from exc
    text = result["candidates"][0]["content"]["parts"][0]["text"].strip()
    story = json.loads(text)
    story["id"] = f"auto-{_slug(story['title'])}-{hashlib.sha1(text.encode()).hexdigest()[:6]}"
    validate_story(story)

    title_norm = story["title"].lower()
    hook_norm = story["scenes"][0].lower()
    for old in existing:
        if SequenceMatcher(None, title_norm, old["title"].lower()).ratio() > 0.76:
            raise RuntimeError("El borrador automático se parece demasiado a un título anterior; reintenta.")
        if SequenceMatcher(None, hook_norm, old["scenes"][0].lower()).ratio() > 0.72:
            raise RuntimeError("El borrador automático se parece demasiado a un inicio anterior; reintenta.")

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    destination = GENERATED_DIR / f"{story['id']}.json"
    destination.write_text(json.dumps(story, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return story


def select_next_story() -> dict[str, Any]:
    stories = all_stories()
    for story in stories:
        validate_story(story)
    state = _load_json(STATE_FILE, {"used_ids": [], "uploads": []})
    used = set(state.get("used_ids", []))
    for story in stories:
        if story["id"] not in used:
            return story
    return _generate_with_gemini(stories)


def mark_used(story_id: str, video_id: str | None = None) -> None:
    state = _load_json(STATE_FILE, {"used_ids": [], "uploads": []})
    if story_id not in state["used_ids"]:
        state["used_ids"].append(story_id)
    if video_id:
        state.setdefault("uploads", []).append({"story_id": story_id, "video_id": video_id})
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

