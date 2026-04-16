from __future__ import annotations

import asyncio
from functools import lru_cache
from io import BytesIO
import os
import re

import discord
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


WIDTH = 1900
HEIGHT = 1220
CARD_FILL = (255, 255, 255, 180)
CARD_BORDER = (255, 255, 255, 64)
TEXT_PRIMARY = (24, 33, 56)
TEXT_SECONDARY = (83, 96, 122)
ACCENT_ORANGE = (255, 143, 82)
ACCENT_TEAL = (72, 183, 169)
ACCENT_GOLD = (240, 186, 78)
CHIP_COLORS = [
    (255, 236, 217, 230),
    (219, 246, 241, 230),
    (232, 238, 255, 230),
    (255, 239, 207, 230),
]


async def render_dashboard_card(
    *,
    member: discord.abc.User,
    summary: dict[str, object],
    tasks: list[dict],
    plans: list[dict],
    exams: list[dict],
    inventory: list[dict],
) -> BytesIO:
    avatar_bytes: bytes | None = None
    try:
        avatar_bytes = await member.display_avatar.read()
    except discord.HTTPException:
        avatar_bytes = None
    return await asyncio.to_thread(
        _render_dashboard_card_sync,
        member.display_name,
        getattr(member, "name", str(member)),
        avatar_bytes,
        summary,
        tasks,
        plans,
        exams,
        inventory,
    )


def _render_dashboard_card_sync(
    display_name: str,
    username: str,
    avatar_bytes: bytes | None,
    summary: dict[str, object],
    tasks: list[dict],
    plans: list[dict],
    exams: list[dict],
    inventory: list[dict],
) -> BytesIO:
    image = Image.new("RGBA", (WIDTH, HEIGHT), (18, 26, 48, 255))
    _paint_background(image)
    draw = ImageDraw.Draw(image)

    header_box = (70, 56, 1830, 320)
    stat_boxes = [
        (70, 350, 480, 560),
        (510, 350, 920, 560),
        (950, 350, 1360, 560),
        (1390, 350, 1830, 560),
    ]
    progress_box = (70, 590, 1100, 1150)
    queue_box = (1130, 590, 1830, 850)
    inventory_box = (1130, 880, 1830, 1150)
    avatar_box = (110, 94, 286, 270)

    _rounded_card(draw, header_box)
    for box in stat_boxes:
        _rounded_card(draw, box)
    _rounded_card(draw, progress_box)
    _rounded_card(draw, queue_box)
    _rounded_card(draw, inventory_box)

    _draw_avatar(image, avatar_bytes, avatar_box)
    _draw_header(draw, header_box, display_name, username, summary)
    _draw_stat_card(draw, stat_boxes[0], "Study Hours", f"{summary.get('study_hours', 0)}h", "Total logged time across your study journey.")
    _draw_stat_card(
        draw,
        stat_boxes[1],
        "Today vs Goal",
        f"{summary.get('today_hours', 0)}h / {summary.get('daily_goal_hours', 0)}h",
        "How close you are to today's target.",
    )
    _draw_stat_card(draw, stat_boxes[2], "Focus Minutes", str(summary.get("focus_minutes", 0)), "Timer-based deep work completed.")
    _draw_stat_card(draw, stat_boxes[3], "Voice Minutes", str(summary.get("voice_minutes", 0)), "Study voice time tracked automatically.")

    _draw_progress_panel(draw, progress_box, summary)
    _draw_queue_panel(draw, queue_box, tasks, plans, exams)
    _draw_inventory_panel(draw, inventory_box, inventory)

    output = BytesIO()
    image.convert("RGB").save(output, format="PNG", optimize=True)
    output.seek(0)
    return output


def _paint_background(image: Image.Image) -> None:
    draw = ImageDraw.Draw(image)
    top = (22, 33, 63)
    bottom = (247, 129, 72)
    for y in range(HEIGHT):
        ratio = y / max(1, HEIGHT - 1)
        color = tuple(int(top[index] * (1 - ratio) + bottom[index] * ratio) for index in range(3))
        draw.line((0, y, WIDTH, y), fill=color + (255,))

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    overlay_draw.ellipse((-120, -40, 540, 620), fill=(81, 191, 176, 78))
    overlay_draw.ellipse((1020, 30, 1710, 760), fill=(255, 220, 150, 68))
    overlay_draw.ellipse((920, 540, 1500, 1080), fill=(31, 52, 95, 115))
    overlay_draw.ellipse((140, 560, 620, 1020), fill=(255, 255, 255, 34))
    overlay = overlay.filter(ImageFilter.GaussianBlur(42))
    image.alpha_composite(overlay)

    line_overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    line_draw = ImageDraw.Draw(line_overlay)
    for offset in range(-HEIGHT, WIDTH, 88):
        line_draw.line((offset, 0, offset + HEIGHT, HEIGHT), fill=(255, 255, 255, 18), width=2)
    image.alpha_composite(line_overlay)


