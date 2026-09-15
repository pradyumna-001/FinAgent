"""Unit tests for the Telegram channel implementation.

No external services required — pure functions + Protocol shape checks.
"""

import pytest

from app.services.channels.base import NotePayload


def test_encode_decode_round_trip():
    from app.services.channels.telegram_channel import encode_callback, decode_callback
    c = encode_callback("approve", "run-42", 7)
    assert decode_callback(c) == ("approve", "run-42", 7)
    assert decode_callback("malformed") is None


def test_approval_keyboard_structure():
    from app.services.channels.telegram_channel import approval_keyboard
    kb = approval_keyboard("run-1", 42)
    assert kb.inline_keyboard  # InlineKeyboardMarkup uses .inline_keyboard
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "✅ aprovar" in texts
    assert "❌ rejeitar" in texts


def test_note_payload_immutable():
    from app.services.channels.base import NotePayload
    p = NotePayload("r1", 1, "PETR4", "buy", 0.8, "justificativa")
    assert p.ticker == "PETR4"
    assert p.confidence == 0.8
    # frozen should prevent mutation
    with pytest.raises((AttributeError,)):
        p.ticker = "TESTE"