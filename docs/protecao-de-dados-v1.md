# Proteção de dados — preparação da versão 1.0

Este documento descreve a primeira camada técnica de proteção. Não substitui a
definição jurídica das finalidades e prazos de guarda da escola.

## Decisões da escola

- O CPF continua necessário na pré-matrícula. O bot valida os dígitos e guarda
  somente os 11 números, sem pontuação.
- Pré-matrículas **não convertidas** podem ser excluídas após **20 dias** do
  recebimento. Esse prazo foi escolhido pela escola, não é um prazo imposto pela
  ANPD.
- Pré-matrículas convertidas em matrícula não entram nessa exclusão. O prazo de
  guarda da matrícula definitiva e das solicitações de atendimento humano ainda
  precisa ser definido separadamente.

## Controles preparados

- O armazenamento `PrivateSqliteStorage` usa uma pasta `private` dedicada. No
  Windows, remove permissões herdadas e permite acesso somente ao usuário do
  serviço, ao SYSTEM e aos administradores; em Linux, usa permissões `700` para
  a pasta e `600` para o banco.
- O bot **continua usando os arquivos JSONL atuais por padrão**. O banco novo é
  ativado somente com `CASTILLA_STORAGE_BACKEND=sqlite`. Isso evita troca de
  armazenamento sem migrar os dados existentes.
- A importação dos JSONL é explícita e não apaga os arquivos de origem. As
  pré-matrículas antigas entram como `needs_review`, fora da exclusão dos 20
  dias, até um responsável confirmar se viraram matrícula.
- O relatório de retenção mostra apenas IDs e contagens. A exclusão exige uma
  opção explícita e faz antes um backup cifrado e verificado.
- O backup usa Fernet. A chave (`CASTILLA_BACKUP_KEY`) deve ficar fora do Git e
  ser guardada separadamente das cópias. Sem a chave, não há recuperação.

## Comandos locais

Os comandos abaixo devem ser executados somente por um administrador no servidor
do bot. Eles não estão disponíveis no webhook público.

```powershell
python -m castilla_bot.privacy_admin status
python -m castilla_bot.privacy_admin migrate
python -m castilla_bot.privacy_admin list-pre-enrollments
python -m castilla_bot.privacy_admin retention
```

`migrate` sem `--apply` apenas conta os registros. `migrate --apply` copia os
JSONL para o banco, sem apagar os originais. Após revisão, o responsável pode
usar `mark-converted <ID>` ou `mark-unconverted <ID>`.
`list-pre-enrollments --identify` mostra, apenas no terminal local, o primeiro
nome e os quatro últimos dígitos do CPF para ajudar na identificação; sem essa
opção, a lista mostra apenas ID, data e estado.

Para backup, configure uma chave Fernet em `CASTILLA_BACKUP_KEY` e escolha um
diretório de backup já criado, diferente da pasta do banco:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Guarde o valor gerado em um gerenciador de segredos; não o cole em mensagens ou
documentos compartilhados. A chave não deve ficar junto com os backups.

```powershell
python -m castilla_bot.privacy_admin backup D:\BackupsProtegidos\castilla-2026-09-18.cbackup
python -m castilla_bot.privacy_admin verify-backup D:\BackupsProtegidos\castilla-2026-09-18.cbackup
python -m castilla_bot.privacy_admin restore-backup D:\BackupsProtegidos\castilla-2026-09-18.cbackup D:\Restauracao\private\castilla.sqlite3
```

O arquivo de backup é cifrado, mas ainda precisa ser guardado em local seguro,
separado do computador principal. O cronograma de backups, a retenção das
cópias e um teste periódico de restauração ainda precisam ser definidos para
produção. A restauração só cria um banco novo e nunca sobrescreve o banco em
uso.

Depois de revisar os candidatos e configurar a chave, a exclusão pode ser
executada manualmente com `retention --apply --backup-output <arquivo>`. Este
comando não é agendado automaticamente. Os dados excluídos do banco podem
continuar presentes em backups antigos e nos JSONL originais; ambos precisam
de uma política de descarte antes do lançamento da versão 1.0.

## Antes de ativar no bot real

1. Fazer cópia segura dos arquivos atuais e confirmar que pode ser restaurada.
2. Importar os JSONL com `migrate --apply`, revisar a contagem e classificar as
   pré-matrículas antigas.
3. Decidir quem terá acesso operacional ao banco e às cópias, e restringir ou
   eliminar os JSONL antigos **somente depois de conferir a migração**.
4. Configurar `CASTILLA_STORAGE_BACKEND=sqlite`, reiniciar o serviço em janela
   combinada e testar uma pré-matrícula real controlada.
5. Definir a rotina de backup e retenção das cópias antes de automatizar a
   exclusão de cadastros.

Referência: [Guia de Segurança da Informação da ANPD para agentes de pequeno
porte](https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/guia-orientativo-sobre-seguranca-da-informacao-para-agentes-de-tratamento-de-pequeno-porte).
