"""Webhook para integração com a API oficial WhatsApp Cloud da Meta."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request

from .bot import CastillaBot, HUMAN_DONE


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
    operator_token: str | None = None,
    phone_number_id: str | None = None,
) -> Flask:
    """Cria a aplicação Flask; parâmetros opcionais facilitam os testes."""

    app = Flask(__name__)
    app.logger.setLevel(logging.INFO)
    chatbot = bot or CastillaBot()
    configured_operator_token = (
        os.getenv("OPERATOR_TOKEN", "") if operator_token is None else operator_token
    )
    if client is None:
        environment = _configuration_from_environment()
        configured_verify_token = verify_token or environment["WHATSAPP_VERIFY_TOKEN"]
        configured_app_secret = app_secret or environment["META_APP_SECRET"]
        configured_phone_number_id = phone_number_id or environment["WHATSAPP_PHONE_NUMBER_ID"]
        whatsapp_client = WhatsAppClient(
            environment["WHATSAPP_ACCESS_TOKEN"],
            configured_phone_number_id,
            environment["META_GRAPH_API_VERSION"],
        )
    else:
        configured_verify_token = verify_token or os.getenv("WHATSAPP_VERIFY_TOKEN", "")
        configured_app_secret = app_secret or os.getenv("META_APP_SECRET", "")
        configured_phone_number_id = (
            os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
            if phone_number_id is None else phone_number_id
        )
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
        # Em contas com coexistência, a Meta envia as mensagens digitadas no
        # WhatsApp Business da escola em um evento distinto das do cliente.
        for outgoing in _business_app_message_echoes(payload, configured_phone_number_id):
            customer = _contact_id(outgoing["to"])
            if customer:
                completed = chatbot.attendant_message(customer, outgoing["text"]["body"])
                if completed:
                    app.logger.info("Atendimento humano encerrado pelo WhatsApp Business")
        # A Meta pode agrupar mais de uma entrada/alteração/mensagem no evento.
        for incoming in _text_messages(payload, configured_phone_number_id):
            sender = _contact_id(incoming["from"])
            if sender is None:
                continue
            message = incoming["text"]["body"]
            reply = chatbot.receive(sender, message)
            if reply is not None:
                whatsapp_client.send_text(sender, reply)
                if reply == HUMAN_DONE:
                    app.logger.info("Aviso de passagem para atendente enviado")
        # O recebimento deve ser confirmado mesmo quando o evento é só um status.
        return jsonify({"status": "received"}), 200

    @app.post("/operator/complete")
    def complete_human_service() -> tuple[Response, int]:
        # O webhook de mensagens do cliente não identifica falas do atendente.
        # Uma interface de atendimento pode chamar esta rota com um token próprio.
        if not configured_operator_token:
            return jsonify({"error": "not found"}), 404
        authorization = request.headers.get("Authorization", "")
        expected = f"Bearer {configured_operator_token}"
        if not hmac.compare_digest(authorization, expected):
            return jsonify({"error": "unauthorized"}), 401
        payload = request.get_json(silent=True) or {}
        session_id = payload.get("customer_phone")
        message = payload.get("message")
        if not isinstance(session_id, str) or not isinstance(message, str):
            return jsonify({"error": "customer_phone and message are required"}), 400
        session_id = _contact_id(session_id)
        if session_id is None:
            return jsonify({"error": "invalid customer_phone"}), 400
        if message.strip().casefold() != "atendimento finalizado":
            return jsonify({"error": "invalid completion phrase"}), 400
        if not chatbot.attendant_message(session_id, message):
            return jsonify({"error": "human service not pending"}), 409
        return jsonify({"status": "completed"}), 200

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


def _text_messages(
    payload: dict[str, Any], phone_number_id: str = ""
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") not in (None, "messages"):
                continue
            value = change.get("value", {})
            if not _for_business_number(value, phone_number_id):
                continue
            for message in value.get("messages", []):
                if (
                    message.get("type") == "text"
                    and isinstance(message.get("from"), str)
                    and isinstance(message.get("text"), dict)
                    and isinstance(message["text"].get("body"), str)
                ):
                    messages.append(message)
    return messages


def _business_app_message_echoes(
    payload: dict[str, Any], phone_number_id: str = ""
) -> list[dict[str, Any]]:
    """Extrai mensagens enviadas pelo atendente no app WhatsApp Business."""
    echoes: list[dict[str, Any]] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "smb_message_echoes":
                continue
            value = change.get("value", {})
            if not _for_business_number(value, phone_number_id):
                continue
            for echo in value.get("message_echoes", []):
                if (
                    echo.get("type") == "text"
                    and isinstance(echo.get("to"), str)
                    and isinstance(echo.get("text"), dict)
                    and isinstance(echo["text"].get("body"), str)
                ):
                    echoes.append(echo)
    return echoes


def _for_business_number(value: dict[str, Any], phone_number_id: str) -> bool:
    if not phone_number_id:
        return True
    metadata = value.get("metadata", {})
    return isinstance(metadata, dict) and metadata.get("phone_number_id") == phone_number_id


def _contact_id(raw: str) -> str | None:
    if re.fullmatch(r"\+?[0-9]{8,15}", raw):
        return raw.removeprefix("+")
    return None


def _valid_signature(body: bytes, received: str, app_secret: str) -> bool:
    expected = "sha256=" + hmac.new(
        app_secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, received)


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