def _rounded_card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int]) -> None:
    draw.rounded_rectangle(box, radius=30, fill=CARD_FILL, outline=CARD_BORDER, width=2)


def _draw_avatar(image: Image.Image, avatar_bytes: bytes | None, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    size = min(x1 - x0, y1 - y0)
    avatar = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    if avatar_bytes:
        try:
            base = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
            avatar = ImageOps.fit(base, (size, size), method=Image.Resampling.LANCZOS)
        except Exception:
            avatar = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    if avatar.getbbox() is None:
        placeholder = Image.new("RGBA", (size, size), (255, 255, 255, 0))
        placeholder_draw = ImageDraw.Draw(placeholder)
        placeholder_draw.ellipse((0, 0, size, size), fill=(255, 255, 255, 230))
        placeholder_draw.ellipse((24, 26, size - 24, size - 24), fill=(ACCENT_TEAL[0], ACCENT_TEAL[1], ACCENT_TEAL[2], 255))
        avatar = placeholder
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    image.paste(avatar, (x0, y0), mask)
    border = Image.new("RGBA", image.size, (0, 0, 0, 0))
    border_draw = ImageDraw.Draw(border)
    border_draw.ellipse((x0 - 6, y0 - 6, x1 + 6, y1 + 6), outline=(255, 255, 255, 235), width=6)
    image.alpha_composite(border)


def _draw_header(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    display_name: str,
    username: str,
    summary: dict[str, object],
) -> None:
    x0, y0, x1, _ = box
    title_font = _font(60, bold=True)
    subtitle_font = _font(30, bold=False)
    pill_font = _font(28, bold=True)
    small_font = _font(22, bold=False)

    left = x0 + 240
    right = x1 - 42
    draw.text((left, y0 + 34), "Study OS Dashboard", font=_font(34, bold=True), fill=(255, 255, 255))
    draw.text((left, y0 + 86), _clean_label(display_name, 26), font=title_font, fill=TEXT_PRIMARY)
    draw.text((left, y0 + 162), f"@{_clean_label(username, 28)}", font=subtitle_font, fill=TEXT_SECONDARY)
    draw.text((right, y0 + 40), "Student Profile Card", font=_font(26, bold=True), fill=TEXT_PRIMARY, anchor="ra")
    draw.text((right, y0 + 82), "Stay consistent, track the grind, flex the wins.", font=small_font, fill=TEXT_SECONDARY, anchor="ra")

    pills = [
        (f"Level {int(summary.get('level', 1))}", (x1 - 575, y0 + 196), (245, 236, 221, 255), ACCENT_ORANGE),
        (f"{int(summary.get('coins', 0))} coins", (x1 - 360, y0 + 196), (221, 247, 242, 255), ACCENT_TEAL),
        (f"{int(summary.get('streak', 0))}-day streak", (x1 - 145, y0 + 196), (255, 239, 207, 255), ACCENT_GOLD),
    ]
    for text, anchor, fill_color, accent in pills:
        _draw_pill(draw, anchor, text, pill_font, fill_color, accent)


def _draw_stat_card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], label: str, value: str, helper: str) -> None:
    x0, y0, x1, y1 = box
    draw.text((x0 + 30, y0 + 26), label, font=_font(26, bold=True), fill=TEXT_SECONDARY)
    draw.text((x0 + 30, y0 + 82), value, font=_font(52, bold=True), fill=TEXT_PRIMARY)
    helper_lines = _wrap_text(draw, helper, _font(19), x1 - x0 - 60, max_lines=2)
    current_y = y0 + 152
    for line in helper_lines:
        draw.text((x0 + 30, current_y), line, font=_font(19), fill=TEXT_SECONDARY)
        current_y += 24


