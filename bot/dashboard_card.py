from __future__ import annotations

import asyncio
from functools import lru_cache
from io import BytesIO
import os
import re

import discord
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


WIDTH = 1600
HEIGHT = 900
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

    _rounded_card(draw, (60, 48, 1540, 238))
    _rounded_card(draw, (60, 270, 410, 430))
    _rounded_card(draw, (430, 270, 780, 430))
    _rounded_card(draw, (800, 270, 1150, 430))
    _rounded_card(draw, (1170, 270, 1540, 430))
    _rounded_card(draw, (60, 458, 860, 840))
    _rounded_card(draw, (890, 458, 1540, 650))
    _rounded_card(draw, (890, 678, 1540, 840))

    _draw_avatar(image, avatar_bytes, (96, 78, 256, 238))
    _draw_header(draw, display_name, username, summary)
    _draw_stat_card(draw, (60, 270, 410, 430), "Study Hours", f"{summary.get('study_hours', 0)}h", "Total logged time across your study journey.")
    _draw_stat_card(
        draw,
        (430, 270, 780, 430),
        "Today vs Goal",
        f"{summary.get('today_hours', 0)}h / {summary.get('daily_goal_hours', 0)}h",
        "How close you are to today's target.",
    )
    _draw_stat_card(draw, (800, 270, 1150, 430), "Focus Minutes", str(summary.get("focus_minutes", 0)), "Timer-based deep work completed.")
    _draw_stat_card(draw, (1170, 270, 1540, 430), "Voice Minutes", str(summary.get("voice_minutes", 0)), "Study voice time tracked automatically.")

    _draw_progress_panel(draw, (60, 458, 860, 840), summary)
    _draw_queue_panel(draw, (890, 458, 1540, 650), tasks, plans, exams)
    _draw_inventory_panel(draw, (890, 678, 1540, 840), inventory)

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


def _draw_header(draw: ImageDraw.ImageDraw, display_name: str, username: str, summary: dict[str, object]) -> None:
    title_font = _font(46, bold=True)
    subtitle_font = _font(22, bold=False)
    pill_font = _font(24, bold=True)
    small_font = _font(18, bold=False)

    draw.text((292, 84), "Study OS Dashboard", font=_font(26, bold=True), fill=(255, 255, 255))
    draw.text((292, 122), _clean_label(display_name, 26), font=title_font, fill=TEXT_PRIMARY)
    draw.text((292, 174), f"@{_clean_label(username, 28)}", font=subtitle_font, fill=TEXT_SECONDARY)
    draw.text((1336, 86), "Student Profile Card", font=_font(22, bold=True), fill=TEXT_PRIMARY, anchor="ra")
    draw.text((1336, 122), "Stay consistent, track the grind, flex the wins.", font=small_font, fill=TEXT_SECONDARY, anchor="ra")

    pills = [
        (f"Level {int(summary.get('level', 1))}", (1128, 164), (245, 236, 221, 255), ACCENT_ORANGE),
        (f"{int(summary.get('coins', 0))} coins", (1296, 164), (221, 247, 242, 255), ACCENT_TEAL),
        (f"{int(summary.get('streak', 0))}-day streak", (1468, 164), (255, 239, 207, 255), ACCENT_GOLD),
    ]
    for text, anchor, fill_color, accent in pills:
        _draw_pill(draw, anchor, text, pill_font, fill_color, accent)


def _draw_stat_card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], label: str, value: str, helper: str) -> None:
    x0, y0, x1, y1 = box
    draw.text((x0 + 28, y0 + 24), label, font=_font(22, bold=True), fill=TEXT_SECONDARY)
    draw.text((x0 + 28, y0 + 72), value, font=_font(36, bold=True), fill=TEXT_PRIMARY)
    helper_lines = _wrap_text(draw, helper, _font(17), x1 - x0 - 56, max_lines=2)
    current_y = y0 + 120
    for line in helper_lines:
        draw.text((x0 + 28, current_y), line, font=_font(17), fill=TEXT_SECONDARY)
        current_y += 21


