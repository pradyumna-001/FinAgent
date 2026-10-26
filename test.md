def test_1():
    mokeypatch.setattr(settings, TELEGRAM_BOT_TOKEN, "")

    result = await telegram_polling_loop()

    assert result['source'] == telegram
    assert res['message'] == "no TELEGRAM_BOT_TOKEN configured — gate auto-passes"