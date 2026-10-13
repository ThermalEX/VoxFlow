"""Polish final transcripts with the rewrite model: one edit animation, undo with hover preview, suggestions."""

import html
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QObject, QTimer, QVariantAnimation
from PySide6.QtWidgets import QHBoxLayout, QWidget

from .edit_diff import frame_html, same_text
from .i18n import describe_error, tr
from .local_server import LocalRewriteServer
from .overlay_widgets import PillButton
from .rewriter import LOCAL_ENDPOINT, RewriteClient, RewriteConfig, RewriteError

REPO_ROOT = Path(__file__).resolve().parents[1]
EDIT_ANIMATION_MS = 800
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


def _repo_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else REPO_ROOT / path


def default_server_factory(config: RewriteConfig) -> LocalRewriteServer:
    server_path, model_path = _repo_path(config.server_path), _repo_path(config.model_path)
    return LocalRewriteServer(LocalRewriteServer.llama_command(server_path, model_path), HEALTH_URL,
                              REPO_ROOT / "runtime" / "llama-server.log",
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

        self.animation = QVariantAnimation(self)
        self.animation.setDuration(EDIT_ANIMATION_MS)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.animation.valueChanged.connect(self._render_frame)
        self.animation.finished.connect(self._finish_animation)
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
        self.reload()

    # Configuration ---------------------------------------------------------------------------

    @property
    def active(self) -> bool:
        return self.config.enabled and self.client is not None

    def reload(self) -> None:
        config = RewriteConfig.from_settings(self.window.settings)
        if config == self.config and (self.client is not None or not config.enabled):
            return
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
        self.animation.stop()
        self.executor.shutdown(wait=False, cancel_futures=True)
        if self.server is not None:
            self.server.stop()
            self.server = None

    # Session flow ----------------------------------------------------------------------------

    def begin(self, text: str, session: int) -> None:
        self.reset()
        self.session = session
        self.original_text = self.edited_text = text
        self._sync_bar()
        if not self.active:
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
        if self.animation.state() == QVariantAnimation.State.Running:
            self.animation.stop()
            if self.window.mode == "result":
                self._set_plain(self.original_text)
                self.transcript.setReadOnly(False)
        if self._hover_text is not None:
            self._end_preview(self._hover_text)
        self.session = None
        self._waiting = False
        self._user_edited = False
        self._hover_text = None
        self.showing_original = False
        self._suggestions = []
        self.undo_button.setText(tr("button.undo_edits"))
        self._sync_bar()

    def _submit(self, kind: str, text: str) -> None:
        call = self.client.clean if kind == "clean" else self.client.suggest
        self.future = self.executor.submit(call, text)
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
            return
        if kind == "clean":
            self._apply_clean(result)
        else:
            self._show_suggestions(result)

    def _apply_clean(self, cleaned: str) -> None:
        if self.transcript.toPlainText() != self.original_text:
            return
        if "".join(cleaned.split()) == "".join(self.original_text.split()):
            self._set_status("status.no_edits")
            self._suggest_timer.start(self.suggest_delay_ms)
            return
        self.edited_text = cleaned
        self.transcript.setReadOnly(True)
        self.animation.start()

    def _render_frame(self, value) -> None:
        if self.animation.state() != QVariantAnimation.State.Running:
            return
        self._set_html(frame_html(self.original_text, self.edited_text, float(value), TEXT_RGB, REMOVED_RGB, ADDED_RGB))

    def _finish_animation(self) -> None:
        self._set_plain(self.edited_text)
        self.transcript.setReadOnly(False)
        self._sync_bar()
        self.window._expand_for_result()
        self._set_status("status.polished")
        self._suggest_timer.start(self.suggest_delay_ms)

    def _request_suggestions(self) -> None:
        if self.active and self._still_current():
            self._submit("suggest", self.edited_text)

    def _show_suggestions(self, suggestions: list[dict]) -> None:
        self._suggestions = [item for item in suggestions if not same_text(item["text"], self.edited_text)]
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
        self._set_plain(text)
        self.transcript.setReadOnly(False)

    def _toggle_undo(self) -> None:
        target = self._other_version()
        self.showing_original = not self.showing_original
        self.undo_button.setText(tr("button.restore_edits" if self.showing_original else "button.undo_edits"))
        self._end_preview(target)
        self.window._expand_for_result()

    def _apply_suggestion(self, index: int) -> None:
        if index >= len(self._suggestions):
            return
        self.edited_text = self._suggestions[index]["text"]
        self.showing_original = False
        self.undo_button.setText(tr("button.undo_edits"))
        self._end_preview(self.edited_text)
        self._sync_bar()
        self._set_status("status.suggestion_applied")
        self.window._expand_for_result()

    def current_text(self) -> str:
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

    # Helpers ----------------------------------------------------------------------------------

    def _sync_bar(self) -> None:
        show_undo = (self.session is not None and not self._user_edited
                     and self.animation.state() != QVariantAnimation.State.Running
                     and not same_text(self.edited_text, self.original_text))
        self.undo_button.setVisible(show_undo)
        for index, button in enumerate(self.suggestion_buttons):
            if index < len(self._suggestions) and self.session is not None and not self._user_edited:
                button.setText(self._suggestions[index]["label"])
                button.setToolTip(self._suggestions[index]["text"])
                button.show()
            else:
                button.hide()
        show_continue = (self.session is not None and self.window.mode == "result"
                         and self.animation.state() != QVariantAnimation.State.Running)
        self.continue_button.setVisible(show_continue)
        visible = show_continue or show_undo or any(not button.isHidden() for button in self.suggestion_buttons)
        if visible != (not self.bar.isHidden()):
            self.bar.setVisible(visible)
            if self.window.mode == "result":
                self.window._expand_for_result()

    def bar_height(self) -> int:
        return 0 if self.bar.isHidden() else self.bar.sizeHint().height() + 10

    def _set_status(self, key: str, tooltip: str = "", **values) -> None:
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
