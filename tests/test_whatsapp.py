import unittest
import hashlib
import hmac
import json
import sqlite3
import tempfile
import time
from unittest.mock import patch
from uuid import uuid4

import requests

from castilla_bot.bot import CastillaBot
from castilla_bot.private_storage import PrivateSqliteStorage
from castilla_bot.storage import JsonlStorage
from castilla_bot.whatsapp import _safe_error_label, create_app


class FakeWhatsAppClient:
    def __init__(self):
        self.sent = []
        self.fail_next = 0
        self.fail_on_attempt = None
        self.attempts = 0

    def send_text(self, recipient, text):
        self.attempts += 1
        if self.attempts == self.fail_on_attempt:
            raise requests.Timeout("falha simulada")
        if self.fail_next:
            self.fail_next -= 1
            raise requests.Timeout("falha simulada")
        self.sent.append((recipient, text))


class WhatsAppWebhookTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.sender = FakeWhatsAppClient()
        self.app = create_app(
            bot=CastillaBot(JsonlStorage(self.temp_dir.name)),
            client=self.sender,
            verify_token="segredo-de-teste",
            app_secret="app-secret-de-teste",
            operator_token="token-do-atendente",
            phone_number_id="school-test-id",
        ).test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_meta_verification(self):
        response = self.app.get(
            "/webhook?hub.mode=subscribe&hub.verify_token=segredo-de-teste&hub.challenge=12345"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "12345")

    def test_invalid_verification_token(self):
        response = self.app.get(
            "/webhook?hub.mode=subscribe&hub.verify_token=errado&hub.challenge=12345"
        )
        self.assertEqual(response.status_code, 403)

    def test_first_message_opens_menu_and_second_is_processed(self):
        first = self._post_signed(self._message_payload("Olá"))
        second = self._post_signed(self._message_payload("3"))
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertIn("Seja bem-vindo", self.sender.sent[0][1])
        self.assertIn("Conheça nossos planos", self.sender.sent[1][1])

    def test_whatsapp_reply_keeps_only_unselected_options(self):
        self._post_signed(self._message_payload("Olá"))
        self._post_signed(self._message_payload("1"))
        course_reply = self.sender.sent[-1][1]
        self.assertNotIn("1️⃣ Conhecer o curso", course_reply)
        self.assertIn("2️⃣ Ver nossa metodologia", course_reply)

        self._post_signed(self._message_payload("2"))
        methodology_reply = self.sender.sent[-1][1]
        self.assertNotIn("1️⃣ Conhecer o curso", methodology_reply)
        self.assertNotIn("2️⃣ Ver nossa metodologia", methodology_reply)
        self.assertIn("3️⃣ Consultar planos e valores", methodology_reply)

    def test_human_handoff_stops_whatsapp_replies_until_operator_completes(self):
        for message in ("Olá", "6", "Maria", "Quero tirar uma dúvida"):
            self.assertEqual(self._post_signed(self._message_payload(message)).status_code, 200)
        self.assertIn("Aguarde um momento", self.sender.sent[-1][1])
        sent_count = len(self.sender.sent)

        for message in ("Olá?", "MENU", "REINICIAR", "atendimento finalizado"):
            self.assertEqual(self._post_signed(self._message_payload(message)).status_code, 200)
        self.assertEqual(len(self.sender.sent), sent_count)

        unauthorized = self.app.post(
            "/operator/complete",
            json={"customer_phone": "5561999999999", "message": "atendimento finalizado"},
        )
        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(len(self.sender.sent), sent_count)

        invalid_phrase = self.app.post(
            "/operator/complete",
            json={"customer_phone": "5561999999999", "message": "voltar"},
            headers={"Authorization": "Bearer token-do-atendente"},
        )
        self.assertEqual(invalid_phrase.status_code, 400)

        completed = self.app.post(
            "/operator/complete",
            json={"customer_phone": "5561999999999", "message": "atendimento finalizado"},
            headers={"Authorization": "Bearer token-do-atendente"},
        )
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(len(self.sender.sent), sent_count)
        self._post_signed(self._message_payload("MENU"))
        self.assertEqual(len(self.sender.sent), sent_count + 1)
        self.assertIn("Outras opções disponíveis", self.sender.sent[-1][1])

    def test_attendant_can_complete_from_whatsapp_business_app_echo(self):
        for message in ("Olá", "6", "Maria", "Quero tirar uma dúvida"):
            self._post_signed(self._message_payload(message))
        sent_count = len(self.sender.sent)

        self._post_signed(self._business_app_echo_payload("Ainda estou atendendo"))
        self._post_signed(self._message_payload("MENU"))
        self.assertEqual(len(self.sender.sent), sent_count)

        self._post_signed(self._business_app_echo_payload(" Atendimento Finalizado ", to="+5561999999999"))
        self.assertEqual(len(self.sender.sent), sent_count)
        self._post_signed(self._message_payload("MENU"))
        self.assertEqual(len(self.sender.sent), sent_count + 1)
        self.assertIn("Outras opções disponíveis", self.sender.sent[-1][1])

    def test_handoff_notice_is_sent_once_even_if_meta_repeats_the_event(self):
        for message in ("Olá", "6", "Maria"):
            self._post_signed(self._message_payload(message))
        final_message = self._message_payload("Dúvida sobre aulas")
        self._post_signed(final_message)
        sent_count = len(self.sender.sent)
        self.assertEqual(sum("Aguarde um momento" in text for _, text in self.sender.sent), 1)

        self._post_signed(final_message)
        self._post_signed(self._message_payload("Ainda não fui atendido"))
        self.assertEqual(len(self.sender.sent), sent_count)

    def test_meta_send_failure_retries_same_message_without_advancing_twice(self):
        first = self._message_payload("Olá")
        self.sender.fail_next = 1
        self.assertEqual(self._post_signed(first).status_code, 503)
        self.assertEqual(self.sender.sent, [])
        self.assertEqual(self._post_signed(first).status_code, 200)
        self.assertEqual(len(self.sender.sent), 1)
        self.assertIn("Seja bem-vindo", self.sender.sent[0][1])
        self.assertEqual(self._post_signed(first).status_code, 200)
        self.assertEqual(len(self.sender.sent), 1)

        for message in ("6", "Maria"):
            self._post_signed(self._message_payload(message))
        final = self._message_payload("Dúvida")
        self.sender.fail_next = 1
        self.assertEqual(self._post_signed(final).status_code, 503)
        self.assertEqual(sum("Aguarde um momento" in text for _, text in self.sender.sent), 0)
        self.assertEqual(self._post_signed(final).status_code, 200)
        self.assertEqual(self._post_signed(final).status_code, 200)
        self.assertEqual(sum("Aguarde um momento" in text for _, text in self.sender.sent), 1)

    def test_batch_retry_skips_message_already_sent(self):
        batch = self._message_payload("Olá")
        second = self._message_payload("3")
        batch["entry"][0]["changes"][0]["value"]["messages"].extend(
            second["entry"][0]["changes"][0]["value"]["messages"]
        )
        self.sender.fail_on_attempt = 2
        self.assertEqual(self._post_signed(batch).status_code, 503)
        self.assertEqual(len(self.sender.sent), 1)
        self.assertEqual(self._post_signed(batch).status_code, 200)
        self.assertEqual(len(self.sender.sent), 2)
        self.assertIn("Conheça nossos planos", self.sender.sent[1][1])

    def test_wrong_business_number_and_wrong_customer_cannot_complete(self):
        for message in ("Olá", "6", "Maria", "Dúvida"):
            self._post_signed(self._message_payload(message))
        sent_count = len(self.sender.sent)

        wrong_business = self._business_app_echo_payload("atendimento finalizado")
        wrong_business["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"] = "other-school"
        self._post_signed(wrong_business)
        self._post_signed(self._business_app_echo_payload("atendimento finalizado", to="5561888888888"))
        self._post_signed(self._message_payload("MENU"))
        self.assertEqual(len(self.sender.sent), sent_count)

    def test_handoff_stays_silent_after_restart_with_private_database(self):
        database = f"{self.temp_dir.name}/private/castilla.sqlite3"
        persistent_storage = PrivateSqliteStorage(database)
        first_sender = FakeWhatsAppClient()
        first_app = create_app(
            bot=CastillaBot(persistent_storage),
            client=first_sender,
            app_secret="app-secret-de-teste",
            phone_number_id="school-test-id",
        ).test_client()
        for message in ("Olá", "6", "Maria", "Dúvida"):
            self._post_signed(self._message_payload(message), app=first_app)
        self.assertEqual(sum("Aguarde um momento" in text for _, text in first_sender.sent), 1)

        restarted_sender = FakeWhatsAppClient()
        restarted_app = create_app(
            bot=CastillaBot(PrivateSqliteStorage(database)),
            client=restarted_sender,
            app_secret="app-secret-de-teste",
            phone_number_id="school-test-id",
        ).test_client()
        for message in ("MENU", "REINICIAR", "atendimento finalizado"):
            self._post_signed(self._message_payload(message), app=restarted_app)
        self.assertEqual(restarted_sender.sent, [])

        self._post_signed(self._business_app_echo_payload("atendimento finalizado"), app=restarted_app)
        self.assertEqual(restarted_sender.sent, [])
        self._post_signed(self._message_payload("MENU"), app=restarted_app)
        self.assertEqual(len(restarted_sender.sent), 1)
        self.assertIn("Outras opções disponíveis", restarted_sender.sent[0][1])

    def test_failed_notice_can_be_retried_after_restart(self):
        database = f"{self.temp_dir.name}/private/castilla.sqlite3"
        first_sender = FakeWhatsAppClient()
        first_app = create_app(
            bot=CastillaBot(PrivateSqliteStorage(database)),
            client=first_sender,
            app_secret="app-secret-de-teste",
            phone_number_id="school-test-id",
        ).test_client()
        for message in ("Olá", "6", "Maria"):
            self._post_signed(self._message_payload(message), app=first_app)
        final = self._message_payload("Dúvida")
        first_sender.fail_next = 1
        self.assertEqual(self._post_signed(final, app=first_app).status_code, 503)

        restarted_sender = FakeWhatsAppClient()
        restarted_app = create_app(
            bot=CastillaBot(PrivateSqliteStorage(database)),
            client=restarted_sender,
            app_secret="app-secret-de-teste",
            phone_number_id="school-test-id",
        ).test_client()
        self.assertEqual(self._post_signed(final, app=restarted_app).status_code, 200)
        self.assertEqual(self._post_signed(final, app=restarted_app).status_code, 200)
        self.assertEqual(sum("Aguarde um momento" in text for _, text in restarted_sender.sent), 1)

    def test_api_message_echo_does_not_complete_human_service(self):
        for message in ("Olá", "6", "Maria", "Quero tirar uma dúvida"):
            self._post_signed(self._message_payload(message))
        sent_count = len(self.sender.sent)
        echo = self._business_app_echo_payload("atendimento finalizado")
        echo["entry"][0]["changes"][0]["field"] = "message_echoes"
        self._post_signed(echo)
        self._post_signed(self._message_payload("MENU"))
        self.assertEqual(len(self.sender.sent), sent_count)

    def test_status_event_is_ignored(self):
        response = self._post_signed(
            {"entry": [{"changes": [{"value": {"statuses": [{}]}}]}]}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.sender.sent, [])

    def test_failed_delivery_status_is_logged_without_customer_data(self):
        payload = {
            "entry": [{"changes": [{"field": "messages", "value": {
                "metadata": {"phone_number_id": "school-test-id"},
                "statuses": [{"status": "failed", "recipient_id": "5561999999999"}],
            }}]}]
        }
        with self.assertLogs("castilla_bot.whatsapp", level="ERROR") as captured:
            response = self._post_signed(payload)
        self.assertEqual(response.status_code, 200)
        self.assertIn("falha na entrega", captured.output[0])
        self.assertNotIn("5561999999999", captured.output[0])

    def test_meta_http_error_label_does_not_log_raw_response(self):
        response = requests.Response()
        response.status_code = 429
        response._content = b'{"error":{"code":4,"message":"sensitive details"}}'
        error = requests.HTTPError("raw request details", response=response)
        self.assertEqual(_safe_error_label(error), "HTTPError status=429 meta_code=4")

    def test_unsigned_event_is_rejected(self):
        response = self.app.post("/webhook", json=self._message_payload("Olá"))
        self.assertEqual(response.status_code, 401)

    def test_operator_route_is_disabled_without_token(self):
        app = create_app(
            bot=CastillaBot(JsonlStorage(self.temp_dir.name)),
            client=FakeWhatsAppClient(),
            operator_token="",
        ).test_client()
        response = app.post(
            "/operator/complete",
            json={"customer_phone": "5561999999999", "message": "atendimento finalizado"},
        )
        self.assertEqual(response.status_code, 404)

    def test_dotenv_is_loaded_only_for_real_runtime(self):
        with patch("castilla_bot.whatsapp.load_dotenv") as dotenv_loader:
            create_app(
                bot=CastillaBot(JsonlStorage(self.temp_dir.name)),
                client=FakeWhatsAppClient(),
            )
            dotenv_loader.assert_not_called()

        environment = {
            "WHATSAPP_VERIFY_TOKEN": "verify-test",
            "WHATSAPP_ACCESS_TOKEN": "access-test",
            "WHATSAPP_PHONE_NUMBER_ID": "phone-test",
            "META_APP_SECRET": "secret-test",
            "META_GRAPH_API_VERSION": "v23.0",
        }
        with (
            patch("castilla_bot.whatsapp.load_dotenv") as dotenv_loader,
            patch(
                "castilla_bot.whatsapp._configuration_from_environment",
                return_value=environment,
            ),
        ):
            create_app(
                bot=CastillaBot(JsonlStorage(self.temp_dir.name)),
                client=None,
            )
            dotenv_loader.assert_called_once_with(override=False)

    def test_production_refuses_legacy_storage(self):
        with patch.dict("os.environ", {"CASTILLA_ENV": "production"}):
            with self.assertRaisesRegex(RuntimeError, "SQLite privado"):
                create_app(
                    bot=CastillaBot(JsonlStorage(self.temp_dir.name)),
                    client=FakeWhatsAppClient(),
                )

    def test_readiness_checks_private_database(self):
        database = f"{self.temp_dir.name}/private/castilla.sqlite3"
        storage = PrivateSqliteStorage(database)
        app = create_app(
            bot=CastillaBot(storage),
            client=FakeWhatsAppClient(),
        ).test_client()
        self.assertEqual(app.get("/ready").status_code, 200)
        with patch.object(storage, "check_readiness", side_effect=sqlite3.OperationalError):
            self.assertEqual(app.get("/ready").status_code, 503)

    def test_inactivity_timer_sends_one_closure_and_next_message_restarts(self):
        sender = FakeWhatsAppClient()
        app = create_app(
            bot=CastillaBot(JsonlStorage(self.temp_dir.name), inactivity_seconds=0.05),
            client=sender,
            app_secret="app-secret-de-teste",
            phone_number_id="school-test-id",
        ).test_client()
        self.assertEqual(self._post_signed(self._message_payload("Olá"), app=app).status_code, 200)

        deadline = time.monotonic() + 1
        while len(sender.sent) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(sum("encerrado por falta de interação" in text for _, text in sender.sent), 1)
        time.sleep(0.1)
        self.assertEqual(sum("encerrado por falta de interação" in text for _, text in sender.sent), 1)

        self.assertEqual(self._post_signed(self._message_payload("Olá novamente"), app=app).status_code, 200)
        self.assertIn("Seja bem-vindo", sender.sent[-1][1])

    @staticmethod
    def _message_payload(text):
        return {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": "school-test-id"},
                                "messages": [
                                    {
                                        "id": uuid4().hex,
                                        "from": "5561999999999",
                                        "type": "text",
                                        "text": {"body": text},
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }

    @staticmethod
    def _business_app_echo_payload(text, to="5561999999999"):
        return {
            "entry": [
                {
                    "changes": [
                        {
                            "field": "smb_message_echoes",
                            "value": {
                                "metadata": {"phone_number_id": "school-test-id"},
                                "message_echoes": [
                                    {
                                        "from": "5561888888888",
                                        "to": to,
                                        "type": "text",
                                        "text": {"body": text},
                                    }
                                ]
                            },
                        }
                    ]
                }
            ]
        }

    def _post_signed(self, payload, app=None):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        signature = "sha256=" + hmac.new(
            b"app-secret-de-teste", body, hashlib.sha256
        ).hexdigest()
        return (app or self.app).post(
            "/webhook",
            data=body,
            content_type="application/json",
            headers={"X-Hub-Signature-256": signature},
        )


if __name__ == "__main__":
    unittest.main()
