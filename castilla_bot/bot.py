"""Máquina de estados do fluxo de atendimento."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import os
from threading import RLock
from typing import Any, Callable

from .private_storage import PrivateSqliteStorage
from .storage import JsonlStorage, RecordStorage, SessionStorage
from .validation import normalize_cpf, normalize_email, normalize_whatsapp


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

INACTIVITY_DONE = """⏱️ Atendimento automático encerrado por falta de interação.

Quando quiser continuar, envie uma nova mensagem para iniciar outro atendimento."""

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
    pending_reply: str | None = None
    pending_message_id: str | None = None
    processed_message_ids: list[str] = field(default_factory=list)
    last_activity_at: str | None = None


class PendingDelivery(RuntimeError):
    """Um envio anterior precisa ser confirmado antes de processar outro evento."""


class CastillaBot:
    """Processa uma mensagem por vez e mantém sessões por identificador."""

    def __init__(
        self,
        storage: RecordStorage | None = None,
        session_storage: SessionStorage | None = None,
        inactivity_seconds: float | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if storage is not None:
            self.storage = storage
        else:
            backend = os.getenv("CASTILLA_STORAGE_BACKEND", "jsonl").casefold()
            if os.getenv("CASTILLA_ENV", "development").casefold() == "production" and backend != "sqlite":
                raise RuntimeError("Em produção, CASTILLA_STORAGE_BACKEND deve ser sqlite")
            if backend == "sqlite":
                self.storage = PrivateSqliteStorage(
                    os.getenv("CASTILLA_DB_PATH", "data/private/castilla.sqlite3")
                )
            elif backend == "jsonl":
                self.storage = JsonlStorage()
            else:
                raise ValueError("CASTILLA_STORAGE_BACKEND deve ser jsonl ou sqlite")
        self.sessions: dict[str, Session] = {}
        self.session_storage = session_storage or (
            self.storage if isinstance(self.storage, PrivateSqliteStorage) else None
        )
        configured_timeout = (
            float(os.getenv("CASTILLA_INACTIVITY_SECONDS", "30"))
            if inactivity_seconds is None else inactivity_seconds
        )
        if configured_timeout <= 0:
            raise ValueError("O tempo de inatividade deve ser maior que zero")
        self.inactivity_seconds = configured_timeout
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()

    def _session(self, session_id: str) -> Session | None:
        if self.session_storage is not None:
            saved = self.session_storage.load_session(session_id)
            if saved is not None:
                session = Session(
                    state=saved["state"],
                    data=saved["data"],
                    field_index=saved["field_index"],
                    selected_options=set(saved["selected_options"]),
                    pending_reply=saved.get("pending_reply"),
                    pending_message_id=saved.get("pending_message_id"),
                    processed_message_ids=saved.get("processed_message_ids", []),
                    last_activity_at=saved.get("last_activity_at"),
                )
                self.sessions[session_id] = session
                return session
        return self.sessions.get(session_id)

    def _save_session(self, session_id: str, session: Session) -> None:
        if self.session_storage is not None:
            self.session_storage.save_session(
                session_id,
                {
                    "state": session.state,
                    "data": session.data,
                    "field_index": session.field_index,
                    "selected_options": sorted(session.selected_options),
                    "pending_reply": session.pending_reply,
                    "pending_message_id": session.pending_message_id,
                    "processed_message_ids": session.processed_message_ids,
                    "last_activity_at": session.last_activity_at,
                },
            )

    def receive(self, session_id: str, message: str, message_id: str | None = None) -> str | None:
        """Processa um evento da Meta sem repetir efeitos de um ID já concluído."""
        with self._lock:
            now = self._now()
            session = self._session(session_id)
            if session is not None:
                if message_id and message_id in session.processed_message_ids:
                    return None
                if session.pending_reply is not None:
                    if session.pending_message_id not in (None, message_id):
                        raise PendingDelivery("Aguarde o envio anterior")
                    return session.pending_reply
            expired = session is not None and self._is_inactive(session, now)
            previously_closed = session is not None and session.state == "inactive_closed"
            if session is None or expired or previously_closed:
                session = Session()
                self.sessions[session_id] = session
                reply = (INACTIVITY_DONE + "\n\n" + WELCOME) if expired else WELCOME
            else:
                reply = self._handle_session(session_id, session, message)
                # REINICIAR troca o objeto da sessão.
                session = self.sessions[session_id]
            if session.state != "human_pending":
                session.last_activity_at = now.isoformat()
            else:
                session.last_activity_at = None
            if reply is None:
                self._remember_message(session, message_id)
            else:
                session.pending_reply = reply
                session.pending_message_id = message_id
            self._save_session(session_id, session)
            return reply

    def reply_delivered(self, session_id: str, message_id: str | None = None) -> None:
        """Confirma o envio e libera o processamento da próxima mensagem."""
        with self._lock:
            session = self._session(session_id)
            if session is not None and session.pending_reply is not None:
                if session.pending_message_id != message_id:
                    raise ValueError("ID da mensagem pendente não corresponde")
                self._remember_message(session, message_id)
                session.pending_reply = None
                session.pending_message_id = None
                self._save_session(session_id, session)

    @staticmethod
    def _remember_message(session: Session, message_id: str | None) -> None:
        if message_id and message_id not in session.processed_message_ids:
            session.processed_message_ids.append(message_id)
            del session.processed_message_ids[:-100]

    def start(self, session_id: str) -> str:
        with self._lock:
            session = Session(last_activity_at=self._now().isoformat())
            self.sessions[session_id] = session
            self._save_session(session_id, session)
            return WELCOME

    def handle(self, session_id: str, message: str) -> str | None:
        with self._lock:
            session = self._session(session_id)
            if session is None:
                session = Session()
                self.sessions[session_id] = session
            response = self._handle_session(session_id, session, message)
            if self.sessions[session_id] is session:
                self._save_session(session_id, session)
            return response

    def _handle_session(self, session_id: str, session: Session, message: str) -> str | None:
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
            self._remember_message(session, session.pending_message_id)
            session.pending_reply = None
            session.pending_message_id = None
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
        with self._lock:
            session = self._session(session_id)
            if (
                session is None
                or session.state != "human_pending"
                or message.strip().casefold() != "atendimento finalizado"
            ):
                return False
            session.state = "main"
            session.data = {}
            session.field_index = 0
            session.last_activity_at = None
            self._save_session(session_id, session)
            return True

    def inactivity_deadline(self, session_id: str) -> tuple[str, datetime] | None:
        """Retorna a atividade esperada e o prazo, ou None quando não há temporizador."""
        with self._lock:
            session = self._session(session_id)
            if (
                session is None
                or session.state in {"human_pending", "inactive_closed"}
                or session.last_activity_at is None
            ):
                return None
            activity = self._parse_activity(session.last_activity_at)
            return session.last_activity_at, activity + timedelta(seconds=self.inactivity_seconds)

    def inactivity_is_due(self, session_id: str, expected_activity: str) -> bool:
        with self._lock:
            session = self._session(session_id)
            return bool(
                session is not None
                and session.last_activity_at == expected_activity
                and self._is_inactive(session, self._now())
            )

    def close_for_inactivity(self, session_id: str, expected_activity: str) -> bool:
        """Encerra exatamente a sessão que originou o temporizador."""
        with self._lock:
            session = self._session(session_id)
            if (
                session is None
                or session.last_activity_at != expected_activity
                or not self._is_inactive(session, self._now())
            ):
                return False
            session.state = "inactive_closed"
            session.data = {}
            session.field_index = 0
            session.selected_options.clear()
            session.pending_reply = None
            session.pending_message_id = None
            session.last_activity_at = None
            self._save_session(session_id, session)
            return True

    def _is_inactive(self, session: Session, now: datetime) -> bool:
        if session.state in {"human_pending", "inactive_closed"} or session.last_activity_at is None:
            return False
        activity = self._parse_activity(session.last_activity_at)
        return now >= activity + timedelta(seconds=self.inactivity_seconds)

    @staticmethod
    def _parse_activity(value: str) -> datetime:
        moment = datetime.fromisoformat(value)
        if moment.tzinfo is None:
            raise ValueError("last_activity_at precisa informar o fuso horário")
        return moment.astimezone(timezone.utc)

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None:
            raise ValueError("O relógio precisa informar o fuso horário")
        return now.astimezone(timezone.utc)

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
        if key == "email":
            email = normalize_email(answer)
            if email is None:
                return "E-mail inválido. Confira o endereço e envie novamente."
            answer = email
        elif key == "cpf":
            cpf = normalize_cpf(answer)
            if cpf is None:
                return "CPF inválido. Confira os 11 números e envie novamente."
            answer = cpf
        elif key == "whatsapp":
            whatsapp = normalize_whatsapp(answer)
            if whatsapp is None:
                return "WhatsApp inválido. Envie o número com DDD, por exemplo: (61) 99999-9999."
            answer = whatsapp
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
