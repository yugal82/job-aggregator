"""Vercel entry point.

Vercel's Python runtime discovers an ASGI/WSGI ``app`` at the module
level. We just re-export the production FastAPI app. All real logic
stays in ``app/`` — this file exists so Vercel can find the handler.
"""
from app.main import app

__all__ = ["app"]
