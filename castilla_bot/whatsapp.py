"""Webhook para integração com a API oficial WhatsApp Cloud da Meta."""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request

from .bot import CastillaBot


# O arquivo .env é a fonte de configuração deste projeto. Isso evita que valores
# antigos deixados no PowerShell prevaleçam após uma edição das credenciais.
load_dotenv(override=True)


class WhatsAppClient:
    """Cliente mínimo para enviar mensagens de texto pela Graph API."""

    def __init__(
        self,
        access_token: str,
        phone_number_id: str,
        api_version: str,
    ) -> None:
        self.access_token = access_token
        self.phone_number_id = phone_number_id
        self.api_version = api_version

    def send_text(self, recipient: str, text: str) -> None:
        url = (
            f"https://graph.facebook.com/{self.api_version}/"
            f"{self.phone_number_id}/messages"
        )
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient,
                "type": "text",
                "text": {"preview_url": False, "body": text},
            },
            timeout=15,
        )
        response.raise_for_status()


def create_app(
    bot: CastillaBot | None = None,
    client: WhatsAppClient | None = None,
    verify_token: str | None = None,
    app_secret: str | None = None,
) -> Flask:
    """Cria a aplicação Flask; parâmetros opcionais facilitam os testes."""

    app = Flask(__name__)
    chatbot = bot or CastillaBot()
    if client is None:
        environment = _configuration_from_environment()
        configured_verify_token = verify_token or environment["WHATSAPP_VERIFY_TOKEN"]
        configured_app_secret = app_secret or environment["META_APP_SECRET"]
        whatsapp_client = WhatsAppClient(
            environment["WHATSAPP_ACCESS_TOKEN"],
            environment["WHATSAPP_PHONE_NUMBER_ID"],
            environment["META_GRAPH_API_VERSION"],
        )
    else:
        configured_verify_token = verify_token or os.getenv("WHATSAPP_VERIFY_TOKEN", "")
        configured_app_secret = app_secret or os.getenv("META_APP_SECRET", "")
        whatsapp_client = client

    @app.get("/")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "castilla-whatsapp-bot"}

    @app.get("/webhook")
    def verify_webhook() -> Response:
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == configured_verify_token and challenge:
            return Response(challenge, status=200, mimetype="text/plain")
        return Response("Verificação inválida", status=403)

    @app.post("/webhook")
    def receive_webhook() -> tuple[Response, int]:
        if configured_app_secret and not _valid_signature(
            request.get_data(),
            request.headers.get("X-Hub-Signature-256", ""),
            configured_app_secret,
        ):
            return jsonify({"error": "invalid signature"}), 401
        payload = request.get_json(silent=True) or {}
        # A Meta pode agrupar mais de uma entrada/alteração/mensagem no evento.
        for incoming in _text_messages(payload):
            sender = incoming["from"]
            message = incoming["text"]["body"]
            if sender not in chatbot.sessions:
                reply = chatbot.start(sender)
                # A primeira mensagem do usuário inicia a sessão e recebe o menu.
            else:
                reply = chatbot.handle(sender, message)
            whatsapp_client.send_text(sender, reply)
        # O recebimento deve ser confirmado mesmo quando o evento é só um status.
        return jsonify({"status": "received"}), 200

    return app


def _configuration_from_environment() -> dict[str, str]:
    values = {
        "WHATSAPP_VERIFY_TOKEN": os.getenv("WHATSAPP_VERIFY_TOKEN", ""),
        "WHATSAPP_ACCESS_TOKEN": os.getenv("WHATSAPP_ACCESS_TOKEN", ""),
        "WHATSAPP_PHONE_NUMBER_ID": os.getenv("WHATSAPP_PHONE_NUMBER_ID", ""),
        "META_APP_SECRET": os.getenv("META_APP_SECRET", ""),
        "META_GRAPH_API_VERSION": os.getenv("META_GRAPH_API_VERSION", ""),
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(
            "Configuração do WhatsApp incompleta. Copie .env.example para .env, "
            f"preencha os valores reais e tente novamente. Ausentes: {names}"
        )
    return values


def _text_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                if message.get("type") == "text" and message.get("from"):
                    messages.append(message)
    return messages


def _valid_signature(body: bytes, received: str, app_secret: str) -> bool:
    expected = "sha256=" + hmac.new(
        app_secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, received)


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
