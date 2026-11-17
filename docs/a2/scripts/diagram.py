"""Draw the VoxFlow system diagram as SVG and PNG."""
import sys
from pathlib import Path
from xml.sax.saxutils import escape

OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

W, H = 1440, 800
AI_FILL, AI_STROKE = "#EDE7FB", "#6B4FC8"
SYS_FILL, SYS_STROKE = "#EAF2FB", "#2F6DB5"
RULE_FILL = "#FFF6E0"
USER_FILL = "#F1F3F5"
INK = "#1E2430"
parts = []

boxes = {}


def box(key, x, y, w, h, title, lines=(), kind="sys", status="impl"):
    fill, stroke = {"ai": (AI_FILL, AI_STROKE), "sys": (SYS_FILL, SYS_STROKE), "rule": (RULE_FILL, "#B7862B"),
                    "user": (USER_FILL, "#5B6575"), "sim": ("#F4F4F4", "#7A7A7A")}[kind]
    dash = {"impl": "", "planned": ' stroke-dasharray="8 6"', "sim": ' stroke-dasharray="2 4"'}[status]
    if status == "planned":
        fill = "#FFFFFF"
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" stroke="{stroke}" '
                 f'stroke-width="2"{dash}/>')
    ty = y + 24
    parts.append(f'<text x="{x + 12}" y="{ty}" font-size="15" font-weight="700" fill="{INK}">{escape(title)}</text>')
    if kind == "ai":
        parts.append(f'<text x="{x + w - 12}" y="{ty}" font-size="12" font-weight="700" fill="{AI_STROKE}" '
                     f'text-anchor="end">AI</text>')
    tag = {"planned": "PLANNED", "sim": "SIMULATED"}.get(status)
    if tag:
        parts.append(f'<text x="{x + w - 12}" y="{y + h - 10}" font-size="11" font-weight="700" fill="#8A5A00" '
                     f'text-anchor="end">{tag}</text>')
    for n, line in enumerate(lines):
        parts.append(f'<text x="{x + 12}" y="{ty + 20 + n * 18}" font-size="13" fill="#3A4252">{escape(line)}</text>')
    boxes[key] = (x, y, w, h)


def anchor(key, side, t=0.5):
    x, y, w, h = boxes[key]
    return {"l": (x, y + h * t), "r": (x + w, y + h * t), "t": (x + w * t, y), "b": (x + w * t, y + h)}[side]


