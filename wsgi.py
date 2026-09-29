"""WSGI entry point: `flask --app wsgi run` locally, gunicorn wsgi:app in containers."""
from app import create_app

app = create_app()

if __name__ == "__main__":  # pragma: no cover
    app.run(host="0.0.0.0", port=5000)
