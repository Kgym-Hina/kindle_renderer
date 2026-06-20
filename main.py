#!/usr/bin/env python3
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

W, H = 600, 800
PAGE_TOP = 20
PAGE_BOTTOM = 24
MARGIN = 24
CARD_GAP = 14
CARD_RADIUS = 20
CARD_BORDER = 3
HEADER_GAP = 12
DEFAULT_OUTPUT_PREFIX = "db"
TEAM_LOGO_DIR = Path("matches/cs/teams")


def load_font(size, bold=False, mono=False):
    candidates = []
    if mono:
        candidates.extend(
            [
                "/System/Library/Fonts/SFNSMono.ttf",
                "/System/Library/Fonts/Menlo.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
                if bold
                else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
            ]
        )
    candidates.extend(
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
            if bold
            else "/System/Library/Fonts/Supplemental/Arial.ttf",
        ]
    )
    for p in candidates:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


FONT_HEADER = load_font(28, True)
FONT_HEADER_META = load_font(18)
FONT_CARD_TITLE = load_font(21, True)
FONT_TEXT = load_font(27)
FONT_SMALL = load_font(20)
FONT_SMALL_MONO = load_font(19, mono=True)
FONT_META = load_font(18)
FONT_BIG = load_font(52, True)
FONT_BIG_MONO = load_font(54, True, mono=True)
FONT_SCORE_MONO = load_font(56, True, mono=True)
FONT_TEAM = load_font(28, True)
FONT_TEAM_SMALL = load_font(23, True)


def text_size(draw, value, font):
    left, top, right, bottom = draw.textbbox((0, 0), str(value), font=font)
    return right - left, bottom - top


def fit_font(draw, value, font_candidates, max_width):
    for font in font_candidates:
        width, _ = text_size(draw, value, font)
        if width <= max_width:
            return font
    return font_candidates[-1]


def text(draw, xy, value, font, fill=0, anchor="la"):
    draw.text(xy, str(value), font=font, fill=fill, anchor=anchor)


def centered_text(draw, center_x, y, value, font, fill=0):
    width, _ = text_size(draw, value, font)
    text(draw, (center_x - width / 2, y), value, font, fill=fill)


def slugify_team_name(value):
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in str(value or ""))
    parts = [part for part in cleaned.split("-") if part]
    return "-".join(parts)


def sample_background_color(image):
    rgba = image.convert("RGBA")
    width, height = rgba.size
    sample_points = [
        (0, 0),
        (min(3, width - 1), 0),
        (0, min(3, height - 1)),
        (min(3, width - 1), min(3, height - 1)),
    ]
    pixels = [rgba.getpixel(point) for point in sample_points]
    r = round(sum(pixel[0] for pixel in pixels) / len(pixels))
    g = round(sum(pixel[1] for pixel in pixels) / len(pixels))
    b = round(sum(pixel[2] for pixel in pixels) / len(pixels))
    a = round(sum(pixel[3] for pixel in pixels) / len(pixels))
    return r, g, b, a


def remove_background(image):
    rgba = image.convert("RGBA")
    bg = sample_background_color(rgba)
    if bg[3] < 8:
        return normalize_foreground_for_white_bg(rgba.convert("LA"))
    grayscale = ImageOps.autocontrast(rgba.convert("L"), cutoff=1)
    mask = Image.new("L", rgba.size, 0)
    source = rgba.load()
    target = mask.load()

    for y in range(rgba.height):
        for x in range(rgba.width):
            r, g, b, a = source[x, y]
            if a == 0:
                target[x, y] = 0
                continue
            distance = math.sqrt((r - bg[0]) ** 2 + (g - bg[1]) ** 2 + (b - bg[2]) ** 2)
            if distance < 18:
                target[x, y] = 0
            elif distance < 42:
                target[x, y] = int(255 * (distance - 18) / 24)
            else:
                target[x, y] = a

    grayscale.putalpha(mask)
    return normalize_foreground_for_white_bg(grayscale)


