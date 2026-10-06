"""Bottom-screen overlay for local voice recognition."""

import ctypes
import math
import sys
import time
from concurrent.futures import Future, ProcessPoolExecutor
from pathlib import Path

import sounddevice as sd
from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCloseEvent, QCursor, QImage, QKeyEvent, QLinearGradient, QPainter, QRadialGradient, QRegion
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMenu,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .audio import AudioBuffer
from .overlay_widgets import CircleIconButton, GlowCapsule
from .particles import ParticleField
from .recognizer import initialize_worker, transcribe_in_worker, worker_ready
from .scheduler import RecognitionJob, RecognitionScheduler


HOTKEY_ID = 0x564F
WM_HOTKEY = 0x0312


class VoxFlowWindow(QWidget):
    def __init__(self, model_dir: str | Path, start_worker: bool = True) -> None:
        super().__init__()
        self.model_dir = Path(model_dir)
        self.audio = AudioBuffer(max_seconds=30)
        self.scheduler: RecognitionScheduler | None = None
        self.stream: sd.InputStream | None = None
        self.executor: ProcessPoolExecutor | None = None
        self.ready_future: Future[bool] | None = None
        self.result_future: Future[str] | None = None
        self.result_job: RecognitionJob | None = None
        self.model_ready = False
        self.capture_warning = ""
        self.limit_reached = False
        self.hotkey_registered = False
        self._animation: QPropertyAnimation | None = None
        self.particles = ParticleField(820, 310)
        self._edge_mask: QImage | None = None
        self._last_particle_tick: float | None = None
        self._background_progress = 0.0
        self._background_revealing = False
        self._background_retracting = False

        self.setWindowTitle("VoxFlow")
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(820, 310)
        self._place_at_bottom()
        self.particles.resize(self.width(), self.height())
        self._build_ui()
        self._load_devices()
        self._set_mode("idle")

        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._poll)
        self.timer.start()
        self.particle_timer = QTimer(self)
        self.particle_timer.setTimerType(Qt.TimerType.PreciseTimer)
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        self.particle_timer.setInterval(self._frame_interval(screen.refreshRate() if screen else 60))
        self.particle_timer.timeout.connect(self._animate_particles)

        if start_worker:
            self._start_worker()

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QWidget { color: #F3F7FF; font-family: 'Segoe UI'; }
            QLabel#status { font-size: 16px; font-weight: 500; color: #F3F7FF; }
            QLabel#muted { font-size: 11px; color: #DBE9FF; }
            QTextEdit { background: transparent; border: none; color: #F3F7FF; font-size: 24px;
                        selection-background-color: #376DE0; }
            QMenu { background: #161E31; color: #F3F6FF; border: 1px solid #354466; padding: 5px; }
            QMenu::item { padding: 7px 18px; }
            QMenu::item:selected { background: #294A87; }
            """
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 16, 28, 22)
        layout.setSpacing(7)
        layout.addStretch(1)
        self.time_label = QLabel("00:00 / 00:30")
        self.time_label.setObjectName("muted")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.time_label)
        self.status_label = QLabel("Loading local speech model…")
        self.status_label.setObjectName("status")
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._add_text_shadow(self.status_label)
        layout.addWidget(self.status_label)
        self.transcript = QTextEdit()
        self.transcript.setPlaceholderText("Say something…")
        self.transcript.setReadOnly(True)
        self.transcript.viewport().setAutoFillBackground(False)
        self.transcript.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.transcript)
        layout.addSpacing(18)

        controls = QHBoxLayout()
        controls.setSpacing(14)
        controls.addStretch(1)
        self.device_button = CircleIconButton("device", "Select microphone")
        self.device_button.clicked.connect(self._show_device_menu)
        controls.addWidget(self.device_button)
        self.copy_button = CircleIconButton("copy", "Copy text")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self._copy_text)
        controls.addWidget(self.copy_button)
        controls.addSpacing(14)
        self.capsule = GlowCapsule()
        self.capsule.setEnabled(False)
        self.capsule.setToolTip("Start voice input")
        capsule_shadow = QGraphicsDropShadowEffect(self.capsule)
        capsule_shadow.setBlurRadius(20)
        capsule_shadow.setOffset(0, 2)
        capsule_shadow.setColor(QColor(16, 29, 49, 105))
        self.capsule.setGraphicsEffect(capsule_shadow)
        self.capsule.clicked.connect(self.toggle_recording)
        controls.addWidget(self.capsule)
        controls.addSpacing(14)
        self.record_button = CircleIconButton("mic", "Start recording")
        self.record_button.setEnabled(False)
        self.record_button.setToolTip("Shortcut: Ctrl+Shift+Space")
        self.record_button.clicked.connect(self.toggle_recording)
        controls.addWidget(self.record_button)
        self.close_button = CircleIconButton("close", "Hide overlay")
        self.close_button.clicked.connect(self.hide_overlay)
        controls.addWidget(self.close_button)
        self.action_buttons = (self.device_button, self.copy_button, self.record_button, self.close_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        self.device_box = QComboBox(self)
        self.device_box.hide()

    @staticmethod
    def _add_text_shadow(label: QLabel) -> None:
        effect = QGraphicsDropShadowEffect(label)
        effect.setBlurRadius(9)
        effect.setOffset(0, 1)
        effect.setColor(QColor(12, 31, 87, 180))
        label.setGraphicsEffect(effect)

    def _show_device_menu(self) -> None:
        if self.stream is not None:
            return
        menu = QMenu(self)
        for index in range(self.device_box.count()):
            action = menu.addAction(self.device_box.itemText(index))
            action.setCheckable(True)
            action.setChecked(index == self.device_box.currentIndex())
            action.triggered.connect(lambda _checked=False, selected=index: self.device_box.setCurrentIndex(selected))
        menu.exec(self.device_button.mapToGlobal(self.device_button.rect().topLeft()))

    def _set_mode(self, mode: str) -> None:
        previous_mode = getattr(self, "mode", None)
        self.mode = mode
        self.transcript.setVisible(mode != "idle")
        self.status_label.setVisible(mode != "idle")
        if mode != "idle":
            self.transcript.setFixedHeight(82 if mode == "recording" else 102)
        self.device_button.setEnabled(mode != "recording")
        self.time_label.setVisible(mode == "recording")
        self.capsule.setToolTip("Stop recording" if mode == "recording" else "Start voice input")
        self.capsule.setAccessibleName("Stop recording" if mode == "recording" else "Start voice input")
        self.record_button.setToolTip("Stop recording" if mode == "recording" else "Start recording")
        self.record_button.setAccessibleName("Stop recording" if mode == "recording" else "Start recording")
        self.record_button.icon_name = "stop" if mode == "recording" else "mic"
        self.record_button.update()
        self.capsule.set_recording(mode == "recording" and self.stream is not None)
        if mode != "recording":
            self.capsule.reset()
        if mode == "recording" and previous_mode != "recording":
            self._background_progress = 0.0
            self._background_revealing = True
            self._background_retracting = False
        elif mode == "idle":
            if not self._background_retracting:
                self._background_progress = 0.0
            self._background_revealing = False
        if self.isVisible():
            self._update_input_mask()

    def _update_input_mask(self) -> None:
        if self.mode == "recording" or self._background_progress > 0:
            self.clearMask()
            return
        self.layout().activate()
        region = QRegion()
        for control in (*self.action_buttons, self.capsule):
            region = region.united(QRegion(control.geometry().adjusted(-14, -14, 14, 14)))
        if self.mode == "result":
            for content in (self.status_label, self.transcript):
                if content.isVisible():
                    region = region.united(QRegion(content.geometry().adjusted(-6, -6, 6, 6)))
        self.setMask(region)

    def paintEvent(self, _event) -> None:
        """Composite every effect before fading the whole surface at its edges."""
        if self._background_progress <= 0:
            return
        if self._edge_mask is None or self._edge_mask.size() != self.size():
            self._edge_mask = self._make_edge_mask()
        frame = self._make_backdrop()
        painter = QPainter(frame)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.particles.pointer is not None:
            halo = QRadialGradient(QPointF(*self.particles.pointer), 145)
            halo.setColorAt(0.0, QColor(181, 217, 255, 52))
            halo.setColorAt(1.0, QColor(181, 217, 255, 0))
            painter.fillRect(self.rect(), halo)
        painter.setPen(Qt.PenStyle.NoPen)
        energy = self.capsule.level if self.stream is not None else 0.0
        for index, particle in enumerate(self.particles.particles):
            highlight = 0
            if self.particles.pointer is not None:
                distance = math.hypot(particle.x - self.particles.pointer[0], particle.y - self.particles.pointer[1])
                highlight = int(max(0.0, 1 - distance / 142) * 110)
            opacity = min(235, particle.opacity + highlight + round(energy * 80))
            color = QColor(214, 233, 255, opacity)
            if index % 5 == 0:
                color = QColor(245, 250, 255, opacity)
            painter.setBrush(color)
            radius = particle.radius * (1 + energy * 0.75)
            painter.drawEllipse(QPointF(particle.x, particle.y), radius, radius)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        painter.drawImage(0, 0, self._edge_mask)
        if self._background_progress < 1:
            eased = self._background_progress ** 0.85
            origin = self.capsule.mapTo(self, self.capsule.rect().center())
            radius = max(1.0, eased * math.hypot(self.width() / 2, self.height()) * 1.05)
            reveal = QRadialGradient(QPointF(origin), radius)
            reveal.setColorAt(0.0, QColor(255, 255, 255, 255))
            reveal.setColorAt(0.82, QColor(255, 255, 255, 255))
            reveal.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.fillRect(frame.rect(), reveal)
        painter.end()
        window_painter = QPainter(self)
        window_painter.drawImage(0, 0, frame)
        window_painter.end()

    def _make_backdrop(self) -> QImage:
        """Draw slow overlapping light clouds with an uneven, moving outline."""
        backdrop = QImage(self.size(), QImage.Format.Format_ARGB32_Premultiplied)
        backdrop.fill(Qt.GlobalColor.transparent)
        painter = QPainter(backdrop)
        phase = self.particles.time
        width, height = self.width(), self.height()
        clouds = (
            (0.28 + 0.025 * math.sin(phase * 0.48), 0.75 + 0.085 * math.sin(phase * 0.64),
             0.25, 0.62, (43, 101, 212), 155 + round(22 * math.sin(phase * 0.7))),
            (0.50 + 0.045 * math.sin(phase * 0.43 + 1.2), 0.77 + 0.070 * math.sin(phase * 0.52),
             0.40, 0.67, (60, 120, 224), 175 - round(20 * math.sin(phase * 0.6))),
            (0.72 + 0.025 * math.sin(phase * 0.50 + 2.2), 0.80 + 0.085 * math.cos(phase * 0.68),
             0.25, 0.60, (67, 138, 238), 150 + round(18 * math.sin(phase * 0.8))),
            (0.50 + 0.025 * math.sin(phase * 0.32 + 2), 0.96,
             0.44, 0.40, (96, 160, 246), 82),
        )
        painter.setPen(Qt.PenStyle.NoPen)
        for cx, cy, rx, ry, rgb, opacity in clouds:
            painter.save()
            painter.translate(cx * width, cy * height)
            painter.scale(rx * width, ry * height)
            glow = QRadialGradient(QPointF(0, 0), 1)
            glow.setColorAt(0.0, QColor(*rgb, opacity))
            glow.setColorAt(0.48, QColor(*rgb, round(opacity * 0.68)))
            glow.setColorAt(0.72, QColor(*rgb, round(opacity * 0.15)))
            glow.setColorAt(0.90, QColor(*rgb, 0))
            glow.setColorAt(1.0, QColor(*rgb, 0))
            painter.fillRect(QRectF(-1, -1, 2, 2), glow)
            painter.restore()
        painter.end()
        return backdrop

    def _make_edge_mask(self) -> QImage:
        mask = QImage(self.size(), QImage.Format.Format_ARGB32_Premultiplied)
        mask.fill(Qt.GlobalColor.transparent)
        painter = QPainter(mask)
        horizontal = QLinearGradient(0, 0, self.width(), 0)
        for position, alpha in ((0.0, 0), (0.006, 0), (0.04, 76), (0.13, 232), (0.22, 255),
                                (0.78, 255), (0.87, 232), (0.96, 76), (0.994, 0), (1.0, 0)):
            horizontal.setColorAt(position, QColor(255, 255, 255, alpha))
        painter.fillRect(mask.rect(), horizontal)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        vertical = QLinearGradient(0, 0, 0, self.height())
        for position, alpha in ((0.0, 0), (0.01, 0), (0.05, 110), (0.16, 255),
                                (0.83, 255), (0.94, 135), (0.98, 0), (1.0, 0)):
            vertical.setColorAt(position, QColor(255, 255, 255, alpha))
        painter.fillRect(mask.rect(), vertical)
        painter.end()
        return mask

    def _animate_particles(self) -> None:
        now = time.perf_counter()
        dt = min(1 / 20, max(1 / 120, now - self._last_particle_tick)) if self._last_particle_tick else 1 / 60
        self._last_particle_tick = now
        cursor = self.mapFromGlobal(QCursor.pos())
        pointer = (float(cursor.x()), float(cursor.y())) if self.rect().contains(cursor) else None
        if self._background_revealing:
            self._background_progress = min(1.0, self._background_progress + dt / 0.56)
            if self._background_progress >= 1:
                self._background_revealing = False
        elif self._background_retracting:
            self._background_progress = max(0.0, self._background_progress - dt / 0.48)
            if self._background_progress <= 0:
                self._background_retracting = False
                self._update_input_mask()
        if self.stream is not None:
            self.capsule.set_level(self.audio.recent_level)
        self.capsule.tick(dt)
        self.particles.step(pointer, dt=dt, energy=self.capsule.level if self.stream is not None else 0)
        self.update()

    @staticmethod
    def _frame_interval(refresh_rate: float) -> int:
        return max(8, int(1000 / min(120, max(60, refresh_rate))))

    def _place_at_bottom(self) -> None:
        screen = QApplication.screenAt(self.cursor().pos()) or QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            width = min(820, area.width() - 24)
            if self.width() != width:
                self.setFixedWidth(width)
                self.particles.resize(self.width(), self.height())
                self._edge_mask = None
            self.move(area.x() + (area.width() - self.width()) // 2, area.y() + area.height() - self.height())

    def reveal(self) -> None:
        self._place_at_bottom()
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen:
            self.particle_timer.setInterval(self._frame_interval(screen.refreshRate()))
        self.show()
        self._update_input_mask()
        self.raise_()
        self.activateWindow()
        self._last_particle_tick = None
        self.particle_timer.start()
        if QApplication.platformName() != "offscreen":
            self.setWindowOpacity(0.0)
            self._animation = QPropertyAnimation(self, b"windowOpacity", self)
            self._animation.setDuration(180)
            self._animation.setStartValue(0.0)
            self._animation.setEndValue(1.0)
            self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._animation.start()

    def hide_overlay(self) -> None:
        if self.stream is not None:
            self._stop_recording()
        if self._animation is not None:
            self._animation.stop()
        self.setWindowOpacity(1.0)
        self.particle_timer.stop()
        self._last_particle_tick = None
        self._background_progress = 0.0
        self._background_revealing = False
        self._background_retracting = False
        self.hide()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide_overlay()
        else:
            super().keyPressEvent(event)

    def register_hotkey(self) -> bool:
        if sys.platform != "win32":
            return False
        self.hotkey_registered = bool(ctypes.windll.user32.RegisterHotKey(int(self.winId()), 0x564F, 0x0002 | 0x0004, 0x20))
        return self.hotkey_registered

    def nativeEvent(self, event_type, message):
        if sys.platform == "win32" and event_type == b"windows_generic_MSG":
            from ctypes import wintypes

            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                if self.isVisible():
                    self.toggle_recording()
                else:
                    self.reveal()
                    if self.model_ready:
                        self._start_recording()
                return True, 0
        return super().nativeEvent(event_type, message)

    def _load_devices(self) -> None:
        try:
            default_id = sd.default.device[0]
            for index, device in enumerate(sd.query_devices()):
                if device["max_input_channels"] > 0:
                    host = sd.query_hostapis(device["hostapi"])["name"]
                    self.device_box.addItem(f"{device['name']} · {host}", index)
                    if index == default_id:
                        self.device_box.setCurrentIndex(self.device_box.count() - 1)
        except Exception as exc:
            self.status_label.setText(f"Microphone unavailable: {exc}")

    def _start_worker(self) -> None:
        if not (self.model_dir / "model.int8.onnx").is_file():
            self.status_label.setText("Speech model missing. Run: python scripts/download_model.py")
            return
        try:
            self.executor = ProcessPoolExecutor(
                max_workers=1,
                initializer=initialize_worker,
                initargs=(str(self.model_dir),),
            )
            self.ready_future = self.executor.submit(worker_ready)
        except Exception as exc:
            self.status_label.setText(f"Could not start recognition: {exc}")

    def toggle_recording(self) -> None:
        if self.stream is not None:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        if not self.model_ready or self.device_box.currentData() is None:
            return
        if self.result_future is not None or (self.scheduler and self.scheduler.state == "finalizing"):
            return
        if not self.isVisible():
            self.reveal()
        device_id = self.device_box.currentData()
        try:
            device = sd.query_devices(device_id, "input")
            sample_rate = round(device["default_samplerate"])
            self.audio.start(sample_rate)
            self.scheduler = RecognitionScheduler(sample_rate)
            self.scheduler.start()
            self.capture_warning = ""
            self.limit_reached = False
            self.transcript.clear()
            self.transcript.setReadOnly(True)
            self.copy_button.setEnabled(False)
            self.device_box.setEnabled(False)
            self.capsule.reset()
            self.stream = sd.InputStream(
                device=device_id,
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                callback=self._on_audio,
            )
            self.stream.start()
            self._set_mode("recording")
            self.record_button.setText("Stop recording")
            self.status_label.setText("Listening · live transcription")
        except Exception as exc:
            if self.stream is not None:
                self.stream.close()
                self.stream = None
            self.audio.stop()
            self.scheduler = None
            self.device_box.setEnabled(True)
            self.status_label.setText(f"Could not start microphone: {exc}")
            self._set_mode("idle")

    def _on_audio(self, frames, _count, _time, status) -> None:
        if status:
            self.capture_warning = str(status)
        try:
            self.limit_reached = self.audio.append(frames) or self.limit_reached
        except RuntimeError:
            pass

    def _stop_recording(self) -> None:
        if self.stream is None:
            return
        self._background_revealing = False
        self._background_retracting = True
        self._background_progress = max(0.0, self._background_progress - 0.06)
        self.capsule.set_recording(False)
        self.capsule.reset()
        self.record_button.icon_name = "mic"
        self.record_button.update()
        self.status_label.setText("Finalizing transcript…")
        if self.isVisible():
            self.repaint()
            self.capsule.repaint()
            self.record_button.repaint()
        self.stream.stop()
        self.stream.close()
        self.stream = None
        self.audio.stop()
        self.device_box.setEnabled(True)
        self.record_button.setText("Transcribing…")
        self.record_button.setEnabled(False)
        self.capsule.setEnabled(False)
        if self.scheduler:
            self.scheduler.stop()
        if self.audio.duration_seconds < 0.25:
            self.scheduler = None
            self.record_button.setText("Start recording")
            self.record_button.setEnabled(True)
            self.capsule.setEnabled(True)
            self.status_label.setText("Recording was too short. Try again.")
            self._set_mode("idle")

    def _poll(self) -> None:
        if self.ready_future is not None and self.ready_future.done():
            try:
                self.model_ready = self.ready_future.result()
                self.status_label.setText("Press Ctrl+Shift+Space to speak")
                self.record_button.setEnabled(self.device_box.count() > 0)
                self.capsule.setEnabled(self.device_box.count() > 0)
            except Exception as exc:
                self.status_label.setText(f"Could not load speech model: {exc}")
            self.ready_future = None

        if self.result_future is not None and self.result_future.done():
            future, job = self.result_future, self.result_job
            self.result_future = None
            self.result_job = None
            try:
                text = future.result()
                if self.scheduler and job:
                    result = self.scheduler.complete(job, text)
                    if result:
                        self.apply_transcript(*result)
            except Exception as exc:
                self.status_label.setText(f"Transcription failed: {exc}")
                self.record_button.setText("Record again")
                self.record_button.setEnabled(self.model_ready)
                self.capsule.setEnabled(self.model_ready)
                self.scheduler = None
                self._set_mode("result")

        if self.stream is not None:
            seconds = int(self.audio.duration_seconds)
            self.time_label.setText(f"{seconds // 60:02d}:{seconds % 60:02d} / 00:30")
            if self.capture_warning:
                self.status_label.setText(f"Recording notice: {self.capture_warning}")
            if self.limit_reached:
                self._stop_recording()

        if self.scheduler and self.executor and self.result_future is None:
            job = self.scheduler.next_job(self.audio.sample_count)
            if job:
                self.result_job = job
                self.result_future = self.executor.submit(
                    transcribe_in_worker,
                    self.audio.snapshot(),
                    self.audio.sample_rate,
                )

    def apply_transcript(self, kind: str, text: str) -> None:
        if kind not in {"partial", "final"}:
            raise ValueError(f"Unknown transcript kind: {kind}")
        self.transcript.setPlainText(text)
        self.transcript.setReadOnly(kind != "final")
        if kind == "final":
            self._set_mode("result")
            self.status_label.setText("Transcript ready · edit or copy" if text else "No speech detected. Try again.")
            self.record_button.setText("Record again")
            self.record_button.setEnabled(self.model_ready)
            self.capsule.setEnabled(self.model_ready)
            self.copy_button.setEnabled(bool(text))
        else:
            self._set_mode("recording")
            self.status_label.setText("Listening · draft may change")

    def _copy_text(self) -> None:
        QApplication.clipboard().setText(self.transcript.toPlainText())
        self.status_label.setText("Copied to clipboard")

    def closeEvent(self, event: QCloseEvent) -> None:
        self.timer.stop()
        self.particle_timer.stop()
        if self.hotkey_registered:
            ctypes.windll.user32.UnregisterHotKey(int(self.winId()), HOTKEY_ID)
            self.hotkey_registered = False
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        if self.executor is not None:
            self.executor.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)
