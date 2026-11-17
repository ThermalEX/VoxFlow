"""Polish final transcripts with the rewrite model: one edit animation, undo with hover preview, suggestions.

In review mode the edits are not applied at once: each one stays marked in place, and clicking it switches
between the rewrite and what was said. Typing ends the review and edits the text as it then stands.

With memory on, a "remember …" request loses its request words and pulses once in the theme color, and names
the user taught VoxFlow are written the remembered way.
"""

import html
import math
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QEvent, QObject, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QTextCursor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QHBoxLayout, QWidget

from .color_themes import saved_color_theme
from .edit_diff import frame_html, highlight_html, resolve_review, review_html, review_hunks, same_text
from .i18n import describe_error, language, tr
from .local_server import LocalRewriteServer
from .overlay_widgets import PillButton
from .paths import DATA_ROOT
from .rewriter import LOCAL_ENDPOINT, RewriteClient, RewriteConfig, RewriteError
from .suggestion_labels import localize_label, translates_into_chinese

EDIT_ANIMATION_MS = 800
REMEMBER_ANIMATION_MS = 1300
GLOW_BLUR = 22  # radius of the halo around remembered text at its brightest
GLOW_LIGHTER = 175  # the halo is a light tint of the theme color, so it shows on the overlay's own glow
# Suggestions are requested only after the polished text has been on screen a moment, so a quick
# confirm never leaves a slow suggestion request queued ahead of the next sentence.
SUGGEST_DELAY_MS = 1200
MAX_SUGGESTIONS = 3
TEXT_RGB = (243, 247, 255)
REMOVED_RGB = (150, 162, 180)
ADDED_RGB = (150, 200, 255)
PREVIEW_COLOR = "#9AA6B6"
SERVER_FIELDS = ("provider", "server_path", "model_path")
HEALTH_URL = LOCAL_ENDPOINT.removesuffix("/v1") + "/health"


def _data_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else DATA_ROOT / path


def default_server_factory(config: RewriteConfig) -> LocalRewriteServer:
    server_path, model_path = _data_path(config.server_path), _data_path(config.model_path)
    return LocalRewriteServer(LocalRewriteServer.llama_command(server_path, model_path), HEALTH_URL,
                              DATA_ROOT / "runtime" / "llama-server.log",
                              required=[("missing_server", server_path), ("missing_model", model_path)])


