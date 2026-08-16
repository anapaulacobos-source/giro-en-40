from __future__ import annotations

import asyncio
import colorsys
import hashlib
import json
import math
import os
import random
import shutil
import subprocess
import textwrap
import unicodedata
import wave
from pathlib import Path
from typing import Any

import edge_tts
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


PALETTES = {
    "misterio": ("#071A2B", "#173B57", "#65D7FF"),
    "humor": ("#25103D", "#6B2DA1", "#FFD166"),
    "emocion": ("#3A1832", "#8E3B62", "#FFB4A2"),
    "fantasia": ("#081C15", "#1B4332", "#95D5B2"),
    "decision": ("#1D2330", "#3E5C76", "#F4D35E"),
    "ciencia-ficcion": ("#080B2B", "#27296D", "#5CE1E6"),
}

SKIN_TONES = ["#F3C6A5", "#D99B72", "#B97855", "#8D573E", "#F0B98E"]
HAIR_COLORS = ["#241A18", "#4A2D20", "#171719", "#8B5A2B", "#61351F"]
SHIRT_COLORS = ["#FF6B6B", "#4D96FF", "#6BCB77", "#9B5DE5", "#FF9F1C", "#00B4D8"]
PANTS_COLORS = ["#202A44", "#30343F", "#4A4E69", "#2B2D42"]


def run(command: list[str]) -> None:
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode:
        raise RuntimeError(
            f"Falló el comando: {' '.join(command)}\n"
            f"STDOUT:\n{completed.stdout[-1200:]}\nSTDERR:\n{completed.stderr[-2400:]}"
        )


def ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    return float(result.stdout.strip())


def run_validated(command: list[str], output: Path, minimum_duration: float, attempts: int = 2) -> float:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            run(command)
            duration = ffprobe_duration(output)
            if duration < minimum_duration:
                raise RuntimeError(
                    f"El archivo {output.name} quedó incompleto: {duration:.2f}s; "
                    f"se esperaban al menos {minimum_duration:.2f}s."
                )
            return duration
        except (RuntimeError, subprocess.CalledProcessError, ValueError) as exc:
            last_error = exc
            if output.exists():
                output.unlink()
    raise RuntimeError(f"No fue posible generar un archivo válido: {output}") from last_error


def _find_font(bold: bool = False) -> str:
    names = (
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        ]
        if bold
        else [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
        ]
    )
    for candidate in names:
        if Path(candidate).exists():
            return candidate
    raise FileNotFoundError("No encontré una fuente compatible. Instala DejaVu Sans.")


def _hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _gradient(size: tuple[int, int], start: str, end: str) -> Image.Image:
    width, height = size
    a = np.array(_hex_rgb(start), dtype=np.float32)
    b = np.array(_hex_rgb(end), dtype=np.float32)
    t = np.linspace(0, 1, height, dtype=np.float32)[:, None, None]
    row = (a[None, None, :] * (1 - t) + b[None, None, :] * t)
    data = np.repeat(row, width, axis=1).astype(np.uint8)
    return Image.fromarray(data, "RGB")


def _fit_text(text: str, max_width: int, max_height: int) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    bold_path = _find_font(True)
    probe = Image.new("RGB", (max_width, max_height))
    draw = ImageDraw.Draw(probe)
    for size in range(76, 42, -2):
        font = ImageFont.truetype(bold_path, size)
        average = max(12, int(max_width / (size * 0.58)))
        lines = textwrap.wrap(text, width=average, break_long_words=False)
        boxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
        line_h = max((box[3] - box[1] for box in boxes), default=size)
        total_h = len(lines) * line_h + max(0, len(lines) - 1) * 24
        if all(box[2] - box[0] <= max_width for box in boxes) and total_h <= max_height:
            return font, lines
    font = ImageFont.truetype(bold_path, 42)
    return font, textwrap.wrap(text, width=38, break_long_words=False)


def _rounded_card(base: Image.Image, box: tuple[int, int, int, int]) -> None:
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    shadow = (box[0] + 8, box[1] + 14, box[2] + 8, box[3] + 14)
    draw.rounded_rectangle(shadow, radius=46, fill=(0, 0, 0, 82))
    draw.rounded_rectangle(box, radius=46, fill=(4, 8, 20, 185), outline=(255, 255, 255, 45), width=2)
    base.alpha_composite(overlay)


def _normalize(text: str) -> str:
    return "".join(
        character for character in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(character) != "Mn"
    )


def _story_profile(story_id: str, salt: int = 0) -> dict[str, Any]:
    seed = int(hashlib.sha256(f"{story_id}:actor:{salt}".encode()).hexdigest()[:10], 16)
    rng = random.Random(seed)
    return {
        "skin": _hex_rgb(rng.choice(SKIN_TONES)),
        "hair": _hex_rgb(rng.choice(HAIR_COLORS)),
        "shirt": _hex_rgb(rng.choice(SHIRT_COLORS)),
        "pants": _hex_rgb(rng.choice(PANTS_COLORS)),
        "long_hair": rng.choice([True, False]),
        "glasses": rng.random() < 0.24,
    }