def _draw_progress_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], summary: dict[str, object]) -> None:
    x0, y0, x1, y1 = box
    width = x1 - x0
    draw.text((x0 + 30, y0 + 24), "Progress Pulse", font=_font(28, bold=True), fill=TEXT_PRIMARY)
    draw.text((x0 + 30, y0 + 62), "Your strongest study trends and today's momentum.", font=_font(18), fill=TEXT_SECONDARY)

    today_hours = float(summary.get("today_hours", 0.0))
    daily_goal = max(0.1, float(summary.get("daily_goal_hours", 0.0) or 0.1))
    ratio = max(0.0, min(1.0, today_hours / daily_goal))
    _draw_progress_bar(draw, (x0 + 30, y0 + 106, x1 - 30, y0 + 136), ratio)
    draw.text((x0 + 30, y0 + 146), f"Daily goal progress: {round(ratio * 100)}%", font=_font(18, bold=True), fill=TEXT_PRIMARY)

    stat_y = y0 + 190
    stats = [
        ("XP", str(int(summary.get("xp", 0)))),
        ("Pending Tasks", str(int(summary.get("pending_tasks", 0)))),
        ("Longest Streak", f"{int(summary.get('longest_streak', summary.get('streak', 0)))} days"),
    ]
    card_width = (width - 100) // 3
    for index, (label, value) in enumerate(stats):
        left = x0 + 30 + index * (card_width + 10)
        right = left + card_width
        draw.rounded_rectangle((left, stat_y, right, stat_y + 88), radius=22, fill=(255, 255, 255, 150))
        draw.text((left + 18, stat_y + 16), label, font=_font(18, bold=True), fill=TEXT_SECONDARY)
        draw.text((left + 18, stat_y + 44), value, font=_font(24, bold=True), fill=TEXT_PRIMARY)

    subject_y = y0 + 316
    draw.text((x0 + 30, subject_y), "Top Subjects This Week", font=_font(22, bold=True), fill=TEXT_PRIMARY)
    subjects = summary.get("top_subjects") or []
    if not isinstance(subjects, list):
        subjects = []
    top_subjects = subjects[:4]
    if not top_subjects:
        draw.text((x0 + 30, subject_y + 42), "No weekly subject data yet. Start logging progress to light this up.", font=_font(18), fill=TEXT_SECONDARY)
        return
    max_hours = max(float(row.get("hours", 0.0)) for row in top_subjects) or 1.0
    line_y = subject_y + 52
    for row in top_subjects:
        subject = _clean_label(str(row.get("subject", "Unknown")), 22)
        hours = float(row.get("hours", 0.0))
        ratio = max(0.08, min(1.0, hours / max_hours))
        draw.text((x0 + 30, line_y), subject, font=_font(18, bold=True), fill=TEXT_PRIMARY)
        draw.text((x1 - 34, line_y), f"{hours}h", font=_font(18, bold=True), fill=TEXT_SECONDARY, anchor="ra")
        _draw_progress_bar(draw, (x0 + 30, line_y + 28, x1 - 34, line_y + 48), ratio, fill=ACCENT_TEAL)
        line_y += 62


def _draw_queue_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], tasks: list[dict], plans: list[dict], exams: list[dict]) -> None:
    x0, y0, x1, y1 = box
    draw.text((x0 + 30, y0 + 24), "Action Queue", font=_font(28, bold=True), fill=TEXT_PRIMARY)
    draw.text((x0 + 30, y0 + 60), "The next things waiting for your attention.", font=_font(18), fill=TEXT_SECONDARY)
    lines: list[str] = []
    for row in tasks[:2]:
        lines.append(f"Task #{row.get('id')}: {_clean_label(str(row.get('content', '')), 52)}")
    for row in plans[:1]:
        lines.append(f"Plan {str(row.get('day', '')).title()}: {row.get('target_date', '')}")
    for row in exams[:1]:
        lines.append(f"Exam #{row.get('id')}: {_clean_label(str(row.get('subject', '')), 24)} on {row.get('exam_date', '')}")
    if not lines:
        lines = ["No active tasks, plans, or exams saved yet."]
    current_y = y0 + 106
    for line in lines[:4]:
        wrapped = _wrap_text(draw, line, _font(20), x1 - x0 - 60, max_lines=2)
        for piece in wrapped:
            draw.text((x0 + 30, current_y), piece, font=_font(20), fill=TEXT_PRIMARY)
            current_y += 28
        current_y += 10


def _draw_inventory_panel(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], inventory: list[dict]) -> None:
    x0, y0, x1, y1 = box
    draw.text((x0 + 30, y0 + 24), "Shop Loadout", font=_font(28, bold=True), fill=TEXT_PRIMARY)
    draw.text((x0 + 30, y0 + 60), "Items you've unlocked and collected from the shop.", font=_font(18), fill=TEXT_SECONDARY)
    if not inventory:
        draw.text((x0 + 30, y0 + 112), "No purchases yet. Save coins and start building your loadout.", font=_font(20), fill=TEXT_PRIMARY)
        return

    current_x = x0 + 30
    current_y = y0 + 104
    max_x = x1 - 28
    chip_font = _font(18, bold=True)
    for index, row in enumerate(inventory[:8]):
        label = _clean_inventory_name(str(row.get("item_name", "Item")))
        text = f"{label} x{int(row.get('quantity', 1))}"
        chip_width = int(_text_width(draw, text, chip_font) + 34)
        if current_x + chip_width > max_x:
            current_x = x0 + 30
            current_y += 56
        fill = CHIP_COLORS[index % len(CHIP_COLORS)]
        draw.rounded_rectangle((current_x, current_y, current_x + chip_width, current_y + 38), radius=19, fill=fill)
        draw.text((current_x + 16, current_y + 8), text, font=chip_font, fill=TEXT_PRIMARY)
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
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()
