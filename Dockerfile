FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY castilla_bot ./castilla_bot
RUN pip install --no-cache-dir .

ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "gunicorn --workers 1 --bind 0.0.0.0:${PORT} 'castilla_bot.whatsapp:create_app()'"]
