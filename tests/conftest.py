"""Shared test fixtures that avoid changing the user's desktop state."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["VOXFLOW_LANG"] = "en"  # tests assert English UI text regardless of the machine locale

import pytest
from PySide6.QtCore import QMimeData
from PySide6.QtWidgets import QApplication


@pytest.fixture
def preserve_clipboard():
    app = QApplication.instance() or QApplication([])
    clipboard = app.clipboard()
    original = QMimeData()
    source = clipboard.mimeData()
    if source is not None:
        for format_name in source.formats():
            original.setData(format_name, source.data(format_name))
    try:
        yield
    finally:
        if original.formats():
            clipboard.setMimeData(original)
        else:
            clipboard.clear()


@pytest.fixture(autouse=True)
def smart_editing_off_by_default(monkeypatch):
    """The app turns smart editing on by default; tests opt in so no real llama-server is launched."""
    from voxflow import i18n, rewriter

    monkeypatch.setattr(rewriter, "DEFAULT_ENABLED", False)
    i18n.set_language("en")
