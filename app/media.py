"""ARC media lab — REAL image generation, image editing, and video editing.

Image generation: Pollinations.ai text-to-image (free, no API key, real diffusion model output).
Image editing: Pillow — crop/resize/rotate/flip/grayscale/blur/sharpen/text overlay/contrast.
Video editing: ffmpeg — trim/resize/mute/speed/extract-frame/extract-audio/convert/caption.

Every output is a real file written to the media dir and served back over HTTP.
No operation here is simulated — if a tool is missing on the host, we return an
honest error instead of pretending it worked.
"""
import os, time, shutil, uuid, urllib.parse
from typing import Optional
import httpx
from .config import get_settings
from . import terminal

S = get_settings()
MEDIA_DIR = os.path.join(S.ARC_DATA_DIR, "output", "media")
os.makedirs(MEDIA_DIR, exist_ok=True)


def _new_path(ext: str) -> tuple[str, str]:
    fname = f"{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}.{ext}"
    return os.path.join(MEDIA_DIR, fname), f"/media/lib/{fname}"


def list_library(limit: int = 60) -> list:
    try:
        files = sorted(os.listdir(MEDIA_DIR), key=lambda f: os.path.getmtime(os.path.join(MEDIA_DIR, f)), reverse=True)
    except FileNotFoundError:
        return []
    out = []
    for f in files[:limit]:
        ext = f.rsplit(".", 1)[-1].lower()
        kind = "video" if ext in ("mp4", "mov", "webm") else "image"
        out.append({"name": f, "url": f"/media/lib/{f}", "kind": kind,
                    "ts": os.path.getmtime(os.path.join(MEDIA_DIR, f))})
    return out


# ---------------- image generation (real, free, no key) ----------------
async def generate_image(prompt: str, width: int = 1024, height: int = 1024) -> dict:
    """Pollinations.ai — real hosted diffusion model, no API key required."""
    seed = int(time.time()) % 999999
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt) +
           f"?width={width}&height={height}&seed={seed}&nologo=true")
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as c:
            r = await c.get(url)
            if r.status_code != 200 or len(r.content) < 500:
                return {"error": f"image service returned HTTP {r.status_code}"}
            path, media_url = _new_path("png")
            with open(path, "wb") as f:
                f.write(r.content)
            return {"url": media_url, "prompt": prompt}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


# ---------------- image editing (real, Pillow) ----------------
def edit_image(src_path: str, action: str, arg: Optional[str] = None) -> dict:
    try:
        from PIL import Image, ImageFilter, ImageOps, ImageDraw, ImageFont
    except ImportError:
        return {"error": "Pillow not installed on host"}
    try:
        im = Image.open(src_path).convert("RGB")
    except Exception as e:
        return {"error": f"can't open image: {e}"}

    a = (action or "").lower().strip()
    try:
        if a == "grayscale":
            im = ImageOps.grayscale(im).convert("RGB")
        elif a == "blur":
            im = im.filter(ImageFilter.GaussianBlur(radius=float(arg) if arg else 6))
        elif a == "sharpen":
            im = im.filter(ImageFilter.SHARPEN)
        elif a == "invert":
            im = ImageOps.invert(im)
        elif a == "rotate":
            im = im.rotate(-float(arg or 90), expand=True)
        elif a == "flip":
            im = ImageOps.mirror(im) if (arg or "h") == "h" else ImageOps.flip(im)
        elif a == "resize":
            w, h = (arg or "800x800").lower().split("x")
            im = im.resize((int(w), int(h)))
        elif a == "crop_square":
            w, h = im.size
            s = min(w, h)
            im = im.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2))
        elif a == "contrast":
            from PIL import ImageEnhance
            im = ImageEnhance.Contrast(im).enhance(float(arg or 1.4))
        elif a == "caption":
            im = im.copy()
            d = ImageDraw.Draw(im)
            w, h = im.size
            fsize = max(24, w // 18)
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", fsize)
            except Exception:
                font = ImageFont.load_default()
            text = arg or ""
            bbox = d.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            x, y = (w - tw) / 2, h - th - 40
            for dx in (-2, 0, 2):
                for dy in (-2, 0, 2):
                    d.text((x + dx, y + dy), text, font=font, fill="black")
            d.text((x, y), text, font=font, fill="white")
        else:
            return {"error": f"unknown image action '{action}'. Try: grayscale, blur, sharpen, invert, rotate, flip, resize, crop_square, contrast, caption"}
    except Exception as e:
        return {"error": f"edit failed: {type(e).__name__}: {e}"}

    path, media_url = _new_path("png")
    im.save(path)
    return {"url": media_url, "action": a}


# ---------------- video editing (real, ffmpeg) ----------------
def edit_video(src_path: str, action: str, arg: Optional[str] = None) -> dict:
    if not shutil.which("ffmpeg"):
        return {"error": "ffmpeg not installed on this host"}
    a = (action or "").lower().strip()

    if a == "trim":
        start, dur = (arg or "0:5").split(":")
        out, media_url = _new_path("mp4")
        cmd = f'ffmpeg -y -i "{src_path}" -ss {start} -t {dur} -c copy "{out}"'
    elif a == "convert":
        ext = (arg or "mp4").lower()
        out, media_url = _new_path(ext)
        cmd = f'ffmpeg -y -i "{src_path}" "{out}"'
    elif a == "mute":
        out, media_url = _new_path("mp4")
        cmd = f'ffmpeg -y -i "{src_path}" -c copy -an "{out}"'
    elif a == "resize":
        w, h = (arg or "720x1280").lower().split("x")
        out, media_url = _new_path("mp4")
        cmd = f'ffmpeg -y -i "{src_path}" -vf scale={w}:{h} "{out}"'
    elif a == "speed":
        mult = float(arg or 1.5)
        vf = 1 / mult
        out, media_url = _new_path("mp4")
        cmd = f'ffmpeg -y -i "{src_path}" -filter:v "setpts={vf}*PTS" -filter:a "atempo={min(2.0,max(0.5,mult))}" "{out}"'
    elif a == "extract_frame":
        t = arg or "1"
        out, media_url = _new_path("png")
        cmd = f'ffmpeg -y -ss {t} -i "{src_path}" -frames:v 1 "{out}"'
    elif a == "extract_audio":
        out, media_url = _new_path("mp3")
        cmd = f'ffmpeg -y -i "{src_path}" -vn -acodec libmp3lame "{out}"'
    elif a == "caption":
        text = (arg or "").replace("'", "").replace(":", "")
        out, media_url = _new_path("mp4")
        cmd = (f'ffmpeg -y -i "{src_path}" -vf "drawtext=text=\'{text}\':fontcolor=white:fontsize=42:'
               f'box=1:boxcolor=black@0.5:boxborderw=10:x=(w-text_w)/2:y=h-th-60" -codec:a copy "{out}"')
    else:
        return {"error": f"unknown video action '{action}'. Try: trim, convert, mute, resize, speed, extract_frame, extract_audio, caption"}

    res = terminal.run_command(cmd, timeout=120)
    if os.path.exists(out) and os.path.getsize(out) > 500:
        return {"url": media_url, "action": a}
    return {"error": f"ffmpeg failed (exit {res['exit_code']}): {res.get('stderr','')[:300]}"}