def normalize_foreground_for_white_bg(image):
    la = image.convert("LA")
    gray = la.getchannel(0)
    alpha = la.getchannel(1)

    total = 0
    count = 0
    for y in range(la.height):
        for x in range(la.width):
            a = alpha.getpixel((x, y))
            if a < 24:
                continue
            total += gray.getpixel((x, y))
            count += 1

    if count == 0:
        return la

    mean_luma = total / count
    if mean_luma > 168:
        gray = ImageOps.invert(gray)
        inverted = Image.merge("LA", (gray, alpha))
        return inverted
    return la


def resolve_local_logo_path(raw, team_name):
    candidates = []
    if raw:
        path = Path(raw)
        if not path.is_absolute():
            path = Path.cwd() / path
        candidates.append(path)
    slug = slugify_team_name(team_name)
    if slug:
        for ext in (".png", ".webp", ".jpg", ".jpeg", ".bmp"):
            candidates.append(Path.cwd() / TEAM_LOGO_DIR / f"{slug}{ext}")
    for path in candidates:
        if path.exists():
            return path
    return None


def resolve_logo_image(mod, key):
    raw = mod.get(key)
    team_name = mod.get("home") if key == "home_logo" else mod.get("away")
    path = resolve_local_logo_path(raw, team_name)
    if not path:
        print(
            f"Missing local logo for '{team_name}'. "
            f"Put an image into {TEAM_LOGO_DIR}/{slugify_team_name(team_name)}.png",
            file=sys.stderr,
        )
        return None
    try:
        return remove_background(Image.open(path))
    except Exception:
        return None


def paste_logo(draw, img, logo, box, label):
    x0, y0, x1, y1 = box
    width = x1 - x0
    height = y1 - y0
    draw.rounded_rectangle(box, radius=18, outline=0, width=2, fill=255)
    if logo is None:
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2
        r = min(width, height) * 0.28
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=0, width=3)
        initials = "".join(part[:1] for part in str(label).split()[:2]).upper() or "?"
        text(draw, (cx, cy + 2), initials[:2], FONT_CARD_TITLE, anchor="mm")
        return
    logo_copy = logo.copy().convert("LA")
    logo_copy.thumbnail((width - 18, height - 18))
    logo_gray = logo_copy.getchannel(0)
    logo_alpha = logo_copy.getchannel(1)
    logo_w, logo_h = logo_gray.size
    logo_canvas = Image.new("L", (logo_w, logo_h), 255)
    logo_canvas.paste(logo_gray, (0, 0), logo_alpha)
    lx = int(x0 + (width - logo_w) / 2)
    ly = int(y0 + (height - logo_h) / 2)
    img.paste(logo_canvas, (lx, ly))


def should_show(mod):
    return mod.get("show", True)


def header_lines(data):
    return data.get("title", "Dashboard"), data.get("subtitle")


def draw_header(draw, data):
    title, updated = header_lines(data)
    title_y = PAGE_TOP
    text(draw, (MARGIN, title_y), title, FONT_HEADER)
    if updated:
        right_text = f"Time Updated: {updated}"
        text(draw, (W - MARGIN, title_y + 5), right_text, FONT_HEADER_META, anchor="ra")
        header_h = max(text_size(draw, title, FONT_HEADER)[1], text_size(draw, right_text, FONT_HEADER_META)[1] + 5)
    else:
        header_h = text_size(draw, title, FONT_HEADER)[1]
    return title_y + header_h + HEADER_GAP


def draw_card_shell(draw, top, height, title):
    x = MARGIN
    w = W - MARGIN * 2
    draw.rounded_rectangle([x, top, x + w, top + height], radius=CARD_RADIUS, outline=0, width=CARD_BORDER, fill=255)
    text(draw, (x + 18, top + 14), title, FONT_CARD_TITLE)
    draw.line((x + 18, top + 44, x + w - 18, top + 44), fill=0, width=2)
    return x, top, w


def measure_metric(mod):
    return 118 + (24 if mod.get("subtitle") else 0)


