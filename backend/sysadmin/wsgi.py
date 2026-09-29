import os
from pathlib import Path

from django.core.wsgi import get_wsgi_application


def _load_dotenv():
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    backend_dir = Path(__file__).resolve().parent.parent
    env_path = backend_dir.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


_load_dotenv()

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sysadmin.settings.production')
application = get_wsgi_application()
