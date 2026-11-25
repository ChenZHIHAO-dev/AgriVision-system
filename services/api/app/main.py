"""ASGI entry point for the installed service."""

from .application import create_app

app = create_app()