def draw_metric(draw, img, top, height, mod):
    x, y, w = draw_card_shell(draw, top, height, mod.get("title", "Metric"))
    value = str(mod.get("value", "-"))
    fonts = (
        [FONT_BIG_MONO, load_font(46, True, mono=True), load_font(40, True, mono=True)]
        if mod.get("use_mono")
        else [FONT_BIG, load_font(46, True), load_font(40, True)]
    )
    value_font = fit_font(draw, value, fonts, w - 48)
    value_h = text_size(draw, value, value_font)[1]
    subtitle_h = 24 if mod.get("subtitle") else 0
    value_y = y + max(58, (height - value_h - subtitle_h) / 2 - 2)
    centered_text(draw, x + w / 2, value_y, value, value_font)
    if mod.get("subtitle"):
        centered_text(draw, x + w / 2, y + height - 34, mod["subtitle"], FONT_SMALL)


def measure_status(mod):
    rows = max(1, len(mod.get("items", [])))
    return 74 + rows * 42


def draw_status(draw, img, top, height, mod):
    x, y, w = draw_card_shell(draw, top, height, mod.get("title", "Status"))
    items = mod.get("items", [])
    rows = max(1, len(items))
    rows_height = rows * 42
    start_y = y + 58 + max(0, (height - 74 - rows_height) / 2)
    for i, item in enumerate(items):
        row_y = start_y + i * 42
        label = str(item.get("label", ""))
        value = str(item.get("value", ""))
        text(draw, (x + 24, row_y), label, FONT_TEXT)
        value_w, _ = text_size(draw, value, FONT_TEXT)
        text(draw, (x + w - 24 - value_w, row_y), value, FONT_TEXT)
        if i < len(items) - 1:
            draw.line((x + 22, row_y + 33, x + w - 22, row_y + 33), fill=0, width=1)


def measure_match(mod):
    lines = int(bool(mod.get("meta") or mod.get("league") or mod.get("competition"))) + int(bool(mod.get("subtitle")))
    return 190 + lines * 22


def draw_match(draw, img, top, height, mod):
    x, y, w = draw_card_shell(draw, top, height, mod.get("title", "Match"))
    center_x = x + w / 2
    content_top = y + 54
    logo_size = 84
    left_logo_box = (x + 26, content_top + 6, x + 26 + logo_size, content_top + 6 + logo_size)
    right_logo_box = (x + w - 26 - logo_size, content_top + 6, x + w - 26, content_top + 6 + logo_size)
    paste_logo(draw, img, resolve_logo_image(mod, "home_logo"), left_logo_box, mod.get("home", "-"))
    paste_logo(draw, img, resolve_logo_image(mod, "away_logo"), right_logo_box, mod.get("away", "-"))

    left_team = str(mod.get("home", "-"))
    right_team = str(mod.get("away", "-"))
    team_fonts = [FONT_TEAM, FONT_TEAM_SMALL, load_font(20, True)]
    team_y = left_logo_box[3] + 12
    centered_text(draw, left_logo_box[0] + logo_size / 2, team_y, left_team, fit_font(draw, left_team, team_fonts, 158))
    centered_text(draw, right_logo_box[0] + logo_size / 2, team_y, right_team, fit_font(draw, right_team, team_fonts, 158))

    score = str(mod.get("score", mod.get("time", "-")))
    score_fonts = (
        [FONT_SCORE_MONO, load_font(48, True, mono=True), load_font(42, True, mono=True)]
        if mod.get("use_mono", True)
        else [FONT_BIG, load_font(46, True), load_font(40, True)]
    )
    score_font = fit_font(draw, score, score_fonts, 200)
    centered_text(draw, center_x, content_top + 26, score, score_font)

    type_label = mod.get("match_type") or mod.get("type_label") or mod.get("status")
    if type_label:
        type_text = str(type_label).upper()
        tw, th = text_size(draw, type_text, FONT_META)
        box = (center_x - tw / 2 - 10, content_top - 2, center_x + tw / 2 + 10, content_top + th + 10)
        draw.rounded_rectangle(box, radius=12, outline=0, width=2, fill=255)
        text(draw, (center_x, box[1] + (box[3] - box[1]) / 2), type_text, FONT_META, anchor="mm")

    meta_lines = []
    meta = mod.get("meta") or mod.get("league") or mod.get("competition")
    if meta:
        meta_lines.append(str(meta))
    if mod.get("subtitle"):
        meta_lines.append(str(mod["subtitle"]))
    meta_font = FONT_SMALL_MONO
    max_meta_width = w - 100
    meta_y = y + height - 10 - len(meta_lines) * 16
    for line in meta_lines:
        line_font = fit_font(draw, line, [meta_font, load_font(17, mono=True), load_font(16, mono=True)], max_meta_width)
        centered_text(draw, center_x, meta_y, line, line_font)
        meta_y += 16


