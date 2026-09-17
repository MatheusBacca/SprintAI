import logging
import re

_SECRET_PATTERNS = [
    re.compile(r"(authorization\s*[:=]\s*)(\S+(?:\s+\S+)?)", re.IGNORECASE),
    re.compile(r"((?:token|api[_-]?key|password|secret)\s*[:=]\s*)(\S+)", re.IGNORECASE),
]


def redact(message: str) -> str:
    for pattern in _SECRET_PATTERNS:
        message = pattern.sub(r"\1***", message)
    return message


class RedactSecretsFilter(logging.Filter):
    """Mascara headers de autorização e tokens que escaparem para mensagens de log."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = redact(message)
        if redacted != message:
            record.msg = redacted
            record.args = None
        return True


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        handler.addFilter(RedactSecretsFilter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger
