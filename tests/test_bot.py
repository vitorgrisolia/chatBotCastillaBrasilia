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

    def test_main_navigation_and_global_menu(self):
        self.assertIn("curso de inglês", self.bot.handle(self.session, "1"))
        self.assertIn("três tipos de aula", self.bot.handle(self.session, "1"))
        self.assertEqual(self.bot.handle(self.session, "MENU"), WELCOME)

    def test_invalid_option(self):
        self.assertEqual(self.bot.handle(self.session, "99"), INVALID)

    def test_human_service_is_saved(self):
        self.bot.handle(self.session, "6")
        self.bot.handle(self.session, "Maria")
        response = self.bot.handle(self.session, "Quero tirar uma dúvida")
        self.assertIn("atendentes", response)
        path = Path(self.temp_dir.name) / "atendimentos.jsonl"
        record = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(record["nome"], "Maria")
        self.assertEqual(record["assunto"], "Quero tirar uma dúvida")

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