class SmartEditor(QObject):
    def __init__(self, window, client=None, server_factory=None) -> None:
        super().__init__(window)
        self.window = window
        self.transcript = window.transcript
        self._fixed_client = client
        # Tests inject a client without a server; the app launches llama-server for the local provider.
        self._server_factory = server_factory if server_factory is not None else (
            None if client is not None else default_server_factory)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rewrite")
        self.config = RewriteConfig()
        self.client = None
        self.server = None
        self.future: Future | None = None
        self._future_kind = ""
        self._future_session = None
        self.session = None
        self.original_text = ""
        self.edited_text = ""
        self.showing_original = False
        self._waiting = False
        self._user_edited = False
        self._hover_text: str | None = None
        self._programmatic = False
        self._suggestions: list[dict] = []
        self.remember_request = False  # this dictation asked VoxFlow to remember it
        self.remember_opening = ""  # a greeting said before the request, left out of the remembered entry
        self.remembered_id: int | None = None  # the entry saved for this request once its glow ended
        self._memory_off_hint = False  # asked to remember while memory is off: say where to turn it on
        self._pending_clean: str | None = None  # a rewrite that arrived while the remember pulse was playing
        self.review_hunks: list[tuple] | None = None  # set while the edits wait for the user's review
        self.review_accepted: list[bool] = []

        self.animation = QVariantAnimation(self)
        self.animation.setDuration(EDIT_ANIMATION_MS)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.valueChanged.connect(self._render_frame)
        self.animation.finished.connect(self._finish_animation)
        self.highlight = QVariantAnimation(self)
        self.highlight.setDuration(REMEMBER_ANIMATION_MS)
        self.highlight.setStartValue(0.0)
        self.highlight.setEndValue(1.0)
        self.highlight.valueChanged.connect(self._render_highlight)
        self.highlight.finished.connect(self._finish_highlight)
        self._highlight_rgb = (255, 255, 255)
        self._glow_color = QColor(255, 255, 255)
        self._status_after_glow: tuple | None = None  # a status that arrived during the remember pulse
        self.suggest_delay_ms = SUGGEST_DELAY_MS
        self._suggest_timer = QTimer(self)
        self._suggest_timer.setSingleShot(True)
        self._suggest_timer.timeout.connect(self._request_suggestions)

        self.bar = QWidget()
        bar_layout = QHBoxLayout(self.bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setSpacing(8)
        bar_layout.addStretch(1)
        self.continue_button = PillButton(tr("button.continue"))
        self.continue_button.clicked.connect(lambda: self.window.continue_recording())
        bar_layout.addWidget(self.continue_button)
        self.undo_button = PillButton(tr("button.undo_edits"))
        self.undo_button.hovered.connect(self._preview_other_version)
        self.undo_button.clicked.connect(self._toggle_undo)
        bar_layout.addWidget(self.undo_button)
        self.suggestion_buttons = []
        for index in range(MAX_SUGGESTIONS):
            button = PillButton()
            button.clicked.connect(lambda _checked=False, i=index: self._apply_suggestion(i))
            bar_layout.addWidget(button)
            self.suggestion_buttons.append(button)
        bar_layout.addStretch(1)
        self.bar.hide()
        self.transcript.textChanged.connect(self._on_text_changed)
        self.transcript.installEventFilter(self)
        self.transcript.viewport().installEventFilter(self)
        self.reload()

    # Configuration ---------------------------------------------------------------------------

    @property
    def active(self) -> bool:
        return self.config.enabled and self.client is not None

    def reload(self, force: bool = False) -> None:
        """Apply the saved settings; `force` restarts the local server even if they did not change
        (e.g. llama.cpp or the model file was just installed)."""
        config = RewriteConfig.from_settings(self.window.settings)
        if not force and config == self.config and (self.client is not None or not config.enabled):
            return
        if force:
            self.release_server()
        previous, self.config = self.config, config
        server_changed = any(getattr(previous, name) != getattr(config, name) for name in SERVER_FIELDS)
        if self.server is not None and (not config.enabled or server_changed):
            self.server.stop()
            self.server = None
        if not config.enabled:
            had_session = self.session is not None
            self.reset()
            self.client = None
            if had_session and self.window.mode == "result":
                self._set_status("status.ready")
            return
        self.client = self._fixed_client or RewriteClient(config.base_url, config.model_name, config.api_key)
        if config.provider == "local" and self.server is None and self._server_factory is not None:
            self.server = self._server_factory(config)
            self.server.start()

    def release_server(self) -> None:
        """Stop llama-server so its program or model files can be replaced or deleted."""
        if self.server is not None:
            self.server.stop()
            self.server = None

    def ready(self) -> bool:
        return self.active and (self.server is None or self.server.ready())

    def test_connection(self, config: RewriteConfig) -> str:
        if not config.enabled:
            raise RewriteError("smart editing is off", kind="disabled")
        if config.provider == "local" and self.server is not None and not self.server.ready():
            problem = getattr(self.server, "problem", None)
            if problem and problem[0] in ("missing_server", "missing_model"):
                raise RewriteError(self.server.failed or "", kind=problem[0], path=problem[1])
            if self.server.failed:
                raise RewriteError(self.server.failed, kind="local_failed")
            raise RewriteError("the local model is still starting", kind="starting")
        return RewriteClient(config.base_url, config.model_name, config.api_key).check()

    def list_models(self, config: RewriteConfig) -> list[str]:
        return RewriteClient(config.base_url, config.model_name, config.api_key).list_models()

    def model_status(self) -> tuple[str, dict]:
        """The local model's state for the settings page, as an i18n key and its values."""
        if not self.config.enabled:
            return "model.off", {}
        if self.config.provider != "local":
            return "model.custom", {}
        if not _data_path(self.config.model_path).is_file():
            return "model.not_installed", {}
        server_path = _data_path(self.config.server_path)
        if not server_path.is_file():
            return "model.missing_server", {"path": str(server_path)}
        if self.server is None:
            return "model.ready", {}
        problem = getattr(self.server, "problem", None)
        if problem and problem[0] in ("missing_server", "missing_model"):
            return f"model.{problem[0]}", {"path": problem[1]}
        if self.server.failed:
            return "model.failed", {"detail": self.server.failed}
        return ("model.ready", {}) if self.server.ready() else ("model.starting", {})

    def retranslate(self) -> None:
        self.continue_button.setText(tr("button.continue"))
        self.undo_button.setText(tr("button.restore_edits" if self.showing_original else "button.undo_edits"))

    def shutdown(self) -> None:
        self._leave_review()
        self.transcript.removeEventFilter(self)
        self.transcript.viewport().removeEventFilter(self)
        self.animation.stop()
        self.executor.shutdown(wait=False, cancel_futures=True)
        if self.server is not None:
            self.server.stop()
            self.server = None

    # Session flow ----------------------------------------------------------------------------

    def begin(self, text: str, session: int) -> None:
        self.reset()
        self.session = session
        memory = getattr(self.window, "memory", None)
        found = memory.find_command(text) if memory is not None else None
        self.remember_request = found is not None and memory.enabled
        self._memory_off_hint = found is not None and not memory.enabled
        if self.remember_request:
            self.remember_opening = found[0]
            text = found[0] + found[1]
            self._set_plain(text)
        self.original_text = self.edited_text = text
        self._sync_bar()
        if self.remember_request:
            self._start_highlight()
        elif self._memory_off_hint:
            self._set_status("status.ready")
        if not self.active:
            self._apply_local_fixes()
            return
        if self.ready():
            self._submit("clean", text)
        elif self.server is not None and self.server.failed:
            self._set_status("status.local_failed", tooltip=self.server.failed)
        else:
            self._waiting = True
            self._set_status("status.waiting_model")

    def reset(self) -> None:
        if self.future is not None and self.future.cancel():
            self.future = None
        self._suggest_timer.stop()
        if self.highlight.state() == QVariantAnimation.State.Running:
            self.highlight.stop()
            self._end_glow()
            if self.window.mode == "result":
                self._set_plain(self.original_text)
                self.transcript.setReadOnly(False)
        self.remember_request = False
        self.remember_opening = ""
        self.remembered_id = None
        self._memory_off_hint = False
        self._status_after_glow = None
        self._pending_clean = None
        if self.animation.state() == QVariantAnimation.State.Running:
            self.animation.stop()
            if self.window.mode == "result":
                self._set_plain(self.original_text)
                self.transcript.setReadOnly(False)
        if self._hover_text is not None:
            self._end_preview(self._hover_text)
        if self.reviewing:
            self._leave_review()
            if self.window.mode == "result":
                self.transcript.setReadOnly(False)
        self.session = None
        self._waiting = False
        self._user_edited = False
        self._hover_text = None
        self.showing_original = False
        self._suggestions = []
        self.undo_button.setText(tr("button.undo_edits"))
        self._sync_bar()

    def _submit(self, kind: str, text: str, *extra) -> None:
        self.future = self.executor.submit(getattr(self.client, kind), text, *extra)
        self._future_kind = kind
        self._future_session = self.session
        if kind == "clean":
            self._set_status("status.polishing")

    def _still_current(self) -> bool:
        return (self.session is not None and not self._user_edited and self.window.mode == "result")

    def poll(self) -> None:
        settings_window = getattr(self.window, "settings_window", None)
        if settings_window is not None:
            key, values = self.model_status()
            if settings_window._model_status != (key, values):
                settings_window.set_model_status(key, **values)
        if not self.active:
            return
        if self._waiting and self.session is not None:
            if self.server is not None and self.server.failed:
                self._waiting = False
                self._set_status("status.local_failed", tooltip=self.server.failed)
            elif self.ready() and self._still_current():
                self._waiting = False
                self._submit("clean", self.original_text)
        if self.future is None or not self.future.done():
            return
        future, kind, session = self.future, self._future_kind, self._future_session
        self.future = None
        if session != self.session or not self._still_current():
            return
        try:
            result = future.result()
        except Exception as exc:  # any backend failure keeps the original text
            if kind == "clean":
                self._set_status("status.smart_failed", tooltip=str(exc), reason=describe_error(exc))
                self._apply_local_fixes()
            return
        if kind == "clean":
            self._apply_clean(result)
        elif kind == "suggest":
            self._show_suggestions(result)
        else:
            self._show_fill(result)

    def _apply_local_fixes(self) -> None:
        """Without a rewrite, still write remembered names the remembered way."""
        memory = getattr(self.window, "memory", None)
        fixed = memory.correct(self.original_text) if memory is not None else self.original_text
        if fixed != self.original_text:
            self._apply_clean(fixed)

    def _apply_clean(self, cleaned: str) -> None:
        memory = getattr(self.window, "memory", None)
        if memory is not None:
            cleaned = memory.correct(cleaned)
        if self.highlight.state() == QVariantAnimation.State.Running:
            self._pending_clean = cleaned
            return
        if self.transcript.toPlainText() != self.original_text:
            return
        if "".join(cleaned.split()) == "".join(self.original_text.split()):
            self._set_status("status.no_edits")
            self._suggest_timer.start(self.suggest_delay_ms)
            return
        self.edited_text = cleaned
        self.transcript.setReadOnly(True)
        if self.config.review:
            self._start_review()
            return
        self.animation.start()

    def _render_frame(self, value) -> None:
        if self.animation.state() != QVariantAnimation.State.Running:
            return
        self._set_html(frame_html(self.original_text, self.edited_text, float(value), TEXT_RGB, REMOVED_RGB, ADDED_RGB))

    def _finish_animation(self) -> None:
        self._keep_remembered(self.edited_text)
        self._set_plain(self.edited_text)
        self.transcript.setReadOnly(False)
        self._sync_bar()
        self.window._expand_for_result()
        self._set_status("status.polished")
        self._suggest_timer.start(self.suggest_delay_ms)

    # Remember pulse ----------------------------------------------------------------------------

    def _start_highlight(self) -> None:
        """The remembered text tints toward the theme color and a halo of that color swells behind it."""
        theme_color = QColor(saved_color_theme(self.window.settings).accent("dark"))
        accent = theme_color.lighter(135)
        self._highlight_rgb = (accent.red(), accent.green(), accent.blue())
        self._glow_color = theme_color.lighter(GLOW_LIGHTER)
        glow = QGraphicsDropShadowEffect(self.transcript)
        glow.setOffset(0, 0)
        glow.setBlurRadius(0)
        glow.setColor(QColor(0, 0, 0, 0))
        self.transcript.setGraphicsEffect(glow)
        self._set_status("status.will_remember")
        self.transcript.setReadOnly(True)
        self.highlight.start()

    def _render_highlight(self, value) -> None:
        if self.highlight.state() != QVariantAnimation.State.Running:
            return
        progress = float(value)
        self._set_html(highlight_html(self.original_text, progress, TEXT_RGB, self._highlight_rgb))
        glow = self.transcript.graphicsEffect()
        if isinstance(glow, QGraphicsDropShadowEffect):
            strength = math.sin(math.pi * progress)  # swells, then fades
            glow.setBlurRadius(GLOW_BLUR * strength)
            color = QColor(self._glow_color)
            color.setAlpha(round(255 * strength))
            glow.setColor(color)

    def _end_glow(self) -> None:
        # Drop the effect afterwards: a resting halo would blur the text and cost a repaint every frame.
        if isinstance(self.transcript.graphicsEffect(), QGraphicsDropShadowEffect):
            self.transcript.setGraphicsEffect(None)

    def _keep_remembered(self, text: str) -> None:
        """Save the remember request now, or update it to the words now on screen."""
        memory = getattr(self.window, "memory", None)
        if self.remember_request and memory is not None:
            self.remembered_id = memory.remember_now(text, self.remember_opening, self.remembered_id)

    def _finish_highlight(self) -> None:
        self._end_glow()
        # The glow means "remembered": save it now rather than only when the text is confirmed.
        self._keep_remembered(self.original_text)
        self._set_status("status.remembered")
        waiting, self._status_after_glow = self._status_after_glow, None
        if waiting is not None:
            key, tooltip, values = waiting
            self._set_status(key, tooltip, **values)
        self._set_plain(self.original_text)
        self.transcript.setReadOnly(False)
        self._sync_bar()
        pending, self._pending_clean = self._pending_clean, None
        if pending is not None and self._still_current():
            self._apply_clean(pending)

    def _request_suggestions(self) -> None:
        if self.active and self._still_current():
            self._submit("suggest", self.edited_text)

    def _show_suggestions(self, suggestions: list[dict]) -> None:
        shown = language()
        self._suggestions = [{**item, "label": localize_label(item["label"], shown)} for item in suggestions
                             if not same_text(item["text"], self.edited_text)
                             # an English speaker has no use for the Chinese version the model likes to offer
                             and not (shown == "en" and translates_into_chinese(self.edited_text, item["text"]))]
        self._suggestions = self._suggestions[:MAX_SUGGESTIONS]
        self._sync_bar()
        memory = getattr(self.window, "memory", None)
        related = memory.related(self.edited_text) if memory is not None else []
        if related and self.active:
            self._submit("fill", self.edited_text, related)

    def _show_fill(self, filled: str) -> None:
        """Offer the text completed from memory as the first suggestion; the user decides."""
        if not filled.strip() or same_text(filled, self.edited_text):
            return
        fill = {"label": tr("suggestion.memory_fill"), "text": filled.strip()}
        self._suggestions = [fill] + [item for item in self._suggestions if not same_text(item["text"], filled)]
        self._suggestions = self._suggestions[:MAX_SUGGESTIONS]
        self._sync_bar()

    # Undo, preview and suggestions ------------------------------------------------------------

    def _other_version(self) -> str:
        return self.edited_text if self.showing_original else self.original_text

    def _preview_other_version(self, hovering: bool) -> None:
        if hovering and self._hover_text is None and self.undo_button.isVisible():
            self._hover_text = self.transcript.toPlainText()
            self.transcript.setReadOnly(True)
            self._set_html(f'<div style="white-space: pre-wrap; color: {PREVIEW_COLOR};">'
                           f"{html.escape(self._other_version())}</div>")
        elif not hovering and self._hover_text is not None:
            self._end_preview(self._hover_text)

    def _end_preview(self, text: str) -> None:
        self._hover_text = None
        if self.reviewing:
            self._render_review()
            return
        self._set_plain(text)
        self.transcript.setReadOnly(False)

    def _toggle_undo(self) -> None:
        if self.reviewing:
            # Undo turns back every edit still kept; Restore keeps them all again.
            keep = not any(self.review_accepted)
            self.review_accepted = [keep] * len(self.review_accepted)
            self._review_changed()
            return
        target = self._other_version()
        self.showing_original = not self.showing_original
        self.undo_button.setText(tr("button.restore_edits" if self.showing_original else "button.undo_edits"))
        self._end_preview(target)
        self.window._expand_for_result()

    def _apply_suggestion(self, index: int) -> None:
        if index >= len(self._suggestions):
            return
        self._leave_review()
        self.edited_text = self._suggestions[index]["text"]
        self.showing_original = False
        self.undo_button.setText(tr("button.undo_edits"))
        self._end_preview(self.edited_text)
        self._sync_bar()
        self._set_status("status.suggestion_applied")
        self.window._expand_for_result()

    def current_text(self) -> str:
        if self.reviewing:
            return self.reviewed_text()
        return self._hover_text if self._hover_text is not None else self.transcript.toPlainText()

    def _on_text_changed(self) -> None:
        if self._programmatic or self.session is None:
            return
        self._user_edited = True
        if self._waiting or (self.future is not None and self._future_kind == "clean"):
            self._set_status("status.ready")
        self._waiting = False
        self._suggest_timer.stop()
        if self.bar.isVisible():
            self._suggestions = []
            self.edited_text = self.original_text
            self._sync_bar()

    # Review mode ------------------------------------------------------------------------------

    @property
    def reviewing(self) -> bool:
        return self.review_hunks is not None

    def reviewed_text(self) -> str:
        return resolve_review(self.review_hunks, self.review_accepted)

    def _start_review(self) -> None:
        """Mark each edit in place, all kept to begin with; the user clicks the ones to turn back."""
        self.review_hunks = review_hunks(self.original_text, self.edited_text)
        self.review_accepted = [True] * sum(1 for item in self.review_hunks if item[0] == "change")
        self.transcript.viewport().setMouseTracking(True)
        self._render_review()
        self._keep_remembered(self.reviewed_text())
        self._sync_bar()
        self.window._expand_for_result()
        count = len(self.review_accepted)
        self._set_status("status.review_one" if count == 1 else "status.review", count=count)
        self._suggest_timer.start(self.suggest_delay_ms)

    def _render_review(self) -> None:
        self._set_html(review_html(self.review_hunks, self.review_accepted, TEXT_RGB, REMOVED_RGB, ADDED_RGB))
        self.transcript.setReadOnly(True)

    def toggle_change(self, index: int) -> None:
        if not self.reviewing or not 0 <= index < len(self.review_accepted):
            return
        self.review_accepted[index] = not self.review_accepted[index]
        self._review_changed()

    def _review_changed(self) -> None:
        self.showing_original = not any(self.review_accepted)
        self.undo_button.setText(tr("button.restore_edits" if self.showing_original else "button.undo_edits"))
        self._render_review()
        self._keep_remembered(self.reviewed_text())
        self.window._expand_for_result()
        self._set_status("status.review_progress", kept=sum(self.review_accepted),
                         count=len(self.review_accepted))

    def finish_review(self) -> None:
        """Turn the marked-up review into plain text the user can edit, keeping the choices made."""
        if not self.reviewing:
            return
        text = self.reviewed_text()
        any_kept = any(self.review_accepted)
        if any_kept:
            self.edited_text = text  # Undo edits still returns to what was said
        self._leave_review()
        self.showing_original = not any_kept
        self.undo_button.setText(tr("button.restore_edits" if self.showing_original else "button.undo_edits"))
        self._set_plain(text)
        self.transcript.setReadOnly(False)
        self._sync_bar()

    def _leave_review(self) -> None:
        if self.review_hunks is None:
            return
        self.review_hunks = None
        self.review_accepted = []
        self.transcript.viewport().setMouseTracking(False)
        self.transcript.viewport().unsetCursor()

    def _change_at(self, pos) -> int | None:
        anchor = self.transcript.anchorAt(pos)
        if anchor.startswith("change:"):
            return int(anchor.removeprefix("change:"))
        return None

    def eventFilter(self, watched, event) -> bool:
        if not self.reviewing or self._hover_text is not None:
            return False
        try:
            return self._review_event(watched, event)
        except RuntimeError:  # the overlay is being torn down
            return False

    def _review_event(self, watched, event) -> bool:
        kind = event.type()
        if watched is self.transcript.viewport():
            if kind == QEvent.Type.MouseMove:
                over = self._change_at(event.position().toPoint()) is not None
                watched.setCursor(Qt.CursorShape.PointingHandCursor if over else Qt.CursorShape.IBeamCursor)
            elif kind == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                index = self._change_at(event.position().toPoint())
                if index is not None:
                    self.toggle_change(index)
                    return True
            elif kind == QEvent.Type.MouseButtonDblClick:
                if self._change_at(event.position().toPoint()) is None:
                    self.finish_review()
                    self.transcript.moveCursor(QTextCursor.MoveOperation.End)
                    return True
        elif watched is self.transcript and kind == QEvent.Type.KeyPress:
            # Enter still confirms; a key that edits text ends the review and then reaches the editor.
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Escape):
                return False
            if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
                return False
            if event.text() or event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
                self.finish_review()
                self.transcript.moveCursor(QTextCursor.MoveOperation.End)
        return False

    # Helpers ----------------------------------------------------------------------------------

    def _sync_bar(self) -> None:
        animating = QVariantAnimation.State.Running in (self.animation.state(), self.highlight.state())
        show_undo = (self.session is not None and not self._user_edited and not animating
                     and not same_text(self.edited_text, self.original_text))
        self.undo_button.setVisible(show_undo)
        for index, button in enumerate(self.suggestion_buttons):
            if index < len(self._suggestions) and self.session is not None and not self._user_edited:
                button.setText(self._suggestions[index]["label"])
                button.setToolTip(self._suggestions[index]["text"])
                button.show()
            else:
                button.hide()
        show_continue = self.session is not None and self.window.mode == "result" and not animating
        self.continue_button.setVisible(show_continue)
        visible = show_continue or show_undo or any(not button.isHidden() for button in self.suggestion_buttons)
        if visible != (not self.bar.isHidden()):
            self.bar.setVisible(visible)
            if self.window.mode == "result":
                self.window._expand_for_result()

    def bar_height(self) -> int:
        return 0 if self.bar.isHidden() else self.bar.sizeHint().height() + 10

    def _set_status(self, key: str, tooltip: str = "", **values) -> None:
        if key in ("status.polished", "status.no_edits", "status.ready"):
            if self._memory_off_hint:
                key, values = "status.memory_off", {}
            elif self.remembered_id is not None:
                key, values = "status.remembered", {}
        if key != "status.will_remember" and self.highlight.state() == QVariantAnimation.State.Running:
            # Keep "will remember" on screen while the text glows; show what came meanwhile afterwards.
            self._status_after_glow = (key, tooltip, values)
            return
        self.window.show_status(key, tooltip, **values)

    def _set_plain(self, text: str) -> None:
        self._programmatic = True
        try:
            self.transcript.setPlainText(text)
            self.window.set_transcript_alignment(self.window.transcript_alignment, persist=False)
        finally:
            self._programmatic = False

    def _set_html(self, markup: str) -> None:
        self._programmatic = True
        try:
            self.transcript.setHtml(markup)
            self.window.set_transcript_alignment(self.window.transcript_alignment, persist=False)
        finally:
            self._programmatic = False
