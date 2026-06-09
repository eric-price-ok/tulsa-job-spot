from datetime import datetime

from fastapi.templating import Jinja2Templates

from .config import settings

templates = Jinja2Templates(directory="app/templates")

# Globals available in every template without passing explicitly
templates.env.globals["settings"] = settings
templates.env.globals["enabled_providers"] = settings.enabled_providers
templates.env.globals["now"] = datetime.now


def _format_phone(value: str | None) -> str:
    if not value:
        return ""
    digits = "".join(c for c in value if c.isdigit())
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    if len(digits) == 10:
        return f"{digits[:3]}.{digits[3:6]}.{digits[6:]}"
    return value


templates.env.filters["format_phone"] = _format_phone
