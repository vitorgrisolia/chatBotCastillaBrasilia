import json
import tempfile
import unittest
from pathlib import Path

from castilla_bot.bot import CastillaBot, INVALID, PRE_ENROLLMENT_FIELDS, WELCOME
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
            response = self.bot.handle(self.session, f"resposta-{index}")
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
        self.assertEqual(record["email"], "resposta-2")
        self.assertEqual(record["cpf"], "resposta-3")
        self.assertEqual(record["whatsapp"], "resposta-4")


if __name__ == "__main__":
    unittest.main()
