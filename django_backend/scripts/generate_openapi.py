"""Generate OpenAPI schema (openapi.yaml) using drf-spectacular.

Run:
    python scripts/generate_openapi.py

Requires drf-spectacular installed in the environment.
"""
import os
import sys
import django

# Ensure project root is on sys.path so Django project package is importable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Ensure settings module is set
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'django_project.settings')
django.setup()

from django.core.management import call_command


def main():
    # Use drf-spectacular management command which handles serialization across versions
    try:
        call_command('spectacular', '--file', './doc/openapi.yaml')
        print('Generated openapi.yaml via manage.py spectacular')
    except Exception as e:
        print('Failed to generate openapi.yaml:', e)


if __name__ == '__main__':
    main()
