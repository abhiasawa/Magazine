"""Vercel entrypoint for the Flask web application."""

from magazine.review.app import create_app

app = create_app()
