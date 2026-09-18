"""Máquina de estados do fluxo de atendimento."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .storage import JsonlStorage


MAIN_OPTIONS = {
    "1": "1️⃣ Conhecer o curso",
    "2": "2️⃣ Ver nossa metodologia",
    "3": "3️⃣ Consultar planos e valores",
    "4": "4️⃣ Fazer minha pré-matrícula",
    "5": "5️⃣ Já sou aluno",
    "6": "6️⃣ Falar com um atendente",
}

WELCOME = """Olá! 👋 Seja bem-vindo ao Castilla Idiomas Brasília!
Como podemos ajudar?

""" + "\n".join(MAIN_OPTIONS.values()) + "\n\nDigite o número da opção desejada."

COURSE = """📚 Nosso curso de inglês é 100% on-line, com aulas ao vivo e direto com o professor.

O curso vai do básico ao avançado em aproximadamente 20 meses. Você terá acesso à Plataforma Castilla Online e poderá agendar suas aulas entre 7h e 21h.

Não trabalhamos com videoaulas gravadas."""

METHODOLOGY = """Nossa metodologia possui três tipos de aula:

📘 Gramática
🗣️ Conversação
✍️ Exercícios

Os exercícios ajudam a reforçar o aprendizado e permitem que o aluno avance para o próximo capítulo.

Todas as aulas são on-line e ao vivo com professores."""

PLANS = """📚 Conheça nossos planos:

🥉 Plano Conversação
Horas ilimitadas
💰 R$ 147,00 por mês

🥉 Plano Básico
3 horas de aula por semana
💰 R$ 197,00 por mês

🥈 Plano Médio
Aulas ilimitadas
💰 R$ 247,00 por mês

🥇 Plano Top
Aulas ilimitadas + 1 hora de aula particular por semana
💰 R$ 397,00 por mês

Todos os planos incluem:

✅ Aulas 100% ao vivo
✅ Plataforma para agendamento
✅ Material didático digital
✅ Suporte durante o aprendizado"""

PLAN_SELECTION = """🎓 Ótimo! Vamos iniciar sua pré-matrícula.

Primeiro, informe o plano escolhido:

1️⃣ Conversação — R$ 147,00/mês
2️⃣ Básico — R$ 197,00/mês
3️⃣ Médio — R$ 247,00/mês
4️⃣ Top — R$ 397,00/mês"""

STUDENT_MENU = """Olá! Como podemos ajudar?

1️⃣ Agendamento de aulas
2️⃣ Acesso à plataforma
3️⃣ Material didático
4️⃣ Dúvidas financeiras
5️⃣ Falar com um atendente
0️⃣ Voltar ao menu"""

INVALID = """Não consegui identificar a opção escolhida. 😕

