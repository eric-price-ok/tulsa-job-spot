from datetime import datetime

from fastapi.templating import Jinja2Templates

from .config import settings

templates = Jinja2Templates(directory="app/templates")

# Globals available in every template without passing explicitly
templates.env.globals["settings"] = settings
templates.env.globals["enabled_providers"] = settings.enabled_providers
templates.env.globals["now"] = datetime.now
