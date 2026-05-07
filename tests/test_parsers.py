def test_whatsapp_parser_strips_system_messages():
    from parsers import parse_whatsapp_txt
    sample = """[1/15/24, 10:30] Tulsi: Client submitted I-140 today
[1/15/24, 10:31] Arjun: Thank you for the update
[1/15/24, 10:32] Tulsi: Next step is medical exam
Messages and calls are end-to-end encrypted"""
    result = parse_whatsapp_txt(sample, "Arjun Mehta")
    assert "I-140" in result
    assert "end-to-end encrypted" not in result

def test_extract_dates_finds_dates_in_text():
    from parsers import extract_dates_from_text
    text = "The deadline is June 15th, 2026. Meeting scheduled for April 22, 2026."
    dates = extract_dates_from_text(text)
    assert isinstance(dates, list)
    assert len(dates) >= 1

def test_extract_dates_returns_empty_list_on_empty_input():
    from parsers import extract_dates_from_text
    assert extract_dates_from_text("") == []

def test_extract_dates_returns_list_on_no_dates():
    from parsers import extract_dates_from_text
    result = extract_dates_from_text("Hello world, everything is fine.")
    assert isinstance(result, list)