def _scene_traits(text: str) -> tuple[str, str, str, str]:
    clean = _normalize(text)
    setting = "room"
    if any(word in clean for word in ("calle", "ciudad", "bus", "avenida", "semaforo", "lluvia")):
        setting = "street"
    elif any(word in clean for word in ("tren", "estacion", "taxi", "viaje")):
        setting = "station"
    elif any(word in clean for word in ("biblioteca", "libro", "carta")):
        setting = "library"
    elif any(word in clean for word in ("oficina", "jefe", "correo", "reunion", "trabajo")):
        setting = "office"
    elif any(word in clean for word in ("jardin", "semilla", "arbol", "planta", "bosque")):
        setting = "garden"
    elif any(word in clean for word in ("cielo", "estrella", "nube")):
        setting = "sky"

    prop = "sparkle"
    prop_groups = [
        (("telefono", "mensaje", "llamada", "pantalla", "autocorrector", "bateria"), "phone"),
        (("ascensor",), "elevator"),
        (("puerta", "manilla"), "door"),
        (("foto", "fotografia", "retrato"), "photo"),
        (("reloj", "minuto", "hora"), "clock"),
        (("tren", "asiento", "estacion"), "train"),
        (("espejo", "reflejo", "vidrio"), "mirror"),
        (("tienda", "estante"), "shop"),
        (("nevera", "refrigerador", "lechuga", "pastel"), "fridge"),
        (("robot",), "robot"),
        (("paquete", "caja"), "package"),
        (("semilla", "arbol", "planta", "bosque"), "plant"),
        (("sombra",), "shadow"),
        (("moneda",), "coin"),
        (("libro", "biblioteca"), "book"),
        (("carta", "nota"), "letter"),
        (("cafe", "taza", "vaso"), "coffee"),
        (("perro",), "dog"),
        (("gato",), "cat"),
        (("boton",), "button"),
        (("luces", "ciudad"), "city"),
        (("mapa", "ruta", "camino"), "map"),
        (("paraguas", "lluvia", "gota"), "rain"),
        (("taxi",), "taxi"),
        (("buzon",), "mailbox"),
        (("semaforo",), "traffic_light"),
        (("maleta",), "suitcase"),
    ]
    for words, candidate in prop_groups:
        if any(word in clean for word in words):
            prop = candidate
            break

    pose = "open"
    if prop == "phone":
        pose = "phone"
    elif prop in {"book", "letter", "photo", "map"}:
        pose = "read"
    elif prop in {"package", "coin", "coffee", "plant", "suitcase"}:
        pose = "hold"
    elif any(word in clean for word in ("corrio", "camino", "viajo", "salio", "entro")):
        pose = "walk"
    elif any(word in clean for word in ("senalo", "mostro", "mira", "miren")):
        pose = "point"
    elif any(word in clean for word in ("saludo", "despedida")):
        pose = "wave"
    elif any(word in clean for word in ("pregunto", "dudo", "decision", "comprendio", "penso")):
        pose = "think"

    expression = "neutral"
    if any(word in clean for word in ("sorpr", "imposible", "aparecio", "solo", "desaparecio", "exactamente")):
        expression = "surprised"
    if any(word in clean for word in ("sonrio", "rio", "carcajada", "aplauso", "gracias", "bien")):
        expression = "happy"
    if any(word in clean for word in ("miedo", "nervios", "cansad", "preocup", "oscuro")):
        expression = "worried"
    if text.strip().endswith("?"):
        expression, pose = "curious", "think"
    return setting, prop, pose, expression


def _draw_setting(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    setting: str,
    accent: tuple[int, int, int],
    rng: random.Random,
) -> None:
    left, top, right, bottom = box
    draw.rounded_rectangle(box, radius=46, fill=(7, 12, 27, 185), outline=(*accent, 95), width=3)
    horizon = bottom - 115
    if setting in {"street", "station"}:
        for index in range(7):
            building_w = 110
            x = left + index * 145 - 35
            h = rng.randint(170, 360)
            draw.rectangle((x, horizon - h, x + building_w, horizon), fill=(19, 35, 58, 235))
            for wy in range(horizon - h + 30, horizon - 20, 55):
                draw.rectangle((x + 20, wy, x + 40, wy + 25), fill=(*accent, 120))
                draw.rectangle((x + 65, wy, x + 85, wy + 25), fill=(255, 230, 150, 105))
        draw.rectangle((left, horizon, right, bottom), fill=(21, 29, 42, 255))
        draw.line((left, horizon + 55, right, horizon + 55), fill=(255, 255, 255, 80), width=6)
    elif setting == "library":
        for shelf_y in (top + 170, top + 360, top + 550):
            draw.rectangle((left + 35, shelf_y, right - 35, shelf_y + 18), fill=(111, 70, 44, 240))
            x = left + 50
            while x < right - 60:
                book_w = rng.randint(24, 45)
                book_h = rng.randint(70, 130)
                color = rng.choice(((205, 78, 90), (69, 123, 157), (238, 174, 71), (93, 168, 128)))
                draw.rectangle((x, shelf_y - book_h, x + book_w, shelf_y), fill=(*color, 235))
                x += book_w + rng.randint(8, 16)
        draw.rectangle((left, horizon, right, bottom), fill=(55, 39, 40, 255))
    elif setting == "office":
        draw.rectangle((left + 45, top + 60, left + 330, top + 270), fill=(28, 54, 76, 240), outline=(*accent, 130), width=5)
        draw.line((left + 187, top + 60, left + 187, top + 270), fill=(*accent, 90), width=4)
        draw.rectangle((left, horizon, right, bottom), fill=(35, 39, 54, 255))
        draw.rectangle((right - 310, horizon - 80, right - 40, horizon - 45), fill=(122, 83, 55, 255))
    elif setting == "garden":
        draw.rectangle((left, horizon, right, bottom), fill=(28, 86, 69, 255))
        for x in range(left + 30, right, 75):
            draw.ellipse((x, horizon - rng.randint(15, 65), x + 60, horizon + 30), fill=(54, 130, 91, 220))
        draw.ellipse((right - 210, top + 65, right - 95, top + 180), fill=(255, 214, 102, 220))
    elif setting == "sky":
        for _ in range(22):
            x, y = rng.randint(left + 20, right - 20), rng.randint(top + 20, bottom - 150)
            r = rng.randint(2, 7)
            draw.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 230, rng.randint(120, 255)))
        draw.rectangle((left, horizon, right, bottom), fill=(31, 55, 77, 255))
    else:
        draw.rectangle((left, horizon, right, bottom), fill=(39, 43, 61, 255))
        draw.rectangle((left + 55, top + 65, left + 330, top + 265), fill=(24, 54, 77, 220), outline=(*accent, 120), width=5)
        draw.line((left + 192, top + 65, left + 192, top + 265), fill=(*accent, 90), width=4)
        draw.ellipse((right - 185, top + 115, right - 85, top + 215), fill=(*accent, 72), outline=(*accent, 145), width=4)


