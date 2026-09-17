from core.logger import redact


def test_redact_mascara_header_authorization():
    assert redact("Authorization: Bearer abc123") == "Authorization: ***"


def test_redact_mascara_tokens_e_chaves():
    assert redact("api_key=sk-xyz token=abc") == "api_key=*** token=***"


def test_redact_preserva_texto_comum():
    assert redact("sync de WAI-1234 concluído") == "sync de WAI-1234 concluído"
