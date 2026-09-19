import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from castilla_bot.bot import CastillaBot, INACTIVITY_DONE, INVALID, PRE_ENROLLMENT_FIELDS, WELCOME
from castilla_bot.storage import JsonlStorage


class CastillaBotTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.bot = CastillaBot(JsonlStorage(self.temp_dir.name))
        self.session = "cliente-1"
        self.bot.start(self.session)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_selected_option_disappears_and_other_options_remain(self):
        course = self.bot.handle(self.session, "1")
        self.assertIn("curso de inglês", course)
        self.assertNotIn("1️⃣ Conhecer o curso", course)
        self.assertIn("2️⃣ Ver nossa metodologia", course)
        self.assertIn("3️⃣ Consultar planos e valores", course)

        methodology = self.bot.handle(self.session, "2")
        self.assertIn("três tipos de aula", methodology)
        self.assertNotIn("1️⃣ Conhecer o curso", methodology)
        self.assertNotIn("2️⃣ Ver nossa metodologia", methodology)
        self.assertIn("3️⃣ Consultar planos e valores", methodology)
        self.assertIn("4️⃣ Fazer minha pré-matrícula", methodology)
        self.assertEqual(self.bot.handle(self.session, "MENU"), self.bot.handle(self.session, "menu"))

    def test_selected_option_cannot_be_repeated_until_restart(self):
        self.bot.handle(self.session, "1")
        repeated = self.bot.handle(self.session, "1")
        self.assertIn("já selecionou", repeated)
        self.assertNotIn("1️⃣ Conhecer o curso", repeated)
        self.assertEqual(self.bot.handle(self.session, "REINICIAR"), WELCOME)
        self.assertIn("curso de inglês", self.bot.handle(self.session, "1"))

    def test_selected_options_are_independent_per_customer(self):
        self.bot.handle(self.session, "1")
        other_session = "cliente-2"
        self.assertEqual(self.bot.start(other_session), WELCOME)
        self.assertIn("1️⃣ Conhecer o curso", self.bot.handle(other_session, "MENU"))

    def test_cancelled_pre_enrollment_keeps_option_available(self):
        self.bot.handle(self.session, "4")
        remaining = self.bot.handle(self.session, "MENU")
        self.assertIn("4️⃣ Fazer minha pré-matrícula", remaining)

    def test_invalid_option(self):
        response = self.bot.handle(self.session, "99")
        self.assertTrue(response.startswith(INVALID))
        self.assertIn("1️⃣ Conhecer o curso", response)

    def test_human_service_is_saved(self):
        self.bot.handle(self.session, "6")
        self.bot.handle(self.session, "Maria")
        response = self.bot.handle(self.session, "Quero tirar uma dúvida")
        self.assertIn("Aguarde um momento", response)
        path = Path(self.temp_dir.name) / "atendimentos.jsonl"
        record = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(record["nome"], "Maria")
        self.assertEqual(record["assunto"], "Quero tirar uma dúvida")

    def test_bot_stays_silent_until_attendant_finishes_service(self):
        self.bot.handle(self.session, "6")
        self.bot.handle(self.session, "Maria")
        self.bot.handle(self.session, "Quero tirar uma dúvida")

        for message in ("Olá?", "MENU", "REINICIAR", "atendimento finalizado"):
            self.assertIsNone(self.bot.handle(self.session, message))
        self.assertFalse(self.bot.attendant_message(self.session, "Outro texto"))
        self.assertFalse(self.bot.attendant_message("outro-cliente", "atendimento finalizado"))
        self.assertIsNone(self.bot.handle(self.session, "Ainda está aí?"))

        self.assertTrue(self.bot.attendant_message(self.session, " Atendimento Finalizado "))
        self.assertIn("1️⃣ Conhecer o curso", self.bot.handle(self.session, "MENU"))
        self.assertFalse(self.bot.attendant_message(self.session, "atendimento finalizado"))

    def test_pre_enrollment_is_saved_with_selected_plan_and_price(self):
        self.bot.handle(self.session, "4")
        first_prompt = self.bot.handle(self.session, "2")
        self.assertIn("pré-matrícula", first_prompt)
        self.assertIn(f"1/{len(PRE_ENROLLMENT_FIELDS)}", first_prompt)
        self.assertIn("Nome completo", first_prompt)
        response = ""
        for index in range(len(PRE_ENROLLMENT_FIELDS)):
            key = PRE_ENROLLMENT_FIELDS[index][0]
            answer = {
                "email": "Aluna@Example.COM",
                "cpf": "529.982.247-25",
                "whatsapp": "(61) 99999-9999",
            }.get(key, f"resposta-{index}")
            response = self.bot.handle(self.session, answer)
        self.assertIn("Pré-matrícula recebida", response)
        self.assertIn("Básico — R$ 197,00/mês", response)
        self.assertIn("Um atendente entrará em contato", response)
        self.assertIn("finalizar seu cadastro", response)
        self.assertNotIn("4️⃣ Fazer minha pré-matrícula", response)
        self.assertIn("3️⃣ Consultar planos e valores", response)
        path = Path(self.temp_dir.name) / "pre_matriculas.jsonl"
        record = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(record["plano"], "Básico — R$ 197,00/mês")
        self.assertEqual(record["nome_completo"], "resposta-0")
        self.assertEqual(record["endereco"], "resposta-1")
        self.assertEqual(record["email"], "Aluna@example.com")
        self.assertEqual(record["cpf"], "52998224725")
        self.assertEqual(record["whatsapp"], "5561999999999")

    def test_invalid_email_and_whatsapp_do_not_advance_or_save(self):
        self.bot.handle(self.session, "4")
        self.bot.handle(self.session, "2")
        self.bot.handle(self.session, "Maria")
        self.bot.handle(self.session, "Rua Central")
        self.assertIn("E-mail inválido", self.bot.handle(self.session, "maria@"))
        self.assertIn("E-mail inválido", self.bot.handle(self.session, "maria..silva@example.com"))
        self.assertIn("CPF", self.bot.handle(self.session, "maria@example.com"))
        self.assertIn("WhatsApp", self.bot.handle(self.session, "529.982.247-25"))
        self.assertIn("WhatsApp inválido", self.bot.handle(self.session, "99999-9999"))
        self.assertFalse((Path(self.temp_dir.name) / "pre_matriculas.jsonl").exists())
        self.assertIn("Pré-matrícula recebida", self.bot.handle(self.session, "+55 (61) 99999-9999"))

    def test_invalid_cpf_is_rejected_without_advancing(self):
        self.bot.handle(self.session, "4")
        self.bot.handle(self.session, "2")
        for answer in ("Maria", "Rua Central", "maria@example.com"):
            self.bot.handle(self.session, answer)
        self.assertIn("CPF inválido", self.bot.handle(self.session, "111.111.111-11"))
        self.assertIn("CPF inválido", self.bot.handle(self.session, "529.982.247-24"))
        self.assertFalse((Path(self.temp_dir.name) / "pre_matriculas.jsonl").exists())
        self.assertIn("WhatsApp", self.bot.handle(self.session, "529.982.247-25"))

    def test_inactivity_resets_automatic_service_after_30_seconds(self):
        now = [datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)]
        bot = CastillaBot(
            JsonlStorage(self.temp_dir.name),
            inactivity_seconds=30,
            clock=lambda: now[0],
        )
        self.assertEqual(bot.receive("timeout-client", "Olá", "m1"), WELCOME)
        bot.reply_delivered("timeout-client", "m1")

        now[0] += timedelta(seconds=29)
        self.assertIn("curso de inglês", bot.receive("timeout-client", "1", "m2"))
        bot.reply_delivered("timeout-client", "m2")

        now[0] += timedelta(seconds=30)
        response = bot.receive("timeout-client", "2", "m3")
        self.assertIn(INACTIVITY_DONE, response)
        self.assertIn(WELCOME, response)
        self.assertNotIn("três tipos de aula", response)

    def test_human_handoff_has_no_inactivity_timeout(self):
        now = [datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)]
        bot = CastillaBot(
            JsonlStorage(self.temp_dir.name),
            inactivity_seconds=30,
            clock=lambda: now[0],
        )
        for index, message in enumerate(("Olá", "6", "Maria", "Dúvida"), start=1):
            message_id = f"human-{index}"
            reply = bot.receive("human-client", message, message_id)
            if reply is not None:
                bot.reply_delivered("human-client", message_id)
        self.assertIsNone(bot.inactivity_deadline("human-client"))
        now[0] += timedelta(hours=1)
        self.assertIsNone(bot.receive("human-client", "Ainda aguardando", "human-5"))


if __name__ == "__main__":
    unittest.main()