def _draw_progress_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], summary: dict[str, object]) -> None:
    x0, y0, x1, y1 = box
    width = x1 - x0
    draw.text((x0 + 32, y0 + 28), "Progress Pulse", font=_font(34, bold=True), fill=TEXT_PRIMARY)
    draw.text((x0 + 32, y0 + 74), "Your strongest study trends and today's momentum.", font=_font(22), fill=TEXT_SECONDARY)

    today_hours = float(summary.get("today_hours", 0.0))
    daily_goal = max(0.1, float(summary.get("daily_goal_hours", 0.0) or 0.1))
    ratio = max(0.0, min(1.0, today_hours / daily_goal))
    _draw_progress_bar(draw, (x0 + 32, y0 + 122, x1 - 32, y0 + 158), ratio)
    draw.text((x0 + 32, y0 + 172), f"Daily goal progress: {round(ratio * 100)}%", font=_font(22, bold=True), fill=TEXT_PRIMARY)

    stat_y = y0 + 228
    stats = [
        ("XP", str(int(summary.get("xp", 0)))),
        ("Pending Tasks", str(int(summary.get("pending_tasks", 0)))),
        ("Longest Streak", f"{int(summary.get('longest_streak', summary.get('streak', 0)))} days"),
    ]
    card_width = (width - 108) // 3
    for index, (label, value) in enumerate(stats):
        left = x0 + 32 + index * (card_width + 12)
        right = left + card_width
        draw.rounded_rectangle((left, stat_y, right, stat_y + 110), radius=22, fill=(255, 255, 255, 150))
        draw.text((left + 20, stat_y + 18), label, font=_font(20, bold=True), fill=TEXT_SECONDARY)
        draw.text((left + 20, stat_y + 52), value, font=_font(32, bold=True), fill=TEXT_PRIMARY)

    subject_y = y0 + 380
    draw.text((x0 + 32, subject_y), "Top Subjects This Week", font=_font(26, bold=True), fill=TEXT_PRIMARY)
    subjects = summary.get("top_subjects") or []
    if not isinstance(subjects, list):
        subjects = []
    top_subjects = subjects[:4]
    if not top_subjects:
        draw.text((x0 + 32, subject_y + 50), "No weekly subject data yet. Start logging progress to light this up.", font=_font(21), fill=TEXT_SECONDARY)
        return
    max_hours = max(float(row.get("hours", 0.0)) for row in top_subjects) or 1.0
    line_y = subject_y + 62
    for row in top_subjects:
        subject = _clean_label(str(row.get("subject", "Unknown")), 22)
        hours = float(row.get("hours", 0.0))
        ratio = max(0.08, min(1.0, hours / max_hours))
        draw.text((x0 + 32, line_y), subject, font=_font(22, bold=True), fill=TEXT_PRIMARY)
        draw.text((x1 - 36, line_y), f"{hours}h", font=_font(22, bold=True), fill=TEXT_SECONDARY, anchor="ra")
        _draw_progress_bar(draw, (x0 + 32, line_y + 32, x1 - 36, line_y + 56), ratio, fill=ACCENT_TEAL)
        line_y += 76


def _draw_queue_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], tasks: list[dict], plans: list[dict], exams: list[dict]) -> None:
    x0, y0, x1, y1 = box
    draw.text((x0 + 32, y0 + 28), "Action Queue", font=_font(34, bold=True), fill=TEXT_PRIMARY)
    draw.text((x0 + 32, y0 + 74), "The next things waiting for your attention.", font=_font(22), fill=TEXT_SECONDARY)
    lines: list[str] = []
    for row in tasks[:2]:
        lines.append(f"Task #{row.get('id')}: {_clean_label(str(row.get('content', '')), 52)}")
    for row in plans[:1]:
        lines.append(f"Plan {str(row.get('day', '')).title()}: {row.get('target_date', '')}")
    for row in exams[:1]:
        lines.append(f"Exam #{row.get('id')}: {_clean_label(str(row.get('subject', '')), 24)} on {row.get('exam_date', '')}")
    if not lines:
        lines = ["No active tasks, plans, or exams saved yet."]
    current_y = y0 + 126
    for line in lines[:4]:
        wrapped = _wrap_text(draw, line, _font(24), x1 - x0 - 64, max_lines=2)
        for piece in wrapped:
            draw.text((x0 + 32, current_y), piece, font=_font(24), fill=TEXT_PRIMARY)
            current_y += 34
        current_y += 16


