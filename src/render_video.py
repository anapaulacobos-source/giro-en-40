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

    card = (66, 400, width - 66, 1455)
    _rounded_card(image, card)
    draw = ImageDraw.Draw(image)
    font, lines = _fit_text(text, card[2] - card[0] - 110, card[3] - card[1] - 150)
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
    draw.rounded_rectangle((width // 2 - cat_w // 2 - 30, 1540, width // 2 + cat_w // 2 + 30, 1604), radius=32, fill=(*accent_rgb, 215))
    draw.text((width // 2 - cat_w // 2, 1551), category, font=category_font, fill=(4, 8, 20, 255))

    counter = f"{index + 1}/{total}"
    counter_box = draw.textbbox((0, 0), counter, font=small)
    draw.text(((width - (counter_box[2] - counter_box[0])) // 2, 1710), counter, font=small, fill=(255, 255, 255, 150))
    image.convert("RGB").save(path, quality=95)


async def synthesize_scenes(story: dict[str, Any], workdir: Path, silent: bool) -> list[Path]:
    audio_files: list[Path] = []
    voice = os.environ.get("VOICE", CONFIG["voice"])
    rate = os.environ.get("VOICE_RATE", CONFIG["voice_rate"])
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
                communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
                await communicate.save(str(destination))
            except Exception as exc:
                if not shutil.which("espeak-ng"):
                    raise RuntimeError(
                        "Falló la narración en línea y no está instalado el respaldo espeak-ng."
                    ) from exc
                fallback_wav = workdir / f"voice_{index:02d}-fallback.wav"
                run(["espeak-ng", "-v", "es", "-s", "172", "-w", str(fallback_wav), text])
                run([
                    "ffmpeg", "-y", "-i", str(fallback_wav), "-ar", "44100", "-ac", "2",
                    "-codec:a", "libmp3lame", "-q:a", "4", str(destination)
                ])
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
