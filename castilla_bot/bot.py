"""Máquina de estados do fluxo de atendimento."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .storage import JsonlStorage


WELCOME = """Olá! 👋 Seja bem-vindo ao Castilla Idiomas Brasília!
Como podemos ajudar?

1️⃣ Conhecer o curso
2️⃣ Ver nossa metodologia
3️⃣ Consultar planos e valores
4️⃣ Fazer minha matrícula
5️⃣ Já sou aluno
6️⃣ Falar com um atendente

Digite o número da opção desejada."""

COURSE = """📚 Nosso curso de inglês é 100% on-line, com aulas ao vivo e direto com o professor.

O curso vai do básico ao avançado em aproximadamente 20 meses. Você terá acesso à Plataforma Castilla Online e poderá agendar suas aulas entre 7h e 21h.

Não trabalhamos com videoaulas gravadas.

1️⃣ Conhecer a metodologia
2️⃣ Ver planos e valores
3️⃣ Fazer matrícula
0️⃣ Voltar ao menu"""

METHODOLOGY = """Nossa metodologia possui três tipos de aula:

📘 Gramática
🗣️ Conversação
✍️ Exercícios

Os exercícios ajudam a reforçar o aprendizado e permitem que o aluno avance para o próximo capítulo.

Todas as aulas são on-line e ao vivo com professores.

1️⃣ Ver planos e valores
2️⃣ Fazer matrícula
0️⃣ Voltar ao menu"""

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
✅ Suporte durante o aprendizado

1️⃣ Quero fazer minha matrícula
2️⃣ Falar com um atendente
0️⃣ Voltar ao menu"""

PLAN_SELECTION = """🎓 Ótimo! Vamos iniciar sua matrícula.

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

Digite MENU para visualizar as opções ou ATENDENTE para falar com nossa equipe."""

ENROLLMENT_DONE = """✅ Recebemos suas informações!

Nossa equipe verificará os dados e entrará em contato para concluir sua matrícula.

Obrigado por escolher o Castilla Idiomas Brasília! 📚✨"""

HUMAN_DONE = """Aguarde um momento. Um de nossos atendentes continuará o atendimento assim que estiver disponível."""

PLANS_BY_OPTION = {
    "1": "Conversação — R$ 147,00/mês",
    "2": "Básico — R$ 197,00/mês",
    "3": "Médio — R$ 247,00/mês",
    "4": "Top — R$ 397,00/mês",
}

ENROLLMENT_FIELDS = [
    ("nome_completo", "Nome completo do aluno"),
    ("data_nascimento", "Data de nascimento"),
    ("sexo", "Sexo"),
    ("cpf", "CPF"),
    ("rg", "RG"),
    ("data_emissao_rg", "Data de emissão do RG"),
    ("orgao_emissor", "Órgão emissor"),
    ("cep", "CEP"),
    ("rua", "Rua"),
    ("numero", "Número"),
    ("complemento", "Complemento (digite NÃO se não houver)"),
    ("bairro", "Bairro"),
    ("cidade", "Cidade"),
    ("whatsapp", "WhatsApp"),
    ("celular", "Celular"),
    ("telefone", "Telefone (digite NÃO se não houver)"),
    ("email", "E-mail"),
    ("responsavel_nome", "Nome completo do responsável financeiro"),
    ("responsavel_cpf", "CPF do responsável financeiro"),
    ("responsavel_telefone", "Telefone/WhatsApp do responsável financeiro"),
    ("responsavel_email", "E-mail do responsável financeiro"),
    ("tipo_horario", "Deseja aulas em horário REGULAR ou FLEXÍVEL?"),
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


class CastillaBot:
    """Processa uma mensagem por vez e mantém sessões por identificador."""

    def __init__(self, storage: JsonlStorage | None = None) -> None:
        self.storage = storage or JsonlStorage()
        self.sessions: dict[str, Session] = {}

    def start(self, session_id: str) -> str:
        self.sessions[session_id] = Session()
        return WELCOME

    def handle(self, session_id: str, message: str) -> str:
        session = self.sessions.setdefault(session_id, Session())
        answer = message.strip()
        normalized = answer.casefold()

        if normalized == "menu":
            self.sessions[session_id] = Session()
            return WELCOME
        if normalized == "atendente":
            return self._start_human(session)
        if not answer:
            return INVALID

        handlers = {
            "main": self._main,
            "course": self._course,
            "methodology": self._methodology,
            "plans": self._plans,
            "plan_selection": self._plan_selection,
            "enrollment": self._enrollment,
            "student": self._student,
            "human_name": self._human_name,
            "human_subject": self._human_subject,
            "finished": self._finished,
        }
        return handlers[session.state](session, answer)

    def _main(self, session: Session, answer: str) -> str:
        routes = {
            "1": ("course", COURSE),
            "2": ("methodology", METHODOLOGY),
            "3": ("plans", PLANS),
            "4": ("plan_selection", PLAN_SELECTION),
            "5": ("student", STUDENT_MENU),
        }
        if answer == "6":
            return self._start_human(session)
        return self._route(session, answer, routes)

    def _course(self, session: Session, answer: str) -> str:
        return self._route(session, answer, {
            "1": ("methodology", METHODOLOGY),
            "2": ("plans", PLANS),
            "3": ("plan_selection", PLAN_SELECTION),
            "0": ("main", WELCOME),
        })

    def _methodology(self, session: Session, answer: str) -> str:
        return self._route(session, answer, {
            "1": ("plans", PLANS),
            "2": ("plan_selection", PLAN_SELECTION),
            "0": ("main", WELCOME),
        })

    def _plans(self, session: Session, answer: str) -> str:
        if answer == "2":
            return self._start_human(session)
        return self._route(session, answer, {
            "1": ("plan_selection", PLAN_SELECTION),
            "0": ("main", WELCOME),
        })

    def _plan_selection(self, session: Session, answer: str) -> str:
        if answer not in PLANS_BY_OPTION:
            return INVALID
        session.state = "enrollment"
        session.field_index = 0
        session.data = {"plano": PLANS_BY_OPTION[answer]}
        return self._field_prompt(session)

    def _enrollment(self, session: Session, answer: str) -> str:
        key, _ = ENROLLMENT_FIELDS[session.field_index]
        session.data[key] = answer
        session.field_index += 1
        if session.field_index < len(ENROLLMENT_FIELDS):
            return self._field_prompt(session)

        record = self._record(session.data)
        self.storage.save("matriculas", record)
        session.state = "finished"
        return ENROLLMENT_DONE

    def _student(self, session: Session, answer: str) -> str:
        if answer == "0":
            session.state = "main"
            return WELCOME
        if answer not in STUDENT_SUBJECTS:
            return INVALID
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
        session.state = "finished"
        return HUMAN_DONE

    @staticmethod
    def _finished(session: Session, answer: str) -> str:
        del session, answer
        return "Atendimento finalizado. Digite MENU para iniciar uma nova conversa."

    @staticmethod
    def _route(
        session: Session,
        answer: str,
        routes: dict[str, tuple[str, str]],
    ) -> str:
        destination = routes.get(answer)
        if destination is None:
            return INVALID
        session.state, response = destination
        return response

    @staticmethod
    def _field_prompt(session: Session) -> str:
        _, label = ENROLLMENT_FIELDS[session.field_index]
        current = session.field_index + 1
        total = len(ENROLLMENT_FIELDS)
        return f"Dados para matrícula ({current}/{total})\n{label}:"

    @staticmethod
    def _record(data: dict[str, Any]) -> dict[str, Any]:
        return {
            **data,
            "recebido_em": datetime.now(timezone.utc).isoformat(),
        }

