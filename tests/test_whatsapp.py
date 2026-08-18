import unittest
import hashlib
import hmac
import json

from castilla_bot.bot import CastillaBot
from castilla_bot.whatsapp import create_app


class FakeWhatsAppClient:
    def __init__(self):
        self.sent = []

    def send_text(self, recipient, text):
        self.sent.append((recipient, text))


class WhatsAppWebhookTests(unittest.TestCase):
    def setUp(self):
        self.sender = FakeWhatsAppClient()
        self.app = create_app(
            bot=CastillaBot(),
            client=self.sender,
            verify_token="segredo-de-teste",
            app_secret="app-secret-de-teste",
        ).test_client()

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

    def test_status_event_is_ignored(self):
        response = self._post_signed(
            {"entry": [{"changes": [{"value": {"statuses": [{}]}}]}]}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.sender.sent, [])

    def test_unsigned_event_is_rejected(self):
        response = self.app.post("/webhook", json=self._message_payload("Olá"))
        self.assertEqual(response.status_code, 401)

    @staticmethod
    def _message_payload(text):
        return {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
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

    def _post_signed(self, payload):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        signature = "sha256=" + hmac.new(
            b"app-secret-de-teste", body, hashlib.sha256
        ).hexdigest()
        return self.app.post(
            "/webhook",
            data=body,
            content_type="application/json",
            headers={"X-Hub-Signature-256": signature},
        )


if __name__ == "__main__":
    unittest.main()