def _draw_inventory_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], inventory: list[dict]) -> None:
    x0, y0, x1, y1 = box
    draw.text((x0 + 32, y0 + 28), "Shop Loadout", font=_font(34, bold=True), fill=TEXT_PRIMARY)
    draw.text((x0 + 32, y0 + 74), "Items you've unlocked and collected from the shop.", font=_font(22), fill=TEXT_SECONDARY)
    if not inventory:
        draw.text((x0 + 32, y0 + 130), "No purchases yet. Save coins and start building your loadout.", font=_font(24), fill=TEXT_PRIMARY)
        return

    current_x = x0 + 32
    current_y = y0 + 126
    max_x = x1 - 30
    chip_font = _font(20, bold=True)
    for index, row in enumerate(inventory[:8]):
        label = _clean_inventory_name(str(row.get("item_name", "Item")))
        text = f"{label} x{int(row.get('quantity', 1))}"
        chip_width = int(_text_width(draw, text, chip_font) + 38)
        if current_x + chip_width > max_x:
            current_x = x0 + 32
            current_y += 62
        fill = CHIP_COLORS[index % len(CHIP_COLORS)]
        draw.rounded_rectangle((current_x, current_y, current_x + chip_width, current_y + 44), radius=22, fill=fill)
        draw.text((current_x + 18, current_y + 9), text, font=chip_font, fill=TEXT_PRIMARY)
        current_x += chip_width + 12


def _draw_pill(
    draw: ImageDraw.ImageDraw,
    anchor: tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    fill_color: tuple[int, int, int, int],
    accent: tuple[int, int, int],
) -> None:
    text_width = _text_width(draw, text, font)
    x_center, y_center = anchor
    left = int(x_center - text_width / 2 - 20)
    right = int(x_center + text_width / 2 + 20)
    top = y_center - 22
    bottom = y_center + 22
    draw.rounded_rectangle((left, top, right, bottom), radius=22, fill=fill_color)
    draw.text((x_center, y_center), text, font=font, fill=accent, anchor="mm")


def _draw_progress_bar(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
    ratio: float,
    *,
    fill: tuple[int, int, int] = ACCENT_ORANGE,
) -> None:
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=(y1 - y0) // 2, fill=(232, 235, 244))
    filled = x0 + int((x1 - x0) * max(0.0, min(1.0, ratio)))
    draw.rounded_rectangle((x0, y0, max(x0 + 18, filled), y1), radius=(y1 - y0) // 2, fill=fill)


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    max_width: int,
    *,
    max_lines: int,
) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if _text_width(draw, trial, font) <= max_width:
            current = trial
            continue
        lines.append(current)
        current = word
        if len(lines) == max_lines - 1:
            break
    if len(lines) < max_lines:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if len(lines) == max_lines and words:
        while _text_width(draw, lines[-1] + "...", font) > max_width and len(lines[-1]) > 1:
            lines[-1] = lines[-1][:-1]
        if lines[-1] != current or len(words) > len(" ".join(lines).split()):
            lines[-1] = lines[-1].rstrip(". ") + "..."
    return lines


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont) -> float:
    box = draw.textbbox((0, 0), text, font=font)
    return float(box[2] - box[0])


def _clean_label(value: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", value or "").strip()
    compact = re.sub(r"[^\x20-\x7E]", "", compact)
    if len(compact) > limit:
        return compact[: limit - 3] + "..."
    return compact or "Student"


def _clean_inventory_name(value: str) -> str:
    compact = _clean_label(value, 26)
    compact = re.sub(r"^[^A-Za-z0-9]+", "", compact).strip()
    return compact or "Reward Item"


@lru_cache(maxsize=12)
def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_filename = "arialbd.ttf" if bold else "arial.ttf"
    fallback_filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    pil_dir = os.path.dirname(ImageFont.__file__)
    candidates = [
        font_filename,
        fallback_filename,
        os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", font_filename),
        os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", fallback_filename),
        os.path.join("/usr/share/fonts/truetype/dejavu", fallback_filename),
        os.path.join("/usr/share/fonts/dejavu", fallback_filename),
        os.path.join("/usr/share/fonts/truetype/liberation2", "LiberationSans-Bold.ttf" if bold else "LiberationSans-Regular.ttf"),
        os.path.join(pil_dir, "fonts", fallback_filename),
        os.path.join(pil_dir, "Fonts", fallback_filename),
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()
