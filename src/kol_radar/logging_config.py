import logging
import re


_SECRET_PATTERN = re.compile(
    r"(?i)\b(api_key|authorization|cookie|token|auth_code)\b(\s*[:=]\s*)([^\s,;]+)"
)


class SecretRedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        record.msg = _SECRET_PATTERN.sub(r"\1\2[REDACTED]", message)
        record.args = ()
        return True


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(SecretRedactingFilter())
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
