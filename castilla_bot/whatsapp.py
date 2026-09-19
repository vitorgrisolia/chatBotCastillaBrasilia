"""Webhook para integração com a API oficial WhatsApp Cloud da Meta."""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
from datetime import datetime, timezone
from threading import Lock, Timer
from typing import Any, Callable

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, request

from .bot import CastillaBot, HUMAN_DONE, INACTIVITY_DONE
from .private_storage import PrivateSqliteStorage


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


class InactivityScheduler:
    """Mantém no máximo um temporizador ativo para cada conversa."""

    def __init__(self, callback: Callable[[str, str], None]) -> None:
        self.callback = callback
        self._lock = Lock()
        self._timers: dict[str, tuple[str, Timer]] = {}

    def schedule(
        self,
        session_id: str,
        expected_activity: str,
        deadline: datetime | None = None,
        *,
        delay_seconds: float | None = None,
    ) -> None:
        if delay_seconds is None:
            if deadline is None:
                raise ValueError("Informe deadline ou delay_seconds")
            delay_seconds = max(
                0.0,
                (deadline.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds(),
            )
        timer = Timer(delay_seconds, self._run, args=(session_id, expected_activity))
        timer.daemon = True
        with self._lock:
            previous = self._timers.pop(session_id, None)
            if previous is not None:
                previous[1].cancel()
            self._timers[session_id] = (expected_activity, timer)
        timer.start()

    def cancel(self, session_id: str) -> None:
        with self._lock:
            previous = self._timers.pop(session_id, None)
        if previous is not None:
            previous[1].cancel()

    def _run(self, session_id: str, expected_activity: str) -> None:
        with self._lock:
            current = self._timers.get(session_id)
            if current is None or current[0] != expected_activity:
                return
            self._timers.pop(session_id, None)
        self.callback(session_id, expected_activity)


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
    # Um único processo: eventos repetidos da mesma conversa não podem enviar
    # respostas simultâneas enquanto a primeira chamada à Meta está pendente.
    contact_locks = [Lock() for _ in range(64)]
    chatbot = bot or CastillaBot()
    if (
        os.getenv("CASTILLA_ENV", "development").casefold() == "production"
        and not isinstance(chatbot.storage, PrivateSqliteStorage)
    ):
        raise RuntimeError("Em produção, o armazenamento deve ser SQLite privado")
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

    scheduler: InactivityScheduler

    def close_inactive_service(customer: str, expected_activity: str) -> None:
        with contact_locks[hash(customer) % len(contact_locks)]:
            if not chatbot.inactivity_is_due(customer, expected_activity):
                return
            try:
                whatsapp_client.send_text(customer, INACTIVITY_DONE)
                if chatbot.close_for_inactivity(customer, expected_activity):
                    app.logger.info("Atendimento automático encerrado por inatividade")
            except Exception as exc:
                app.logger.error("Falha ao encerrar atendimento inativo: %s", _safe_error_label(exc))
                scheduler.schedule(customer, expected_activity, delay_seconds=5)

    scheduler = InactivityScheduler(close_inactive_service)

    def refresh_inactivity(customer: str) -> None:
        deadline = chatbot.inactivity_deadline(customer)
        if deadline is None:
            scheduler.cancel(customer)
        else:
            expected_activity, expires_at = deadline
            scheduler.schedule(customer, expected_activity, expires_at)

    @app.get("/")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "castilla-whatsapp-bot"}

    @app.get("/ready")
    def readiness() -> tuple[Response, int]:
        if isinstance(chatbot.storage, PrivateSqliteStorage):
            try:
                chatbot.storage.check_readiness()
            except Exception as exc:
                app.logger.error("Banco indisponível: %s", _safe_error_label(exc))
                return jsonify({"status": "unavailable"}), 503
        return jsonify({"status": "ready"}), 200

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
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "invalid payload"}), 400
        try:
            # Em contas com coexistência, a Meta envia as mensagens digitadas no
            # WhatsApp Business da escola em um evento distinto das do cliente.
            for outgoing in _business_app_message_echoes(payload, configured_phone_number_id):
                customer = _contact_id(outgoing["to"])
                if customer:
                    with contact_locks[hash(customer) % len(contact_locks)]:
                        completed = chatbot.attendant_message(customer, outgoing["text"]["body"])
                    if completed:
                        app.logger.info("Atendimento humano encerrado pelo WhatsApp Business")
            # A Meta pode agrupar mais de uma entrada/alteração/mensagem no evento.
            for incoming in _text_messages(payload, configured_phone_number_id):
                sender = _contact_id(incoming["from"])
                if sender is None:
                    continue
                message_id = incoming.get("id")
                if not isinstance(message_id, str):
                    message_id = None
                with contact_locks[hash(sender) % len(contact_locks)]:
                    reply = chatbot.receive(sender, incoming["text"]["body"], message_id)
                    if reply is not None:
                        whatsapp_client.send_text(sender, reply)
                        chatbot.reply_delivered(sender, message_id)
                        if reply == HUMAN_DONE:
                            app.logger.info("Aviso de passagem para atendente enviado")
                    refresh_inactivity(sender)
            for _ in _failed_delivery_statuses(payload, configured_phone_number_id):
                app.logger.error("A Meta informou falha na entrega de uma mensagem")
        except Exception as exc:
            # Não confirme um lote que falhou: a Meta pode reenviá-lo. Não registre
            # conteúdo, número de telefone ou tokens nos logs.
            app.logger.error("Falha ao processar webhook: %s", _safe_error_label(exc))
            return jsonify({"error": "temporary processing failure"}), 503
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


def _failed_delivery_statuses(
    payload: dict[str, Any], phone_number_id: str = ""
) -> list[dict[str, Any]]:
    failed: list[dict[str, Any]] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") not in (None, "messages"):
                continue
            value = change.get("value", {})
            if not _for_business_number(value, phone_number_id):
                continue
            failed.extend(
                status for status in value.get("statuses", [])
                if isinstance(status, dict) and status.get("status") == "failed"
            )
    return failed


def _for_business_number(value: dict[str, Any], phone_number_id: str) -> bool:
    if not phone_number_id:
        return True
    metadata = value.get("metadata", {})
    return isinstance(metadata, dict) and metadata.get("phone_number_id") == phone_number_id


def _contact_id(raw: str) -> str | None:
    if re.fullmatch(r"\+?[0-9]{8,15}", raw):
        return raw.removeprefix("+")
    return None


def _safe_error_label(exc: Exception) -> str:
    """Diagnóstico sem texto da Meta, URL, telefone ou credenciais."""
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        response = exc.response
        try:
            error = response.json().get("error", {})
        except (ValueError, AttributeError):
            error = {}
        meta_code = error.get("code") if isinstance(error, dict) else None
        code = meta_code if isinstance(meta_code, int) else "unknown"
        return f"HTTPError status={response.status_code} meta_code={code}"
    return type(exc).__name__


def _valid_signature(body: bytes, received: str, app_secret: str) -> bool:
    expected = "sha256=" + hmac.new(
        app_secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, received)


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
