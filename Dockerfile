FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md constraints.txt ./
COPY castilla_bot ./castilla_bot
RUN pip install --no-cache-dir -c constraints.txt . \
    && useradd --system --create-home --uid 10001 castilla
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

ENV PORT=8000
EXPOSE 8000
ENTRYPOINT ["sh", "/usr/local/bin/docker-entrypoint.sh"]
# Um processo com várias threads: os bloqueios por contato ficam em memória e só
# protegem conversas dentro do mesmo processo. Não aumente --workers.
CMD ["sh", "-c", "exec gunicorn --workers 1 --threads 4 --bind 0.0.0.0:${PORT} 'castilla_bot.whatsapp:create_app()'"]
