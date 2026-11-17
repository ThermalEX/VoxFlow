"""Compose storyboard sheets from overlay screenshots."""
import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication

SHOTS = Path(sys.argv[1])
OUT = Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
app = QApplication.instance() or QApplication([])

BOARDS = {
    "storyboard1_dictate": ("Storyboard 1 · Dictate, see the edit, confirm (default mode)", [
        ("sb1_1_recording", "Presses Ctrl+Shift+Space and speaks; the live draft may still change."),
        ("sb1_2_animating", "Stops; the local model's edit plays once as a strike-and-fade animation."),
        ("sb1_3_polished", "Edited text with Undo edits and a suggestion chip; Enter pastes it back."),
        ("sb1_4_hover_original", "Hovering Undo edits previews exactly what was said."),
    ]),
    "storyboard2_recover": ("Storyboard 2 · A misread instruction is caught and reversed", [
        ("sb2_1_misread", "Said: “Tell Xiao Li: delete the first sentence, it’s wordy, then give it "
                          "to me by Friday.” The model executes the quoted instruction."),
        ("sb2_2_hover_original", "Hovering Undo edits reveals the full spoken message."),
        ("sb2_3_undone", "One click restores it; nothing has been pasted yet."),
        ("sb2_4_review", "Review mode (optional): every edit is marked in place, not applied."),
        ("sb2_5_review_kept_word", "Clicking the “shorter, like,” edit keeps the user’s words "
                                   "(3 of 4 edits kept)."),
    ]),
    "storyboard3_memory": ("Storyboard 3 · Remember, inspect, reuse (memory on)", [
        ("sb3_1_glow", "“Remember …”: the request word is dropped and the text glows once."),
        ("sb3_2_remembered", "The status line confirms it and says where it is stored."),
        ("sb3_3_memory_page", "Settings › Memory: inspect, edit, delete, keep 7 days or forever."),
        ("sb3_4_fill_offered", "A later related dictation is offered “Fill from memory”."),
        ("sb3_5_filled", "Only after the click are the time and room added."),
    ]),
}

COLS = 3
CELL_W = 500
PAD = 22
BACKDROP = QColor("#2B3140")
INK = QColor("#1E2430")


def framed(image: QImage) -> QImage:
    """Put a translucent overlay grab on a dark desktop-like backdrop."""
    out = QImage(image.size(), QImage.Format.Format_ARGB32)
    out.fill(BACKDROP)
    p = QPainter(out)
    p.drawImage(0, 0, image)
    p.end()
    return out


def wrap(painter, text, width):
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = (line + " " + word).strip()
        if painter.fontMetrics().horizontalAdvance(trial) > width and line:
            lines.append(line)
            line = word
        else:
            line = trial
    lines.append(line)
    return lines


for name, (title, cells) in BOARDS.items():
    images = []
    for shot, caption in cells:
        image = QImage(str(SHOTS / f"{shot}.png"))
        if shot != "sb3_3_memory_page":
            image = framed(image)
        else:  # a light dialog: leave room above it for the number badge
            padded = QImage(image.width() + 40, image.height() + 70, QImage.Format.Format_ARGB32)
            padded.fill(QColor("#EEF1F6"))
            painter = QPainter(padded)
            painter.drawImage(20, 56, image)
            painter.end()
            image = padded
        images.append((image.scaledToWidth(CELL_W, Qt.TransformationMode.SmoothTransformation), caption))
    img_h = max(CELL_W * 356 // 776, max(i.height() for i, _ in images))
    caption_h = 64
    rows = (len(images) + COLS - 1) // COLS
    width = PAD + COLS * (CELL_W + PAD)
    height = 64 + rows * (img_h + caption_h + PAD) + PAD
    sheet = QImage(width, height, QImage.Format.Format_ARGB32)
    sheet.fill(QColor("white"))
    p = QPainter(sheet)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    title_font = QFont("Segoe UI", 15)
    title_font.setBold(True)
    p.setFont(title_font)
    p.setPen(INK)
    p.drawText(QRectF(PAD, 14, width - 2 * PAD, 36), Qt.AlignmentFlag.AlignVCenter, title)
    for index, (image, caption) in enumerate(images):
        row, col = divmod(index, COLS)
        x = PAD + col * (CELL_W + PAD)
        y = 64 + row * (img_h + caption_h + PAD)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(x, y, CELL_W, img_h), 10, 10)
        p.save()
        p.setClipPath(clip)
        p.fillRect(QRectF(x, y, CELL_W, img_h), BACKDROP)
        p.drawImage(int(x), int(y + (img_h - image.height()) / 2), image)
        p.restore()
        # number badge
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#F5B841"))
        p.drawEllipse(QRectF(x + 10, y + 10, 30, 30))
        badge = QFont("Segoe UI", 11)
        badge.setBold(True)
        p.setFont(badge)
        p.setPen(INK)
        p.drawText(QRectF(x + 10, y + 10, 30, 30), Qt.AlignmentFlag.AlignCenter, str(index + 1))
        p.setFont(QFont("Segoe UI", 10))
        p.setPen(INK)
        for n, line in enumerate(wrap(p, caption, CELL_W - 8)[:3]):
            p.drawText(QRectF(x + 2, y + img_h + 8 + n * 19, CELL_W - 4, 19), Qt.AlignmentFlag.AlignLeft, line)
    p.end()
    sheet.save(str(OUT / f"{name}.png"))
    print(name, sheet.size().toTuple())