def arrow(points, label="", lx=None, ly=None, color="#4A5568", dashed=False, both=False, anchor_="middle"):
    d = "M " + " L ".join(f"{px:.0f} {py:.0f}" for px, py in points)
    dash = ' stroke-dasharray="7 5"' if dashed else ""
    start = ' marker-start="url(#arrowstart)"' if both else ""
    parts.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="2"{dash} marker-end="url(#arrow)"{start}/>')
    if label:
        if lx is None:
            (x1, y1), (x2, y2) = points[len(points) // 2 - 1], points[len(points) // 2]
            lx, ly = (x1 + x2) / 2, (y1 + y2) / 2 - 6
        for n, line in enumerate(label.splitlines()):
            width = len(line) * 6.7 + 8
            left = {"middle": lx - width / 2, "start": lx - 4, "end": lx - width + 4}[anchor_]
            parts.append(f'<rect x="{left:.0f}" y="{ly + n * 15 - 12:.0f}" width="{width:.0f}" height="16" '
                         f'fill="white" fill-opacity="0.92"/>')
            parts.append(f'<text x="{lx:.0f}" y="{ly + n * 15:.0f}" font-size="12" fill="#2D3748" '
                         f'text-anchor="{anchor_}">{escape(line)}</text>')


# Boxes ----------------------------------------------------------------------------------------
box("user", 40, 40, 220, 64, "Person", ["speaks · presses keys · clicks"], kind="user")
box("target", 1140, 40, 220, 64, "Previous app", ["chat, email, document…"], kind="user")
box("paste", 790, 40, 250, 64, "Paste-back", ["clipboard + SendInput"])

box("mic", 40, 180, 220, 64, "Microphone capture", ["audio kept in RAM only"])
box("sched", 40, 300, 220, 64, "Recognition scheduler", ["partial ≈1.2 s · final on stop"])
box("asr", 40, 420, 220, 100, "ASR worker process", ["SenseVoiceSmall INT8", "(sherpa-onnx, local)",
                                                       "incremental segments"], kind="ai")
box("qasr", 40, 560, 220, 80, "Qwen3-ASR comparison", ["candidate ASR, real recordings"], status="planned")

box("overlay", 340, 170, 380, 360, "Overlay (PySide6)", [
    "status line: listening / polishing / ready",
    "live draft while speaking",
    "edit animation (strike & fade)",
    "  or review mode: per-edit keep/reject",
    "Undo edits · hover shows original",
    "0–3 suggestion chips (applied on click)",
    "Continue · Enter confirms · Esc closes",
    "",
    "modes: idle → recording →",
    "            finalizing → result",
])

box("smart", 790, 170, 250, 170, "Smart editor (rules)", [
    "“remember …” detector",
    "pinyin name correction",
    "relative dates resolved by rule",
    "JSON / truncation checks",
    "any failure → keep original",
], kind="rule")
box("llm", 1110, 170, 250, 170, "llama-server (local GPU)", [
    "VoxFlow-rewrite v6",
    "Qwen3.5-2B + LoRA, GGUF",
    "clean · suggest · fill",
    "extract · daily summary",
    "(or any OpenAI-compatible",
    " API, reviewer's own key)",
], kind="ai")

box("store", 340, 610, 230, 84, "Memory store (SQLite)", ["local · off by default", "7 days or forever"])
box("mempage", 600, 610, 210, 84, "Settings › Memory", ["inspect · edit · delete", "change retention"])

box("train", 1110, 380, 250, 90, "Training pipeline", ["seeds → dataset → LoRA → GGUF", "(WSL, offline)"])
box("eval", 1110, 500, 250, 90, "Offline evaluation", ["fixed test sets replayed,", "no participants; v1 → v7"],
    kind="sim", status="sim")
box("study", 870, 620, 490, 74, "Review study", ["log keep / reject decisions; pilot comparing",
                                                 "immediate edits with review mode"], status="planned")

# Arrows ---------------------------------------------------------------------------------------
arrow([anchor("user", "b"), anchor("mic", "t")], "speech", 165, 146, anchor_="start")
arrow([(260, 72), (300, 72), (300, 230), (340, 230)], "keys · clicks", 306, 130, anchor_="start")
arrow([anchor("mic", "b"), anchor("sched", "t")], "audio", 160, 276, anchor_="start")
arrow([anchor("sched", "b"), anchor("asr", "t")], "snapshot + session id", 160, 396, anchor_="start")
arrow([anchor("asr", "r", 0.4), (340, 460)], "partial / final", 300, 484)
arrow([anchor("overlay", "r", 0.2), anchor("smart", "l", 0.32)], "final text", 755, 208)
arrow([anchor("smart", "l", 0.75), anchor("overlay", "r", 0.57)], "edit · chips", 755, 294)
arrow([anchor("smart", "r", 0.3), anchor("llm", "l", 0.3)], "request", 1075, 214)
arrow([anchor("llm", "l", 0.8), anchor("smart", "r", 0.8)], "text / JSON", 1075, 298)
arrow([(530, 170), (530, 72), (790, 72)], "confirmed text", 660, 66)
arrow([anchor("paste", "r"), anchor("target", "l")], "paste", 1090, 66)
arrow([(455, 530), (455, 610)], "confirmed text (if memory on)", 448, 576, anchor_="end")
arrow([anchor("store", "r"), anchor("mempage", "l")], "", both=True)
arrow([(540, 610), (540, 585), (900, 585), (900, 340)], "names · related entries", 720, 579)
arrow([anchor("train", "t"), anchor("llm", "b")], "GGUF", 1242, 364, anchor_="start")
arrow([anchor("eval", "r"), (1395, 545), (1395, 255), (1360, 255)], "replay", 1390, 420, anchor_="end")
arrow([(720, 490), (840, 490), (840, 657), (870, 657)], "decisions", 780, 484, dashed=True)

# Legend ---------------------------------------------------------------------------------------
ly = 730
legend = [
    (SYS_FILL, SYS_STROKE, "", "implemented"),
    ("#FFFFFF", "#2F6DB5", ' stroke-dasharray="8 6"', "planned"),
    ("#F4F4F4", "#7A7A7A", ' stroke-dasharray="2 4"', "simulated (replayed test data)"),
    (AI_FILL, AI_STROKE, "", "AI model"),
    (RULE_FILL, "#B7862B", "", "deterministic rules around the model"),
]
x = 40
for fill, stroke, dash, label in legend:
    parts.append(f'<rect x="{x}" y="{ly}" width="34" height="20" rx="4" fill="{fill}" stroke="{stroke}" '
                 f'stroke-width="2"{dash}/>')
    parts.append(f'<text x="{x + 42}" y="{ly + 15}" font-size="13" fill="{INK}">{escape(label)}</text>')
    x += 70 + len(label) * 7.2
parts.append(f'<path d="M {x} {ly + 10} L {x + 40} {ly + 10}" stroke="#4A5568" stroke-width="2" '
             f'stroke-dasharray="7 5" marker-end="url(#arrow)"/>')
parts.append(f'<text x="{x + 50}" y="{ly + 15}" font-size="13" fill="{INK}">planned flow</text>')

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"
 font-family="Segoe UI, Arial, sans-serif">
<defs>
<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto">
<path d="M 0 0 L 10 5 L 0 10 z" fill="#4A5568"/></marker>
<marker id="arrowstart" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="8" markerHeight="8" orient="auto">
<path d="M 10 0 L 0 5 L 10 10 z" fill="#4A5568"/></marker>
</defs>
<rect width="{W}" height="{H}" fill="white"/>
<text x="40" y="24" font-size="13" fill="#5B6575">VoxFlow system diagram · everything runs on the user's Windows PC unless marked otherwise</text>
{chr(10).join(parts)}
</svg>'''
(OUT / "system_diagram.svg").write_text(svg, encoding="utf-8")

from PySide6.QtCore import QRectF
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer

app = QGuiApplication.instance() or QGuiApplication([])
renderer = QSvgRenderer(str(OUT / "system_diagram.svg"))
image = QImage(W * 2, H * 2, QImage.Format.Format_ARGB32)
image.fill(QColor("white"))
painter = QPainter(image)
painter.setRenderHint(QPainter.RenderHint.Antialiasing)
renderer.render(painter, QRectF(0, 0, W * 2, H * 2))
painter.end()
image.save(str(OUT / "system_diagram.png"))
print("ok")
