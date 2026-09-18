import json
import os
import subprocess
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet, InvalidToken

from castilla_bot.private_storage import PrivateSqliteStorage, RETENTION_DAYS
from castilla_bot.bot import CastillaBot


class PrivateStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.database = self.root / "private" / "castilla.sqlite3"
        self.storage = PrivateSqliteStorage(self.database)

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def record(moment, cpf="52998224725"):
        return {
            "nome_completo": "Pessoa de teste",
            "cpf": cpf,
            "recebido_em": moment.isoformat(),
        }

    def test_records_are_stored_in_private_database(self):
        record_id = self.storage.save(
            "pre_matriculas", self.record(datetime.now(timezone.utc))
        )
        self.assertTrue(self.database.exists())
        self.assertEqual(len(record_id), 32)
        self.assertEqual(self.storage.counts(), {"pre_matriculas:pending": 1})
        default_listing = self.storage.pre_enrollments()
        self.assertNotIn("primeiro_nome", default_listing[0])
        self.assertNotIn("cpf_final", default_listing[0])
        identified = self.storage.pre_enrollments(identify=True)[0]
        self.assertEqual(identified["primeiro_nome"], "Pessoa")
        self.assertEqual(identified["cpf_final"], "4725")
        self.assertNotIn("52998224725", str(identified))
        if os.name == "nt":
            acl = subprocess.run(
                ["icacls", str(self.database)],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            self.assertNotIn("CodexSandboxUsers", acl)

    def test_legacy_import_is_explicit_idempotent_and_not_purgeable_before_review(self):
        old = datetime.now(timezone.utc) - timedelta(days=30)
        source = self.root / "pre_matriculas.jsonl"
        source.write_text(json.dumps(self.record(old)) + "\n", encoding="utf-8")
        original = source.read_bytes()

        self.assertEqual(self.storage.import_legacy("pre_matriculas", source), 1)
        self.assertEqual(self.storage.counts(), {})
        self.assertEqual(self.storage.import_legacy("pre_matriculas", source, apply=True), 1)
        self.assertEqual(self.storage.import_legacy("pre_matriculas", source, apply=True), 0)
        self.assertEqual(self.storage.counts(), {"pre_matriculas:needs_review": 1})
        self.assertEqual(self.storage.retention_candidates(), [])
        self.assertEqual(source.read_bytes(), original)

    def test_retention_excludes_recent_converted_and_unreviewed_records(self):
        now = datetime(2026, 9, 18, tzinfo=timezone.utc)
        old = now - timedelta(days=RETENTION_DAYS + 1)
        recent = now - timedelta(days=RETENTION_DAYS - 1)
        due_id = self.storage.save("pre_matriculas", self.record(old))
        converted_id = self.storage.save("pre_matriculas", self.record(old, "11144477735"))
        recent_id = self.storage.save("pre_matriculas", self.record(recent))
        self.assertTrue(self.storage.mark_converted(converted_id))

        self.assertEqual(self.storage.retention_candidates(as_of=now), [due_id])
        self.assertEqual(
            self.storage.purge_candidates([due_id, converted_id, recent_id], as_of=now), 1
        )
        self.assertEqual(self.storage.counts(), {
            "pre_matriculas:converted": 1,
            "pre_matriculas:pending": 1,
        })

    def test_legacy_record_must_be_reviewed_before_retention(self):
        old = datetime.now(timezone.utc) - timedelta(days=30)
        source = self.root / "pre_matriculas.jsonl"
        source.write_text(json.dumps(self.record(old)) + "\n", encoding="utf-8")
        self.storage.import_legacy("pre_matriculas", source, apply=True)
        record_id = next(iter(self._record_ids()))

        self.assertTrue(self.storage.mark_unconverted(record_id))
        self.assertIn(record_id, self.storage.retention_candidates())

    def test_backup_is_encrypted_verified_and_never_overwritten(self):
        self.storage.save("pre_matriculas", self.record(datetime.now(timezone.utc)))
        backup_dir = self.root / "backups"
        backup_dir.mkdir()
        destination = backup_dir / "castilla.cbackup"
        key = Fernet.generate_key()

        self.storage.encrypted_backup(destination, key)
        self.assertNotIn(b"52998224725", destination.read_bytes())
        self.assertEqual(
            self.storage.verify_backup(destination, key), {"pre_matriculas:pending": 1}
        )
        with self.assertRaises(InvalidToken):
            self.storage.verify_backup(destination, Fernet.generate_key())
        with self.assertRaises(FileExistsError):
            self.storage.encrypted_backup(destination, key)

        restored = self.root / "restore" / "private" / "restored.sqlite3"
        self.storage.restore_backup(destination, restored, key)
        self.assertEqual(
            PrivateSqliteStorage(restored).counts(), {"pre_matriculas:pending": 1}
        )
        with self.assertRaises(FileExistsError):
            self.storage.restore_backup(destination, restored, key)

    def test_database_directory_must_be_dedicated(self):
        with self.assertRaises(ValueError):
            PrivateSqliteStorage(self.root / "unsafe.sqlite3")

    def test_bot_uses_private_database_only_when_enabled(self):
        other_database = self.root / "another" / "private" / "bot.sqlite3"
        with patch.dict(
            "os.environ",
            {
                "CASTILLA_STORAGE_BACKEND": "sqlite",
                "CASTILLA_DB_PATH": str(other_database),
            },
        ):
            bot = CastillaBot()
        self.assertIsInstance(bot.storage, PrivateSqliteStorage)
        self.assertTrue(other_database.exists())

    def _record_ids(self):
        import sqlite3

        with closing(sqlite3.connect(self.database)) as connection:
            return [row[0] for row in connection.execute("SELECT id FROM records")]


if __name__ == "__main__":
    unittest.main()