Digite MENU para visualizar as opções restantes ou ATENDENTE para falar com nossa equipe."""

HUMAN_DONE = """✅ Solicitação recebida. Aguarde um momento: um de nossos atendentes continuará a conversa por aqui assim que estiver disponível."""

PLANS_BY_OPTION = {
    "1": "Conversação — R$ 147,00/mês",
    "2": "Básico — R$ 197,00/mês",
    "3": "Médio — R$ 247,00/mês",
    "4": "Top — R$ 397,00/mês",
}

PRE_ENROLLMENT_FIELDS = [
    ("nome_completo", "Nome completo"),
    ("endereco", "Endereço completo"),
    ("email", "E-mail"),
    ("cpf", "CPF"),
    ("whatsapp", "WhatsApp"),
]

STUDENT_SUBJECTS = {
    "1": "Agendamento de aulas",
    "2": "Acesso à plataforma",
    "3": "Material didático",
    "4": "Dúvidas financeiras",
    "5": "Atendimento geral ao aluno",
}


@dataclass
class Session:
    state: str = "main"
    data: dict[str, Any] = field(default_factory=dict)
    field_index: int = 0
    selected_options: set[str] = field(default_factory=set)


class CastillaBot:
    """Processa uma mensagem por vez e mantém sessões por identificador."""

    def __init__(self, storage: JsonlStorage | None = None) -> None:
        self.storage = storage or JsonlStorage()
        self.sessions: dict[str, Session] = {}

    def start(self, session_id: str) -> str:
        self.sessions[session_id] = Session()
        return WELCOME

    def handle(self, session_id: str, message: str) -> str | None:
        session = self.sessions.setdefault(session_id, Session())
        # Durante o atendimento humano, nem comandos do cliente reativam o bot.
        if session.state == "human_pending":
            return None
        answer = message.strip()
        normalized = answer.casefold()

        if normalized == "reiniciar":
            return self.start(session_id)
        if normalized == "menu":
            session.state = "main"
            session.data = {}
            session.field_index = 0
            return self._remaining_menu(session)
        if normalized == "atendente":
            session.selected_options.add("6")
            return self._start_human(session)
        if not answer:
            return INVALID

        handlers = {
            "main": self._main,
            "plan_selection": self._plan_selection,
            "pre_enrollment": self._pre_enrollment,
            "student": self._student,
            "human_name": self._human_name,
            "human_subject": self._human_subject,
        }
        return handlers[session.state](session, answer)

    def attendant_message(self, session_id: str, message: str) -> bool:
        """Reativa o bot somente após o encerramento enviado pelo atendente."""
        session = self.sessions.get(session_id)
        if (
            session is None
            or session.state != "human_pending"
            or message.strip().casefold() != "atendimento finalizado"
        ):
            return False
        session.state = "main"
        session.data = {}
        session.field_index = 0
        return True

    def _main(self, session: Session, answer: str) -> str:
        if answer in session.selected_options:
            return "Você já selecionou essa opção.\n\n" + self._remaining_menu(session)
        information = {"1": COURSE, "2": METHODOLOGY, "3": PLANS}
        if answer in information:
            session.selected_options.add(answer)
            return information[answer] + "\n\n" + self._remaining_menu(session)
        if answer == "4":
            session.state = "plan_selection"
            return PLAN_SELECTION + "\n\nDigite MENU para voltar às opções restantes."
        if answer == "5":
            session.state = "student"
            return STUDENT_MENU
        if answer == "6":
            session.selected_options.add(answer)
            return self._start_human(session)
        return INVALID + "\n\n" + self._remaining_menu(session)

    def _plan_selection(self, session: Session, answer: str) -> str:
        if answer not in PLANS_BY_OPTION:
            return INVALID
        session.state = "pre_enrollment"
        session.field_index = 0
        session.data = {"plano": PLANS_BY_OPTION[answer]}
        return self._field_prompt(session)

    def _pre_enrollment(self, session: Session, answer: str) -> str:
        key, _ = PRE_ENROLLMENT_FIELDS[session.field_index]
        session.data[key] = answer
        session.field_index += 1
        if session.field_index < len(PRE_ENROLLMENT_FIELDS):
            return self._field_prompt(session)

        record = self._record(session.data)
        self.storage.save("pre_matriculas", record)
        session.selected_options.add("4")
        session.state = "main"
        plan = session.data["plano"]
        return f"""✅ Pré-matrícula recebida!

Plano escolhido: {plan}

Seus dados foram registrados. Um atendente entrará em contato pelo WhatsApp ou telefone informado para finalizar seu cadastro e confirmar a matrícula.

Obrigado por escolher o Castilla Idiomas Brasília! 📚✨

{self._remaining_menu(session)}"""

    def _student(self, session: Session, answer: str) -> str:
        if answer == "0":
            session.state = "main"
            return self._remaining_menu(session)
        if answer not in STUDENT_SUBJECTS:
            return INVALID
        session.selected_options.add("5")
        session.data = {"assunto": STUDENT_SUBJECTS[answer]}
        session.state = "human_name"
        return "👩‍💼 Certo! Para encaminhar seu atendimento, informe seu nome:"

    def _start_human(self, session: Session) -> str:
        session.state = "human_name"
        session.data = {}
        return "👩‍💼 Certo! Para encaminhar seu atendimento, informe seu nome:"

    def _human_name(self, session: Session, answer: str) -> str:
        session.data["nome"] = answer
        if "assunto" in session.data:
            return self._save_human(session)
        session.state = "human_subject"
        return "Agora, informe o assunto do atendimento:"

    def _human_subject(self, session: Session, answer: str) -> str:
        session.data["assunto"] = answer
        return self._save_human(session)

    def _save_human(self, session: Session) -> str:
        self.storage.save("atendimentos", self._record(session.data))
        session.state = "human_pending"
        return HUMAN_DONE

    @staticmethod
    def _remaining_menu(session: Session) -> str:
        remaining = [
            label for option, label in MAIN_OPTIONS.items()
            if option not in session.selected_options
        ]
        if not remaining:
            return "Todas as opções foram selecionadas. Digite REINICIAR para começar de novo."
        return (
            "Outras opções disponíveis:\n\n"
            + "\n".join(remaining)
            + "\n\nDigite o número desejado ou REINICIAR para começar de novo."
        )

    @staticmethod
    def _field_prompt(session: Session) -> str:
        _, label = PRE_ENROLLMENT_FIELDS[session.field_index]
        current = session.field_index + 1
        total = len(PRE_ENROLLMENT_FIELDS)
        return f"Dados para pré-matrícula ({current}/{total})\n{label}:"

    @staticmethod
    def _record(data: dict[str, Any]) -> dict[str, Any]:
        return {
            **data,
            "recebido_em": datetime.now(timezone.utc).isoformat(),
        }
