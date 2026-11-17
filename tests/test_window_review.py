from PySide6.QtCore import QEvent, QPointF, QSettings, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QTextCursor
from PySide6.QtWidgets import QApplication

from test_window_rewrite import FakeClient, RecordingOutput, settle
from voxflow.edit_diff import resolve_review, review_html, review_hunks
from voxflow.rewriter import RewriteConfig
from voxflow.window import VoxFlowWindow

SAID = "嗯我们周三，不对，周四下午三点开会，然后 teh report 发给张三。"
REWRITE = "我们周四下午三点开会，然后 the report 发给张三。"


# Splitting a rewrite into decisions -------------------------------------------------------------

def test_hunks_resolve_to_either_version():
    hunks = review_hunks(SAID, REWRITE)
    changes = [item for item in hunks if item[0] == "change"]
    assert len(changes) >= 2
    assert resolve_review(hunks, [True] * len(changes)) == REWRITE
    assert resolve_review(hunks, [False] * len(changes)) == SAID


def test_each_change_is_decided_on_its_own():
    hunks = review_hunks("teh cat sat on teh mat", "the cat sat on the mat")
    assert [item for item in hunks if item[0] == "change"] == [("change", "teh", "the"), ("change", "teh", "the")]
    assert resolve_review(hunks, [True, False]) == "the cat sat on teh mat"


def test_reworded_phrase_is_one_decision_not_scattered_letters():
    hunks = review_hunks("我明天请个假啊", "我明日想请假啊")
    assert len([item for item in hunks if item[0] == "change"]) == 1


def test_heavy_rewrite_is_a_single_change():
    hunks = review_hunks("hello there", "完全不同的一句话")
    assert hunks == [("change", "hello there", "完全不同的一句话")]


def test_review_markup_links_every_change():
    hunks = review_hunks("teh cat", "the cat")
    markup = review_html(hunks, [True], (1, 1, 1), (2, 2, 2), (3, 3, 3))
    assert 'href="change:0"' in markup and "line-through" in markup


# The overlay in review mode ---------------------------------------------------------------------

def make_review_window(tmp_path, client):
    app = QApplication.instance() or QApplication([])
    settings = QSettings(str(tmp_path / "voxflow.ini"), QSettings.Format.IniFormat)
    RewriteConfig(enabled=True, provider="custom", endpoint="http://example.test/v1", model="m",
                  review=True).save(settings)
    output = RecordingOutput()
    window = VoxFlowWindow(model_dir=tmp_path, start_worker=False, settings=settings, text_output=output,
                           rewrite_client=client)
    window.model_ready = True
    window.reveal()
    window._background_progress = 1.0
    return app, window, output


def start_review(app, window, said=SAID):
    window.apply_transcript("final", said)
    settle(app, window, lambda: window.smart.reviewing)


def test_review_marks_edits_instead_of_animating(tmp_path):
    app, window, output = make_review_window(tmp_path, FakeClient(clean=REWRITE))
    start_review(app, window)

    smart = window.smart
    assert smart.animation.state() != smart.animation.State.Running
    assert window.transcript.isReadOnly()
    assert "line-through" in window.transcript.toHtml()
    assert window._status[0] == "status.review"
    assert smart.current_text() == REWRITE  # every edit is kept until the user turns one back
    assert smart.undo_button.isVisible()
    window.close()


def test_rejected_change_keeps_the_spoken_words_when_confirmed(tmp_path):
    app, window, output = make_review_window(tmp_path, FakeClient(clean="the cat sat on the mat"))
    start_review(app, window, said="teh cat sat on teh mat")

    window.smart.toggle_change(1)
    assert window._status[0] == "status.review_progress"
    window._confirm_text()
    assert output.calls == ["the cat sat on teh mat"]
    window.close()


