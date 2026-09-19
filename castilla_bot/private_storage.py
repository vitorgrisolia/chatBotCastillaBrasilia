"""Armazenamento restrito para cadastros da próxima versão do bot.

Não importa nem altera os arquivos JSONL antigos automaticamente.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import sqlite3
import subprocess
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from cryptography.fernet import Fernet


COLLECTIONS = {"pre_matriculas", "matriculas", "atendimentos"}
RETENTION_DAYS = 20


def _private_access(path: Path, *, directory: bool) -> None:
    """Restringe o caminho ao usuário do serviço e administradores do sistema."""
    if os.name != "nt":
        path.chmod(0o700 if directory else 0o600)
        return

    result = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        capture_output=True,
        text=True,
        check=True,
    )
    rows = list(csv.reader(io.StringIO(result.stdout)))
    if len(rows) != 1 or len(rows[0]) != 2:
        raise RuntimeError("Não foi possível identificar o usuário do serviço.")
    user_sid = rows[0][1]
    inheritance = "(OI)(CI)F" if directory else "F"
    grants = [
        f"*{user_sid}:{inheritance}",
        f"*S-1-5-18:{inheritance}",  # SYSTEM
        f"*S-1-5-32-544:{inheritance}",  # Administrators
    ]
    for arguments in (
        ["icacls", str(path), "/grant:r", *grants],
        ["icacls", str(path), "/inheritance:r"],
    ):
        subprocess.run(arguments, capture_output=True, text=True, check=True)


def _received_at(record: dict[str, object]) -> datetime:
    raw = record.get("recebido_em")
    moment = datetime.fromisoformat(str(raw)) if raw else datetime.now(timezone.utc)
    if moment.tzinfo is None:
        raise ValueError("recebido_em precisa informar o fuso horário")
    return moment.astimezone(timezone.utc)


class PrivateSqliteStorage:
    """Guarda registros em SQLite com ACL local e estado de conversão."""

    def __init__(self, db_path: str | Path = "data/private/castilla.sqlite3") -> None:
        self.db_path = Path(db_path).resolve()
        if self.db_path.parent.name.casefold() != "private" or self.db_path.suffix != ".sqlite3":
            raise ValueError("O banco deve ser um arquivo .sqlite3 em uma pasta chamada private")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        _private_access(self.db_path.parent, directory=True)
        self.db_path.touch(exist_ok=True)
        _private_access(self.db_path, directory=False)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS records (
                    id TEXT PRIMARY KEY,
                    collection TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    received_at_unix INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'bot'
                );
                CREATE INDEX IF NOT EXISTS records_retention
                    ON records(collection, status, received_at_unix);
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def load_session(self, session_id: str) -> dict[str, object] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT state FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
        return json.loads(row["state"]) if row else None

    def check_readiness(self) -> None:
        """Falha se o banco ou a tabela de sessões não estiver acessível."""
        with self._connect() as connection:
            connection.execute("SELECT 1 FROM sessions LIMIT 1").fetchone()

    def save_session(self, session_id: str, state: dict[str, object]) -> None:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO sessions (session_id, state, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    state = excluded.state, updated_at = excluded.updated_at""",
                (
                    session_id,
                    json.dumps(state, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def save(self, collection: str, record: dict[str, object]) -> str:
        if collection not in COLLECTIONS:
            raise ValueError("Coleção de dados não permitida")
        moment = _received_at(record)
        status = "pending" if collection == "pre_matriculas" else "not_applicable"
        record_id = uuid4().hex
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO records
                (id, collection, payload, received_at, received_at_unix, status)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    record_id,
                    collection,
                    json.dumps(record, ensure_ascii=False),
                    moment.isoformat(),
                    int(moment.timestamp()),
                    status,
                ),
            )
        return record_id

    @staticmethod
    def _read_legacy(
        collection: str, source: str | Path
    ) -> list[tuple[str, dict[str, object]]]:
        if collection not in COLLECTIONS:
            raise ValueError("Coleção de dados não permitida")
        source_path = Path(source)
        entries: list[tuple[str, dict[str, object]]] = []
        with source_path.open("r", encoding="utf-8") as file:
            for line_number, line in enumerate(file, start=1):
                if not line.strip():
                    continue
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError(f"Registro inválido na linha {line_number}")
                fingerprint = hashlib.sha256(
                    f"{collection}:{line_number}:".encode() + line.encode("utf-8")
                ).hexdigest()
                entries.append(("legacy-" + fingerprint, record))
        return entries

    @staticmethod
    def preview_legacy(collection: str, source: str | Path) -> int:
        """Conta e valida um arquivo antigo sem criar ou alterar o banco."""
        return len(PrivateSqliteStorage._read_legacy(collection, source))

    def import_legacy(self, collection: str, source: str | Path, *, apply: bool = False) -> int:
        """Importa JSONL antigo, sem apagar o original.

        Pré-matrículas antigas exigem revisão humana antes de entrar na retenção.
        """
        entries = self._read_legacy(collection, source)

        if not apply:
            return len(entries)
        inserted = 0
        with self._connect() as connection:
            for record_id, record in entries:
                moment = _received_at(record)
                status = "needs_review" if collection == "pre_matriculas" else "not_applicable"
                cursor = connection.execute(
                    """INSERT OR IGNORE INTO records
                    (id, collection, payload, received_at, received_at_unix, status, source)
                    VALUES (?, ?, ?, ?, ?, ?, 'legacy_jsonl')""",
                    (
                        record_id,
                        collection,
                        json.dumps(record, ensure_ascii=False),
                        moment.isoformat(),
                        int(moment.timestamp()),
                        status,
                    ),
                )
                inserted += cursor.rowcount
        return inserted

    def mark_converted(self, record_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE records SET status = 'converted'
                WHERE id = ? AND collection = 'pre_matriculas'
                AND status IN ('pending', 'needs_review')""",
                (record_id,),
            )
        return cursor.rowcount == 1

    def mark_unconverted(self, record_id: str) -> bool:
        """Libera uma pré-matrícula antiga revisada para a regra de retenção."""
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE records SET status = 'pending'
                WHERE id = ? AND collection = 'pre_matriculas'
                AND status = 'needs_review'""",
                (record_id,),
            )
        return cursor.rowcount == 1

    def retention_candidates(self, *, as_of: datetime | None = None) -> list[str]:
        now = as_of or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("as_of precisa informar o fuso horário")
        cutoff = int((now - timedelta(days=RETENTION_DAYS)).timestamp())
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT id FROM records
                WHERE collection = 'pre_matriculas' AND status = 'pending'
                AND received_at_unix <= ? ORDER BY received_at_unix, id""",
                (cutoff,),
            ).fetchall()
        return [row["id"] for row in rows]

    def purge_candidates(
        self, candidate_ids: list[str], *, as_of: datetime | None = None
    ) -> int:
        """Exclui somente IDs previamente revisados; nunca roda automaticamente."""
        if not candidate_ids:
            return 0
        now = as_of or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("as_of precisa informar o fuso horário")
        cutoff = int((now - timedelta(days=RETENTION_DAYS)).timestamp())
        with self._connect() as connection:
            cursor = connection.executemany(
                """DELETE FROM records
                WHERE id = ? AND collection = 'pre_matriculas' AND status = 'pending'
                AND received_at_unix <= ?""",
                [(record_id, cutoff) for record_id in candidate_ids],
            )
        return cursor.rowcount

    def counts(self) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT collection || ':' || status AS label, COUNT(*) AS count "
                "FROM records GROUP BY collection, status"
            ).fetchall()
        return {row["label"]: row["count"] for row in rows}

    def pre_enrollments(self, *, identify: bool = False) -> list[dict[str, str]]:
        """Lista IDs para revisão; identificação parcial é opcional."""
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT id, received_at, status, payload FROM records
                   WHERE collection = 'pre_matriculas'
                   ORDER BY received_at_unix DESC, id"""
            ).fetchall()
        result = []
        for row in rows:
            item = {
                "id": row["id"],
                "recebido_em": row["received_at"],
                "status": row["status"],
            }
            if identify:
                payload = json.loads(row["payload"])
                first_name = str(payload.get("nome_completo", "")).split(" ")[0]
                cpf_digits = "".join(
                    character for character in str(payload.get("cpf", "")) if character.isdigit()
                )
                item["primeiro_nome"] = first_name
                item["cpf_final"] = cpf_digits[-4:] if len(cpf_digits) == 11 else ""
            result.append(item)
        return result

    def encrypted_backup(self, destination: str | Path, key: bytes | str) -> Path:
        """Cria backup cifrado em outro diretório sem sobrescrever cópias."""
        target = Path(destination).resolve()
        if target.parent == self.db_path.parent:
            raise ValueError("O backup deve ficar fora do diretório do banco")
        if not target.parent.is_dir():
            raise FileNotFoundError("O diretório de backup não existe")
        with self._connect() as source, closing(sqlite3.connect(":memory:")) as snapshot:
            source.backup(snapshot)
            dump = "\n".join(snapshot.iterdump()).encode("utf-8")
        token = Fernet(key).encrypt(dump)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor = os.open(target, flags, 0o600)
        try:
            _private_access(target, directory=False)
            with os.fdopen(descriptor, "wb") as file:
                descriptor = -1
                file.write(token)
                file.flush()
                os.fsync(file.fileno())
        except BaseException:
            if descriptor >= 0:
                os.close(descriptor)
            target.unlink(missing_ok=True)
            raise
        return target

    @staticmethod
    def verify_backup(source: str | Path, key: bytes | str) -> dict[str, int]:
        dump = Fernet(key).decrypt(Path(source).read_bytes()).decode("utf-8")
        with closing(sqlite3.connect(":memory:")) as connection:
            connection.executescript(dump)
            check = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if check != "ok":
                raise ValueError("Backup inválido")
            rows = connection.execute(
                "SELECT collection || ':' || status, COUNT(*) FROM records "
                "GROUP BY collection, status"
            ).fetchall()
        return dict(rows)

    @staticmethod
    def restore_backup(
        source: str | Path, destination: str | Path, key: bytes | str
    ) -> Path:
        """Restaura somente em banco novo, nunca por cima do banco em uso."""
        PrivateSqliteStorage.verify_backup(source, key)
        dump = Fernet(key).decrypt(Path(source).read_bytes()).decode("utf-8")
        target = Path(destination).resolve()
        if target.parent.name.casefold() != "private" or target.suffix != ".sqlite3":
            raise ValueError("Restaure em um arquivo .sqlite3 numa pasta private")
        target.parent.mkdir(parents=True, exist_ok=True)
        _private_access(target.parent, directory=True)
        descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        try:
            _private_access(target, directory=False)
            with closing(sqlite3.connect(target)) as connection:
                connection.executescript(dump)
                if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("Restauração inválida")
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return target