RENDERERS = {
    "metric": {"measure": measure_metric, "draw": draw_metric, "stretch": 70},
    "status": {"measure": measure_status, "draw": draw_status, "stretch": 80},
    "match": {"measure": measure_match, "draw": draw_match, "stretch": 90},
}


def build_pages(data):
    modules = [m for m in data.get("modules", []) if should_show(m) and m.get("type") in RENDERERS]
    probe = ImageDraw.Draw(Image.new("L", (W, H), 255))
    header_bottom = draw_header(probe, data)
    usable_height = H - PAGE_BOTTOM - header_bottom

    pages = []
    current_page = []
    current_height = 0
    for mod in modules:
        min_height = RENDERERS[mod["type"]]["measure"](mod)
        needed = min_height if not current_page else min_height + CARD_GAP
        if current_page and current_height + needed > usable_height:
            pages.append(current_page)
            current_page = []
            current_height = 0
            needed = min_height
        current_page.append({"mod": mod, "min_height": min_height})
        current_height += needed
    if current_page or not pages:
        pages.append(current_page)
    return pages


def compute_heights(page, free_space):
    heights = [entry["min_height"] for entry in page]
    if free_space <= 0 or not page:
        return heights
    caps = [RENDERERS[entry["mod"]["type"]]["stretch"] for entry in page]
    remaining = free_space
    while remaining > 0:
        progressed = False
        for i in range(len(heights)):
            if heights[i] - page[i]["min_height"] < caps[i]:
                heights[i] += 1
                remaining -= 1
                progressed = True
                if remaining == 0:
                    break
        if not progressed:
            break
    return heights


def render_page(data, page):
    img = Image.new("L", (W, H), 255)
    draw = ImageDraw.Draw(img)
    header_bottom = draw_header(draw, data)
    min_total = sum(entry["min_height"] for entry in page)
    gaps = CARD_GAP * max(0, len(page) - 1)
    free_space = max(0, H - PAGE_BOTTOM - header_bottom - min_total - gaps - 8)
    heights = compute_heights(page, free_space)
    y = header_bottom + 8
    for i, (entry, height) in enumerate(zip(page, heights)):
        renderer = RENDERERS[entry["mod"]["type"]]["draw"]
        renderer(draw, img, int(y), int(height), entry["mod"])
        y += height
        if i < len(page) - 1:
            y += CARD_GAP
    return img


def output_prefix(output):
    path = Path(output)
    stem = path.stem.lower()
    prefix = "db" if not stem.startswith("db") else path.stem.split("_")[0]
    return path.parent, prefix


def cleanup_stale_outputs(directory, prefix, keep_count):
    for path in sorted(directory.glob(f"{prefix}_*.png")):
        suffix = path.stem[len(prefix) + 1 :]
        if not suffix.isdigit():
            continue
        if int(suffix) > keep_count:
            path.unlink(missing_ok=True)


def render(data, output):
    pages = build_pages(data)
    directory, prefix = output_prefix(output)
    directory.mkdir(parents=True, exist_ok=True)
    generated = []
    for i, page in enumerate(pages, start=1):
        img = render_page(data, page)
        out = directory / f"{prefix}_{i}.png"
        img.save(out)
        generated.append(out)
    cleanup_stale_outputs(directory, prefix, len(generated))
    return generated


def main():
    if len(sys.argv) < 3:
        print("Usage: python main.py data.json output.png")
        sys.exit(1)
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        data = json.load(f)
    for path in render(data, sys.argv[2]):
        print(path.name)


if __name__ == "__main__":
    main()
