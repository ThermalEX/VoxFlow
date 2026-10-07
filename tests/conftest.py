"""Shared test fixtures that avoid changing the user's desktop state."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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
