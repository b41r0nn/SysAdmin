#!/usr/bin/env python
import os
import sys
from pathlib import Path


def main():
    # Cargar .env automáticamente en desarrollo local (no sobreescribe
    # variables que ya existan en el entorno; en Docker no tiene efecto).
    try:
        from dotenv import load_dotenv
    except ImportError:
        load_dotenv = None

    if load_dotenv is not None:
        backend_dir = Path(__file__).resolve().parent
        env_path = backend_dir.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sysadmin.settings.local')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