def _limb(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], fill: tuple[int, int, int], width: int) -> None:
    draw.line(points, fill=(16, 19, 29, 255), width=width + 12, joint="curve")
    draw.line(points, fill=(*fill, 255), width=width, joint="curve")
    x, y = points[-1]
    draw.ellipse((x - width // 2, y - width // 2, x + width // 2, y + width // 2), fill=(*fill, 255), outline=(16, 19, 29, 255), width=5)


def _draw_person(
    draw: ImageDraw.ImageDraw,
    cx: int,
    ground: int,
    profile: dict[str, Any],
    pose: str,
    expression: str,
    scale: float = 1.0,
    flip: int = 1,
    silhouette: bool = False,
) -> None:
    s = scale
    skin = (23, 30, 45) if silhouette else profile["skin"]
    hair = (13, 17, 27) if silhouette else profile["hair"]
    shirt = (25, 32, 47) if silhouette else profile["shirt"]
    pants = (18, 24, 37) if silhouette else profile["pants"]
    outline = (12, 16, 27, 255)
    head_r = int(66 * s)
    head_y = ground - int(470 * s)
    shoulder_y = ground - int(365 * s)
    hip_y = ground - int(185 * s)
    foot_y = ground - int(18 * s)
    arm_w = max(18, int(29 * s))
    leg_w = max(22, int(36 * s))

    if pose == "walk":
        _limb(draw, [(cx - int(28*s), hip_y), (cx - int(75*s), ground - int(80*s)), (cx - int(98*s), foot_y)], pants, leg_w)
        _limb(draw, [(cx + int(28*s), hip_y), (cx + int(80*s), ground - int(105*s)), (cx + int(112*s), foot_y)], pants, leg_w)
    else:
        _limb(draw, [(cx - int(28*s), hip_y), (cx - int(35*s), foot_y)], pants, leg_w)
        _limb(draw, [(cx + int(28*s), hip_y), (cx + int(35*s), foot_y)], pants, leg_w)

    left_shoulder = (cx - int(50*s), shoulder_y)
    right_shoulder = (cx + int(50*s), shoulder_y)
    if pose == "phone":
        _limb(draw, [left_shoulder, (cx - int(95*s), shoulder_y + int(85*s)), (cx - int(78*s), head_y + int(18*s))], skin, arm_w)
        _limb(draw, [right_shoulder, (cx + int(85*s), shoulder_y + int(115*s))], skin, arm_w)
    elif pose == "read":
        _limb(draw, [left_shoulder, (cx - int(80*s), shoulder_y + int(105*s)), (cx - int(38*s), shoulder_y + int(145*s))], skin, arm_w)
        _limb(draw, [right_shoulder, (cx + int(80*s), shoulder_y + int(105*s)), (cx + int(38*s), shoulder_y + int(145*s))], skin, arm_w)
    elif pose == "hold":
        _limb(draw, [left_shoulder, (cx - int(95*s), shoulder_y + int(100*s)), (cx - int(55*s), shoulder_y + int(155*s))], skin, arm_w)
        _limb(draw, [right_shoulder, (cx + int(95*s), shoulder_y + int(100*s)), (cx + int(55*s), shoulder_y + int(155*s))], skin, arm_w)
    elif pose in {"point", "wave"}:
        direction = flip
        _limb(draw, [left_shoulder, (cx - direction * int(120*s), shoulder_y - int(55*s)), (cx - direction * int(185*s), shoulder_y - int(70*s))], skin, arm_w)
        _limb(draw, [right_shoulder, (cx + int(78*s), shoulder_y + int(112*s))], skin, arm_w)
    elif pose == "think":
        _limb(draw, [right_shoulder, (cx + int(85*s), shoulder_y + int(85*s)), (cx + int(45*s), head_y + int(50*s))], skin, arm_w)
        _limb(draw, [left_shoulder, (cx - int(70*s), shoulder_y + int(120*s))], skin, arm_w)
    else:
        _limb(draw, [left_shoulder, (cx - int(118*s), shoulder_y + int(45*s)), (cx - int(150*s), shoulder_y + int(5*s))], skin, arm_w)
        _limb(draw, [right_shoulder, (cx + int(118*s), shoulder_y + int(45*s)), (cx + int(150*s), shoulder_y + int(5*s))], skin, arm_w)

    body = (cx - int(70*s), shoulder_y - int(15*s), cx + int(70*s), hip_y + int(20*s))
    draw.rounded_rectangle(body, radius=int(32*s), fill=(*shirt, 255), outline=outline, width=max(5, int(8*s)))
    draw.ellipse((cx - head_r, head_y - head_r, cx + head_r, head_y + head_r), fill=(*skin, 255), outline=outline, width=max(5, int(8*s)))
    if profile["long_hair"]:
        draw.pieslice((cx - head_r - int(10*s), head_y - head_r - int(12*s), cx + head_r + int(10*s), head_y + head_r + int(38*s)), 175, 365, fill=(*hair, 255), outline=outline, width=max(4, int(7*s)))
        draw.ellipse((cx - head_r, head_y - head_r, cx + head_r, head_y + head_r), fill=(*skin, 255), outline=outline, width=max(5, int(8*s)))
    draw.pieslice((cx - head_r, head_y - head_r - int(8*s), cx + head_r, head_y + int(35*s)), 180, 360, fill=(*hair, 255))

    eye_y = head_y - int(5*s)
    eye_dx = int(25*s)
    eye_r = max(3, int(6*s))
    if expression == "worried":
        draw.line((cx - eye_dx - int(10*s), eye_y - int(17*s), cx - eye_dx + int(8*s), eye_y - int(22*s)), fill=outline, width=max(3, int(5*s)))
        draw.line((cx + eye_dx - int(8*s), eye_y - int(22*s), cx + eye_dx + int(10*s), eye_y - int(17*s)), fill=outline, width=max(3, int(5*s)))
    elif expression in {"surprised", "curious"}:
        draw.arc((cx - eye_dx - int(12*s), eye_y - int(25*s), cx - eye_dx + int(12*s), eye_y - int(8*s)), 190, 350, fill=outline, width=max(3, int(5*s)))
        draw.arc((cx + eye_dx - int(12*s), eye_y - int(25*s), cx + eye_dx + int(12*s), eye_y - int(8*s)), 190, 350, fill=outline, width=max(3, int(5*s)))
    draw.ellipse((cx - eye_dx - eye_r, eye_y - eye_r, cx - eye_dx + eye_r, eye_y + eye_r), fill=outline)
    draw.ellipse((cx + eye_dx - eye_r, eye_y - eye_r, cx + eye_dx + eye_r, eye_y + eye_r), fill=outline)
    mouth_y = head_y + int(35*s)
    if expression == "happy":
        draw.arc((cx - int(28*s), mouth_y - int(18*s), cx + int(28*s), mouth_y + int(15*s)), 5, 175, fill=outline, width=max(4, int(7*s)))
    elif expression == "surprised":
        draw.ellipse((cx - int(10*s), mouth_y - int(8*s), cx + int(10*s), mouth_y + int(14*s)), outline=outline, width=max(4, int(6*s)))
    elif expression == "worried":
        draw.arc((cx - int(24*s), mouth_y, cx + int(24*s), mouth_y + int(28*s)), 190, 350, fill=outline, width=max(4, int(6*s)))
    else:
        draw.line((cx - int(18*s), mouth_y + int(5*s), cx + int(18*s), mouth_y + int(5*s)), fill=outline, width=max(4, int(6*s)))

    if profile["glasses"] and not silhouette:
        g = max(3, int(5*s))
        draw.ellipse((cx - int(48*s), eye_y - int(22*s), cx - int(5*s), eye_y + int(22*s)), outline=outline, width=g)
        draw.ellipse((cx + int(5*s), eye_y - int(22*s), cx + int(48*s), eye_y + int(22*s)), outline=outline, width=g)
        draw.line((cx - int(5*s), eye_y, cx + int(5*s), eye_y), fill=outline, width=g)
    if pose == "phone" and not silhouette:
        draw.rounded_rectangle((cx - int(101*s), head_y - int(6*s), cx - int(62*s), head_y + int(70*s)), radius=int(8*s), fill=(25, 31, 45, 255), outline=(120, 224, 255, 255), width=max(3, int(5*s)))
    if pose == "read" and not silhouette:
        draw.polygon([(cx - int(70*s), shoulder_y + int(115*s)), (cx, shoulder_y + int(140*s)), (cx, shoulder_y + int(205*s)), (cx - int(75*s), shoulder_y + int(170*s))], fill=(255, 229, 160, 255), outline=outline)
        draw.polygon([(cx, shoulder_y + int(140*s)), (cx + int(70*s), shoulder_y + int(115*s)), (cx + int(75*s), shoulder_y + int(170*s)), (cx, shoulder_y + int(205*s))], fill=(255, 240, 190, 255), outline=outline)


def _draw_prop(draw: ImageDraw.ImageDraw, kind: str, x: int, y: int, accent: tuple[int, int, int]) -> None:
    dark = (15, 20, 32, 255)
    white = (245, 247, 250, 255)
    if kind == "phone":
        draw.rounded_rectangle((x - 105, y - 205, x + 105, y + 205), radius=28, fill=(28, 34, 51, 255), outline=(*accent, 255), width=10)
        draw.rounded_rectangle((x - 78, y - 155, x + 78, y + 95), radius=14, fill=(201, 242, 255, 255))
        draw.rounded_rectangle((x - 55, y - 95, x + 50, y - 45), radius=20, fill=(*accent, 235))
        draw.rounded_rectangle((x - 25, y - 20, x + 58, y + 30), radius=20, fill=(255, 255, 255, 235))
    elif kind in {"door", "elevator"}:
        draw.rounded_rectangle((x - 150, y - 280, x + 150, y + 250), radius=18, fill=(49, 63, 80, 255), outline=(*accent, 255), width=10)
        if kind == "elevator":
            draw.line((x, y - 270, x, y + 240), fill=(*accent, 150), width=6)
            draw.polygon([(x - 20, y - 330), (x, y - 360), (x + 20, y - 330)], fill=(*accent, 255))
        else:
            draw.ellipse((x + 90, y - 5, x + 115, y + 20), fill=(255, 220, 110, 255), outline=dark, width=4)
    elif kind == "photo":
        draw.polygon([(x - 145, y - 185), (x + 120, y - 215), (x + 155, y + 180), (x - 115, y + 205)], fill=white, outline=dark)
        draw.rectangle((x - 105, y - 140, x + 95, y + 85), fill=(103, 166, 190, 255))
        draw.ellipse((x - 35, y - 95, x + 35, y - 25), fill=(245, 190, 145, 255), outline=dark, width=4)
        draw.polygon([(x - 75, y + 70), (x, y - 10), (x + 75, y + 70)], fill=(*accent, 255))
    elif kind == "clock":
        draw.ellipse((x - 160, y - 160, x + 160, y + 160), fill=(250, 245, 225, 255), outline=(*accent, 255), width=12)
        draw.line((x, y, x, y - 90), fill=dark, width=12)
        draw.line((x, y, x + 75, y + 45), fill=dark, width=12)
        draw.ellipse((x - 13, y - 13, x + 13, y + 13), fill=dark)
    elif kind == "train":
        draw.rounded_rectangle((x - 220, y - 170, x + 220, y + 150), radius=55, fill=(64, 98, 135, 255), outline=(*accent, 255), width=10)
        for wx in (-145, -35, 75):
            draw.rounded_rectangle((x + wx, y - 120, x + wx + 80, y - 25), radius=12, fill=(175, 230, 245, 255))
        draw.ellipse((x - 145, y + 110, x - 65, y + 190), fill=dark)
        draw.ellipse((x + 65, y + 110, x + 145, y + 190), fill=dark)
    elif kind == "mirror":
        draw.rounded_rectangle((x - 145, y - 260, x + 145, y + 245), radius=70, fill=(167, 225, 238, 170), outline=(*accent, 255), width=12)
        draw.ellipse((x - 62, y - 155, x + 62, y - 30), fill=(243, 190, 150, 180), outline=dark, width=5)
        draw.rounded_rectangle((x - 65, y - 25, x + 65, y + 150), radius=30, fill=(*accent, 150), outline=dark, width=5)
    elif kind == "fridge":
        draw.rounded_rectangle((x - 155, y - 280, x + 155, y + 250), radius=26, fill=(225, 238, 240, 255), outline=dark, width=10)
        draw.line((x - 145, y - 40, x + 145, y - 40), fill=dark, width=8)
        draw.line((x + 90, y - 185, x + 90, y - 80), fill=(*accent, 255), width=13)
        draw.ellipse((x - 60, y + 40, x + 60, y + 160), fill=(116, 190, 108, 255), outline=dark, width=5)
    elif kind == "robot":
        draw.rounded_rectangle((x - 120, y - 115, x + 120, y + 175), radius=35, fill=(185, 205, 220, 255), outline=dark, width=10)
        draw.rounded_rectangle((x - 105, y - 280, x + 105, y - 90), radius=35, fill=(211, 226, 235, 255), outline=dark, width=10)
        draw.line((x, y - 280, x, y - 330), fill=dark, width=8)
        draw.ellipse((x - 15, y - 350, x + 15, y - 320), fill=(*accent, 255))
        draw.ellipse((x - 60, y - 215, x - 25, y - 180), fill=(*accent, 255))
        draw.ellipse((x + 25, y - 215, x + 60, y - 180), fill=(*accent, 255))
        draw.arc((x - 55, y - 185, x + 55, y - 120), 10, 170, fill=dark, width=7)
    elif kind in {"dog", "cat"}:
        body_color = (194, 132, 72, 255) if kind == "dog" else (135, 142, 158, 255)
        draw.ellipse((x - 145, y - 40, x + 85, y + 120), fill=body_color, outline=dark, width=8)
        draw.ellipse((x + 30, y - 150, x + 160, y - 10), fill=body_color, outline=dark, width=8)
        ear = [(x + 45, y - 130), (x + 20, y - 220), (x + 90, y - 160)]
        draw.polygon(ear, fill=body_color, outline=dark)
        draw.ellipse((x + 115, y - 100, x + 130, y - 85), fill=dark)
        draw.arc((x - 225, y - 125, x - 105, y + 20), 180, 330, fill=body_color, width=18)
        for lx in (-90, 25):
            draw.line((x + lx, y + 75, x + lx, y + 180), fill=dark, width=25)
            draw.line((x + lx, y + 75, x + lx, y + 175), fill=body_color, width=15)
    elif kind == "plant":
        draw.rectangle((x - 18, y - 40, x + 18, y + 185), fill=(91, 75, 45, 255))
        for dx, dy in ((-100, -80), (15, -150), (90, -55), (-30, 0)):
            draw.ellipse((x + dx - 60, y + dy - 45, x + dx + 60, y + dy + 45), fill=(72, 167, 108, 255), outline=dark, width=5)
        draw.polygon([(x - 115, y + 170), (x + 115, y + 170), (x + 75, y + 300), (x - 75, y + 300)], fill=(190, 97, 65, 255), outline=dark)
    elif kind == "rain":
        draw.arc((x - 190, y - 160, x + 190, y + 210), 180, 360, fill=(*accent, 255), width=20)
        draw.line((x, y + 20, x, y + 250), fill=white, width=15)
        draw.arc((x - 35, y + 215, x + 65, y + 300), 0, 180, fill=white, width=15)
        for dx, dy in ((-170, -250), (-60, -320), (50, -250), (155, -310)):
            draw.line((x + dx, y + dy, x + dx - 25, y + dy + 70), fill=(130, 220, 255, 210), width=10)
    elif kind == "traffic_light":
        draw.rounded_rectangle((x - 85, y - 240, x + 85, y + 170), radius=28, fill=(32, 38, 48, 255), outline=dark, width=8)
        for cy, color in ((y - 160, (235, 76, 82)), (y - 35, (245, 193, 67)), (y + 90, accent)):
            draw.ellipse((x - 52, cy - 52, x + 52, cy + 52), fill=(*color, 255), outline=dark, width=5)
        draw.rectangle((x - 14, y + 170, x + 14, y + 330), fill=(45, 50, 60, 255))
    elif kind == "mailbox":
        draw.rounded_rectangle((x - 140, y - 120, x + 140, y + 80), radius=70, fill=(205, 67, 75, 255), outline=dark, width=9)
        draw.rectangle((x - 140, y - 20, x + 140, y + 100), fill=(205, 67, 75, 255), outline=dark, width=8)
        draw.rectangle((x - 15, y + 95, x + 15, y + 320), fill=(80, 58, 50, 255))
        draw.rectangle((x + 60, y - 190, x + 78, y - 65), fill=(*accent, 255))
        draw.polygon([(x + 78, y - 190), (x + 150, y - 155), (x + 78, y - 120)], fill=(*accent, 255))
    elif kind == "map":
        draw.polygon([(x - 190, y - 170), (x - 55, y - 220), (x + 65, y - 170), (x + 195, y - 220), (x + 175, y + 185), (x + 50, y + 230), (x - 75, y + 180), (x - 200, y + 230)], fill=(244, 226, 166, 255), outline=dark)
        draw.line((x - 65, y - 205, x - 75, y + 180), fill=(120, 101, 75, 255), width=5)
        draw.line((x + 60, y - 165, x + 50, y + 220), fill=(120, 101, 75, 255), width=5)
        draw.line((x - 140, y + 100, x - 20, y - 40, x + 100, y + 70, x + 160, y - 80), fill=(*accent, 255), width=12)
    elif kind == "taxi":
        draw.rounded_rectangle((x - 220, y - 80, x + 220, y + 125), radius=65, fill=(245, 190, 50, 255), outline=dark, width=10)
        draw.polygon([(x - 125, y - 80), (x - 65, y - 190), (x + 100, y - 190), (x + 165, y - 80)], fill=(245, 190, 50, 255), outline=dark)
        draw.rectangle((x - 50, y - 175, x + 75, y - 95), fill=(153, 220, 235, 255))
        draw.ellipse((x - 145, y + 80, x - 55, y + 170), fill=dark)
        draw.ellipse((x + 65, y + 80, x + 155, y + 170), fill=dark)
    elif kind == "suitcase":
        draw.rounded_rectangle((x - 150, y - 120, x + 150, y + 190), radius=32, fill=(190, 115, 75, 255), outline=dark, width=10)
        draw.arc((x - 65, y - 195, x + 65, y - 75), 180, 360, fill=dark, width=13)
        draw.line((x, y - 110, x, y + 180), fill=(*accent, 255), width=10)
    elif kind in {"book", "letter", "coffee", "coin", "package", "button", "shop", "city", "shadow", "sparkle"}:
        if kind == "book":
            draw.polygon([(x - 180, y - 130), (x, y - 75), (x, y + 185), (x - 185, y + 125)], fill=(250, 223, 155, 255), outline=dark)
            draw.polygon([(x, y - 75), (x + 180, y - 130), (x + 185, y + 125), (x, y + 185)], fill=(255, 238, 185, 255), outline=dark)
        elif kind == "letter":
            draw.rectangle((x - 185, y - 125, x + 185, y + 145), fill=white, outline=dark, width=8)
            draw.line((x - 180, y - 120, x, y + 25, x + 180, y - 120), fill=(*accent, 255), width=8)
        elif kind == "coffee":
            draw.rounded_rectangle((x - 120, y - 95, x + 90, y + 135), radius=25, fill=(244, 237, 220, 255), outline=dark, width=9)
            draw.arc((x + 55, y - 45, x + 175, y + 85), 260, 100, fill=white, width=20)
            for dx in (-40, 20, 70):
                draw.arc((x + dx - 25, y - 220, x + dx + 25, y - 80), 90, 270, fill=(*accent, 190), width=7)
        elif kind == "coin":
            draw.ellipse((x - 145, y - 145, x + 145, y + 145), fill=(247, 195, 65, 255), outline=dark, width=11)
            draw.ellipse((x - 95, y - 95, x + 95, y + 95), outline=(255, 235, 140, 255), width=9)
            draw.text((x - 28, y - 62), "?", font=ImageFont.truetype(_find_font(True), 100), fill=dark)
        elif kind == "package":
            draw.rectangle((x - 170, y - 135, x + 170, y + 165), fill=(202, 145, 86, 255), outline=dark, width=10)
            draw.rectangle((x - 28, y - 135, x + 28, y + 165), fill=(*accent, 235))
            draw.line((x - 170, y - 135, x, y - 35, x + 170, y - 135), fill=dark, width=8)
        elif kind == "button":
            draw.polygon([(x - 190, y + 60), (x + 190, y + 60), (x + 150, y + 230), (x - 150, y + 230)], fill=(82, 92, 112, 255), outline=dark)
            draw.ellipse((x - 115, y - 105, x + 115, y + 95), fill=(235, 65, 75, 255), outline=dark, width=12)
        else:
            for angle in range(0, 360, 45):
                radians = math.radians(angle)
                x2, y2 = x + int(160 * math.cos(radians)), y + int(160 * math.sin(radians))
                draw.line((x, y, x2, y2), fill=(*accent, 180), width=10)
            draw.ellipse((x - 55, y - 55, x + 55, y + 55), fill=(*accent, 245), outline=white, width=8)


def _draw_story_stage(
    image: Image.Image,
    story: dict[str, Any],
    text: str,
    index: int,
    accent: tuple[int, int, int],
    rng: random.Random,
) -> None:
    draw = ImageDraw.Draw(image)
    stage = (45, 205, CONFIG["width"] - 45, 1115)
    setting, prop, pose, expression = _scene_traits(text)
    _draw_setting(draw, stage, setting, accent, rng)
    main_profile = _story_profile(story["id"])
    second_profile = _story_profile(story["id"], 1)
    clean = _normalize(text)

    if prop == "shadow":
        _draw_person(draw, 300, 1040, main_profile, pose, expression, scale=0.95, silhouette=True)
        _draw_person(draw, 390, 1040, main_profile, pose, expression, scale=0.95)
        _draw_prop(draw, "sparkle", 790, 600, accent)
    elif prop == "mirror":
        _draw_person(draw, 310, 1040, main_profile, pose, expression, scale=0.95)
        _draw_prop(draw, prop, 790, 635, accent)
    elif prop in {"robot", "dog", "cat", "fridge", "train", "taxi", "traffic_light"}:
        _draw_person(draw, 300, 1040, main_profile, pose, expression, scale=0.92)
        _draw_prop(draw, prop, 770, 680, accent)
    else:
        _draw_person(draw, 315, 1040, main_profile, pose, expression, scale=0.94, flip=-1 if index % 2 else 1)
        _draw_prop(draw, prop, 770, 650, accent)

    if any(word in clean for word in ("mujer", "anciano", "nina", "amiga", "jefe", "abuelo", "conductor", "personas")) and prop not in {"robot", "dog", "cat", "fridge", "train", "taxi"}:
        _draw_person(draw, 820, 1050, second_profile, "open", "happy" if "amiga" in clean else "neutral", scale=0.70, flip=-1)


def make_scene_image(story: dict[str, Any], text: str, index: int, total: int, path: Path) -> None:
    width, height = CONFIG["width"], CONFIG["height"]
    start, end, accent = PALETTES.get(story["category"], PALETTES["misterio"])
    image = _gradient((width, height), start, end).convert("RGBA")
    seed = int(hashlib.sha256(f"{story['id']}:{index}".encode()).hexdigest()[:16], 16)
    rng = random.Random(seed)

    shapes = Image.new("RGBA", image.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shapes)
    accent_rgb = _hex_rgb(accent)
    for _ in range(22):
        radius = rng.randint(30, 170)
        x = rng.randint(-radius, width + radius)
        y = rng.randint(-radius, height + radius)
        alpha = rng.randint(10, 34)
        sdraw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(*accent_rgb, alpha))
    for _ in range(9):
        x1, y1 = rng.randint(0, width), rng.randint(0, height)
        x2, y2 = x1 + rng.randint(-350, 350), y1 + rng.randint(100, 500)
        sdraw.line((x1, y1, x2, y2), fill=(*accent_rgb, rng.randint(18, 45)), width=rng.randint(2, 7))
    shapes = shapes.filter(ImageFilter.GaussianBlur(radius=10))
    image.alpha_composite(shapes)

    draw = ImageDraw.Draw(image)
    small = ImageFont.truetype(_find_font(True), 31)
    brand = CONFIG["brand"]
    label = CONFIG["series_label"]
    draw.text((70, 78), brand, font=small, fill=(*accent_rgb, 255))
    label_box = draw.textbbox((0, 0), label, font=small)
    draw.text((width - 70 - (label_box[2] - label_box[0]), 78), label, font=small, fill=(255, 255, 255, 175))

    progress_left, progress_right, progress_y = 70, width - 70, 145
    draw.rounded_rectangle((progress_left, progress_y, progress_right, progress_y + 10), radius=5, fill=(255, 255, 255, 45))
    progress = progress_left + int((progress_right - progress_left) * (index + 1) / total)
    draw.rounded_rectangle((progress_left, progress_y, progress, progress_y + 10), radius=5, fill=(*accent_rgb, 255))

    # Cada frase se convierte en una viñeta: el protagonista conserva su
    # apariencia y cambia de pose, expresión, escenario y objeto relevante.
    _draw_story_stage(image, story, text, index, accent_rgb, rng)

    # El texto funciona como subtítulo grande sin tapar la actuación.
    card = (66, 1160, width - 66, 1648)
    _rounded_card(image, card)
    draw = ImageDraw.Draw(image)
    font, lines = _fit_text(text, card[2] - card[0] - 110, card[3] - card[1] - 100)
    boxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
    line_heights = [box[3] - box[1] for box in boxes]
    total_height = sum(line_heights) + max(0, len(lines) - 1) * 24
    y = card[1] + (card[3] - card[1] - total_height) // 2
    for line, box, line_height in zip(lines, boxes, line_heights):
        line_width = box[2] - box[0]
        x = (width - line_width) // 2
        draw.text((x + 3, y + 5), line, font=font, fill=(0, 0, 0, 120))
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_height + 24

    category = story["category"].replace("-", " ").upper()
    category_font = ImageFont.truetype(_find_font(True), 34)
    cat_box = draw.textbbox((0, 0), category, font=category_font)
    cat_w = cat_box[2] - cat_box[0]
    draw.rounded_rectangle((width // 2 - cat_w // 2 - 30, 1705, width // 2 + cat_w // 2 + 30, 1769), radius=32, fill=(*accent_rgb, 215))
    draw.text((width // 2 - cat_w // 2, 1716), category, font=category_font, fill=(4, 8, 20, 255))

    counter = f"{index + 1}/{total}"
    counter_box = draw.textbbox((0, 0), counter, font=small)
    draw.text(((width - (counter_box[2] - counter_box[0])) // 2, 1825), counter, font=small, fill=(255, 255, 255, 150))
    image.convert("RGB").save(path, quality=95)


def _natural_speech_text(text: str) -> str:
    """Añade pausas leves sin cambiar el subtítulo visible."""
    speech = text.strip()
    speech = speech.replace(";", ",")
    speech = speech.replace(": ", ":  ")
    return speech


async def synthesize_scenes(story: dict[str, Any], workdir: Path, silent: bool) -> list[Path]:
    audio_files: list[Path] = []
    voice = os.environ.get("VOICE", CONFIG["voice"])
    rate = os.environ.get("VOICE_RATE", CONFIG["voice_rate"])
    pitch = os.environ.get("VOICE_PITCH", "-2Hz")

    # Actualiza automáticamente instalaciones anteriores, para que baste con
    # reemplazar este archivo en GitHub.
    if voice == "es-MX-DaliaNeural":
        voice = "es-CL-CatalinaNeural"
    if rate == "+8%":
        rate = "-2%"

    for index, text in enumerate(story["scenes"]):
        destination = workdir / f"voice_{index:02d}.mp3"
        if silent:
            estimated = max(2.7, len(text.split()) / 2.7)
            run([
                "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                "-t", f"{estimated:.2f}", "-q:a", "9", "-acodec", "libmp3lame", str(destination)
            ])
        else:
            try:
                communicate = edge_tts.Communicate(
                    text=_natural_speech_text(text),
                    voice=voice,
                    rate=rate,
                    pitch=pitch,
                    volume="+0%",
                )
                await communicate.save(str(destination))
            except Exception as exc:
                raise RuntimeError(
                    "No se pudo obtener la voz neural natural. Se detuvo el video para evitar "
                    "publicar una voz robótica; vuelve a ejecutar el workflow."
                ) from exc
        audio_files.append(destination)
    return audio_files


def make_music(duration: float, story_id: str, path: Path) -> None:
    sample_rate = 44100
    total = int((duration + 1) * sample_rate)
    audio = np.zeros(total, dtype=np.float32)
    seed = int(hashlib.sha256(story_id.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    base = rng.choice([196.0, 220.0, 246.94])
    ratios = [1.0, 1.25, 1.5, 2.0]
    beat_seconds = 1.5
    note_length = int(beat_seconds * sample_rate)
    for n, start in enumerate(range(0, total, note_length)):
        freq = base * ratios[(n + seed) % len(ratios)]
        length = min(note_length, total - start)
        t = np.arange(length, dtype=np.float32) / sample_rate
        envelope = np.minimum(1, t / 0.18) * np.exp(-t / 1.25)
        tone = (np.sin(2 * math.pi * freq * t) + 0.35 * np.sin(2 * math.pi * freq * 0.5 * t))
        audio[start : start + length] += tone * envelope * 0.16
    audio = np.clip(audio, -1, 1)
    stereo = np.column_stack((audio, audio))
    pcm = (stereo * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())


def make_thumbnail(story: dict[str, Any], scene_image: Path, output: Path) -> None:
    image = Image.open(scene_image).convert("RGB")
    image.save(output, quality=92)


def render_story(story: dict[str, Any], output_dir: Path, silent: bool = False) -> dict[str, Any]:
    for binary in ("ffmpeg", "ffprobe"):
        if not shutil.which(binary):
            raise RuntimeError(f"Falta {binary}. Instálalo antes de generar el video.")
    output_dir.mkdir(parents=True, exist_ok=True)
    workdir = ROOT / "work" / story["id"]
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)

    audio_files = asyncio.run(synthesize_scenes(story, workdir, silent))
    clip_files: list[Path] = []
    durations: list[float] = []
    total_scenes = len(story["scenes"])
    first_image: Path | None = None
    for index, (text, audio) in enumerate(zip(story["scenes"], audio_files)):
        image_path = workdir / f"scene_{index:02d}.jpg"
        clip_path = workdir / f"clip_{index:02d}.ts"
        make_scene_image(story, text, index, total_scenes, image_path)
        if first_image is None:
            first_image = image_path
        duration = ffprobe_duration(audio) + 0.34
        durations.append(duration)
        fade_out = max(0.1, duration - 0.18)
        vf = (
            "zoompan=z='min(max(zoom,pzoom)+0.00055,1.065)':d=1:"
            "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s={CONFIG['width']}x{CONFIG['height']}:fps={CONFIG['fps']},"
            f"fade=t=in:st=0:d=0.16,fade=t=out:st={fade_out:.3f}:d=0.18,format=yuv420p"
        )
        audio_fade_out = max(0.1, duration - 0.22)
        clip_command = [
            "ffmpeg", "-y", "-loop", "1", "-i", str(image_path), "-i", str(audio),
            "-t", f"{duration:.3f}", "-vf", vf,
            "-af", f"apad,afade=t=in:st=0:d=0.08,afade=t=out:st={audio_fade_out:.3f}:d=0.12",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
            "-f", "mpegts", str(clip_path)
        ]
        run_validated(clip_command, clip_path, max(0.5, duration - 0.18))
        clip_files.append(clip_path)

    concat_file = workdir / "concat.txt"
    concat_file.write_text("".join(f"file '{clip.as_posix()}'\n" for clip in clip_files), encoding="utf-8")
    voice_video = workdir / "voice_video.mp4"
    voice_command = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-map", "0:v:0", "-c:v", "copy", "-an", "-movflags", "+faststart", str(voice_video)
    ]
    run_validated(voice_command, voice_video, max(1.0, sum(durations) - 0.8))

    duration = ffprobe_duration(voice_video)
    narration = workdir / "narration.wav"
    narration_inputs: list[str] = []
    narration_filters: list[str] = []
    narration_labels: list[str] = []
    for index, audio in enumerate(audio_files):
        narration_inputs.extend(["-i", str(audio)])
        label = f"n{index}"
        narration_filters.append(
            f"[{index}:a]apad=pad_dur=0.34,aformat=sample_rates=44100:channel_layouts=stereo[{label}]"
        )
        narration_labels.append(f"[{label}]")
    narration_filters.append(
        "".join(narration_labels) + f"concat=n={len(audio_files)}:v=0:a=1[narration]"
    )
    narration_command = [
        "ffmpeg", "-y", *narration_inputs,
        "-filter_complex", ";".join(narration_filters),
        "-map", "[narration]", "-c:a", "pcm_s16le", str(narration)
    ]
    run_validated(narration_command, narration, max(1.0, sum(durations) - 0.8))

    music = workdir / "music.wav"
    make_music(duration, story["id"], music)
    final_video = output_dir / f"{story['id']}.mp4"
    final_command = [
        "ffmpeg", "-y", "-i", str(voice_video), "-i", str(narration), "-i", str(music),
        "-filter_complex",
        "[1:a]volume=1.12,alimiter=limit=0.92[voice];"
        "[2:a]volume=0.10,afade=t=in:st=0:d=1.2[music];"
        "[voice][music]amix=inputs=2:duration=first:dropout_transition=2[a]",
        "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart", "-shortest", str(final_video)
    ]
    run_validated(final_command, final_video, max(1.0, duration - 0.5))
    thumbnail = output_dir / f"{story['id']}-thumbnail.jpg"
    assert first_image is not None
    make_thumbnail(story, first_image, thumbnail)

    return {
        "video": str(final_video),
        "thumbnail": str(thumbnail),
        "duration_seconds": round(ffprobe_duration(final_video), 2),
        "scene_durations": [round(x, 2) for x in durations],
    }