def test_clicking_a_change_switches_it(tmp_path):
    app, window, _output = make_review_window(tmp_path, FakeClient(clean="the cat"))
    start_review(app, window, said="teh cat")
    viewport = window.transcript.viewport()
    cursor = QTextCursor(window.transcript.document())
    cursor.setPosition(window.transcript.document().find("the").selectionStart() + 1)
    point = QPointF(window.transcript.cursorRect(cursor).center())
    for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
        event = QMouseEvent(kind, point, viewport.mapToGlobal(point), Qt.MouseButton.LeftButton,
                            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(viewport, event)
    assert window.smart.review_accepted == [False]
    assert window.smart.current_text() == "teh cat"
    window.close()


def test_undo_turns_back_all_edits_and_restore_keeps_them(tmp_path):
    app, window, output = make_review_window(tmp_path, FakeClient(clean=REWRITE))
    start_review(app, window)
    smart = window.smart

    smart.undo_button.click()
    assert smart.current_text() == SAID
    assert smart.undo_button.text() == "Restore edits" or smart.undo_button.text() == "恢复修改"
    smart.undo_button.click()
    assert smart.current_text() == REWRITE
    window.close()


def test_hover_preview_returns_to_the_review(tmp_path):
    app, window, _output = make_review_window(tmp_path, FakeClient(clean=REWRITE))
    start_review(app, window)
    smart = window.smart

    smart.undo_button.hovered.emit(True)
    assert window.transcript.toPlainText() == SAID
    smart.undo_button.hovered.emit(False)
    assert smart.reviewing and "line-through" in window.transcript.toHtml()
    window.close()


def test_typing_ends_the_review_with_the_choices_made(tmp_path):
    app, window, output = make_review_window(tmp_path, FakeClient(clean="the cat sat on the mat"))
    start_review(app, window, said="teh cat sat on teh mat")
    window.smart.toggle_change(0)

    QApplication.sendEvent(window.transcript, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Period,
                                                        Qt.KeyboardModifier.NoModifier, "."))
    assert not window.smart.reviewing
    assert not window.transcript.isReadOnly()
    assert window.transcript.toPlainText() == "teh cat sat on the mat."
    window._confirm_text()
    assert output.calls == ["teh cat sat on the mat."]
    window.close()


def test_enter_confirms_during_review(tmp_path):
    app, window, output = make_review_window(tmp_path, FakeClient(clean=REWRITE))
    start_review(app, window)

    QApplication.sendEvent(window.transcript, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return,
                                                        Qt.KeyboardModifier.NoModifier))
    assert output.calls == [REWRITE]
    window.close()


def test_suggestion_replaces_the_review(tmp_path):
    client = FakeClient(clean=REWRITE, suggestions=[{"label": "English", "text": "Meeting Thursday 3pm."}])
    app, window, output = make_review_window(tmp_path, client)
    window.smart.suggest_delay_ms = 0
    start_review(app, window)
    settle(app, window, lambda: window.smart.suggestion_buttons[0].isVisible())

    window.smart.suggestion_buttons[0].click()
    assert not window.smart.reviewing
    assert window.transcript.toPlainText() == "Meeting Thursday 3pm."
    window.close()


def test_new_recording_clears_the_review(tmp_path):
    app, window, _output = make_review_window(tmp_path, FakeClient(clean=REWRITE))
    start_review(app, window)
    window.smart.reset()
    assert not window.smart.reviewing
    window.close()


def test_review_is_off_by_default(tmp_path):
    settings = QSettings(str(tmp_path / "voxflow.ini"), QSettings.Format.IniFormat)
    assert RewriteConfig.from_settings(settings).review is False


def test_settings_switch_turns_review_on(tmp_path):
    app, window, _output = make_review_window(tmp_path, FakeClient(clean=REWRITE))
    page = window.settings_window
    page.rewrite_review.setChecked(False)
    assert RewriteConfig.from_settings(window.settings).review is False
    assert window.smart.config.review is False
    page.rewrite_review.setChecked(True)
    assert window.smart.config.review is True
    window.close()
