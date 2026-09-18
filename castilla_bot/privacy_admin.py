"""Comandos locais de administração de dados; nunca expõem cadastros no webhook."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .private_storage import COLLECTIONS, PrivateSqliteStorage, RETENTION_DAYS


def _backup_key() -> str:
    key = os.getenv("CASTILLA_BACKUP_KEY", "")
    if not key:
        raise SystemExit("Configure CASTILLA_BACKUP_KEY antes de criar ou verificar backups.")
    return key


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    load_dotenv(override=False)
    parser = argparse.ArgumentParser(description="Administração local dos dados do Castilla Bot")
    parser.add_argument(
        "--db",
        default=os.getenv("CASTILLA_DB_PATH", "data/private/castilla.sqlite3"),
        help="Arquivo SQLite na pasta private",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Mostra contagens, sem dados pessoais")
    listing = commands.add_parser("list-pre-enrollments", help="Lista IDs para revisão")
    listing.add_argument("--identify", action="store_true", help="Mostra primeiro nome e CPF final")
    migration = commands.add_parser("migrate", help="Pré-visualiza ou importa JSONL antigo")
    migration.add_argument("--source-dir", default="data")
    migration.add_argument("--apply", action="store_true")
    converted = commands.add_parser("mark-converted", help="Marca pré-matrícula como matriculada")
    converted.add_argument("record_id")
    unconverted = commands.add_parser(
        "mark-unconverted", help="Confirma que uma pré-matrícula antiga não virou matrícula"
    )
    unconverted.add_argument("record_id")
    retention = commands.add_parser("retention", help="Mostra pendências com mais de 20 dias")
    retention.add_argument("--apply", action="store_true", help="Exclui após backup cifrado")
    retention.add_argument("--backup-output", type=Path)
    backup = commands.add_parser("backup", help="Cria cópia cifrada em outro diretório")
    backup.add_argument("output", type=Path)
    verify = commands.add_parser("verify-backup", help="Testa descriptografia e integridade")
    verify.add_argument("source", type=Path)
    restore = commands.add_parser("restore-backup", help="Restaura em um banco novo")
    restore.add_argument("source", type=Path)
    restore.add_argument("destination", type=Path)
    args = parser.parse_args()

    if args.command == "verify-backup":
        counts = PrivateSqliteStorage.verify_backup(args.source, _backup_key())
        print("Backup íntegro:", counts)
        return
    if args.command == "restore-backup":
        target = PrivateSqliteStorage.restore_backup(
            args.source, args.destination, _backup_key()
        )
        print("Backup restaurado em um banco novo:", target)
        return
    if args.command == "migrate" and not args.apply:
        source_dir = Path(args.source_dir)
        for collection in sorted(COLLECTIONS):
            source = source_dir / f"{collection}.jsonl"
            if source.is_file():
                count = PrivateSqliteStorage.preview_legacy(collection, source)
                print(f"{collection}: {count} registro(s) encontrado(s); nada importado")
        return

    storage = PrivateSqliteStorage(args.db)
    if args.command == "status":
        print("Registros:", storage.counts())
        print(f"Pré-matrículas pendentes há {RETENTION_DAYS} dias ou mais:",
              len(storage.retention_candidates()))
    elif args.command == "list-pre-enrollments":
        for item in storage.pre_enrollments(identify=args.identify):
            print(item)
    elif args.command == "migrate":
        source_dir = Path(args.source_dir)
        for collection in sorted(COLLECTIONS):
            source = source_dir / f"{collection}.jsonl"
            if source.is_file():
                count = storage.import_legacy(collection, source, apply=args.apply)
                action = "importados" if args.apply else "encontrados; nada importado"
                print(f"{collection}: {count} {action}")
    elif args.command == "mark-converted":
        if not storage.mark_converted(args.record_id):
            raise SystemExit("ID não encontrado ou já concluído.")
        print("Pré-matrícula marcada como convertida.")
    elif args.command == "mark-unconverted":
        if not storage.mark_unconverted(args.record_id):
            raise SystemExit("ID não encontrado ou não aguardava revisão.")
        print("Pré-matrícula antiga incluída na regra de retenção.")
    elif args.command == "backup":
        target = storage.encrypted_backup(args.output, _backup_key())
        PrivateSqliteStorage.verify_backup(target, _backup_key())
        print("Backup cifrado criado e verificado:", target)
    elif args.command == "retention":
        candidates = storage.retention_candidates()
        print(f"Pré-matrículas pendentes com {RETENTION_DAYS} dias ou mais:", len(candidates))
        if not args.apply or not candidates:
            return
        if args.backup_output is None:
            raise SystemExit("Para excluir, informe --backup-output e uma chave de backup.")
        key = _backup_key()
        target = storage.encrypted_backup(args.backup_output, key)
        PrivateSqliteStorage.verify_backup(target, key)
        print("Backup criado e verificado:", target)
        print("Registros excluídos:", storage.purge_candidates(candidates))


if __name__ == "__main__":
    main()
