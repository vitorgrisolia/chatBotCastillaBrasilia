# CastillaBot — WhatsApp Customer Service Chatbot

[English](README.md) | [Português (Brasil)](README.pt-BR.md)

CastillaBot is a Python chatbot built for Castilla Idiomas Brasília, a Brazilian
language school. It automates the first stage of customer service on WhatsApp,
presents course information and pricing, collects pre-enrollment requests, and
routes customers to a human agent when necessary.

The conversational core is independent from WhatsApp. It can be reused in a
terminal, website, Telegram integration, or any channel capable of providing a
stable customer ID and exchanging text messages.

## Project highlights

- Rule-based conversation flow implemented as a finite-state machine.
- Main-menu options disappear after selection; unselected options remain visible with their original numbers.
- Separate sessions for multiple concurrent customers.
- Course, methodology, pricing, student support, and human handoff flows.
- Pre-enrollment collection with the selected plan and price.
- CPF, email-format, and Brazilian WhatsApp-number validation.
- Official WhatsApp Cloud API integration through a Flask webhook.
- Meta webhook verification and HMAC-SHA256 request signature validation.
- Private SQLite persistence for records and sessions in production mode.
- Duplicate-event protection and safe retries after observable Meta failures.
- Automatic-flow closure after 30 seconds without customer interaction.
- Controlled JSONL migration, encrypted backups, and 20-day retention.
- Dependency injection for isolated bot and webhook testing.
- Docker support and a production WSGI configuration with Gunicorn.
- Automated tests covering the conversation and WhatsApp webhook behavior.

## Conversation flow

```text
Welcome menu (remaining options after each selection)
├── Course information
├── Methodology
├── Plans and pricing
├── Pre-enrollment
│   ├── Plan selection
│   ├── Customer details
│   └── Human follow-up confirmation
├── Student support
└── Human agent handoff
```

The pre-enrollment flow collects the customer's full name, address, email, CPF
(Brazilian taxpayer ID), and WhatsApp number. After the final answer, the bot
confirms the chosen plan and price and informs the customer that a team member
will contact them to complete the enrollment.
The bot checks CPF digits, email syntax, and Brazilian WhatsApp numbers with an
area code before advancing. These checks do not verify ownership of the contacts.

## How it works

`CastillaBot` processes one message at a time. Each customer is identified by a
`session_id`, which maps to a `Session` held in memory in legacy JSONL mode or
persisted in private SQLite storage when the `sqlite` backend is active, containing:

- the current conversation state;
- the data already collected;
- the index of the next requested field;
- the main-menu options already selected.

The active state selects the appropriate handler for each incoming message. The
handler validates the menu option, updates the session, and returns the next
text response. Completed pre-enrollments and human-support requests are written
to JSONL in development mode or to private SQLite storage in production mode.

For WhatsApp, Meta sends events to the Flask webhook. The application verifies
the request signature, extracts incoming text messages, uses the sender's phone
number as the session identifier, runs the conversational core, and sends the
reply through the Graph API.

During the automated flow, every customer message resets a 30-second inactivity
timer. When it expires, the bot sends one closure notice, clears the session,
and starts a new service on the customer's next message. The timer is disabled
after human handoff, which still ends only when the attendant completes it.

After handoff, the bot sends one confirmation and stays silent, including for
`MENU` and `REINICIAR`. If the school's number uses WhatsApp Business App and
Cloud API coexistence and subscribes to `smb_message_echoes`, the attendant can
write `atendimento finalizado` in that customer's WhatsApp conversation. The
webhook receives the business-app message echo and resumes the bot. A customer
sending the same phrase cannot release it. Without coexistence and that event,
messages typed in the app do not reach this webhook; an attendant interface
would need to use the protected `POST /operator/complete` endpoint instead.

`MENU` shows only the remaining options. `REINICIAR` starts a fresh conversation
with all options available again. A pre-enrollment option is removed only after
the customer completes the form; cancelling it with `MENU` keeps it available.

## Technology stack

- Python 3.10+
- Flask
- Requests
- python-dotenv
- Gunicorn on Linux deployments
- Meta WhatsApp Cloud API
- Python `unittest`
- Docker

## Project structure

```text
castilla_bot/
├── bot.py              # Conversation states, timer, menus, and business rules
├── cli.py              # Local terminal interface
├── private_storage.py  # Private SQLite, backup, migration, and retention
├── privacy_admin.py    # Local data-administration commands
├── storage.py          # Legacy JSONL persistence for development
├── validation.py       # CPF, email, and WhatsApp validation
├── whatsapp.py         # Flask webhook and Meta Graph API client
└── __init__.py
tests/
├── test_bot.py
├── test_private_storage.py
├── test_validation.py
└── test_whatsapp.py
.github/workflows/ci.yml # Automated tests on GitHub
.env.exemple        # Environment variable template
Dockerfile          # Container image for deployment
fly.toml.example    # Permanent-hosting configuration template
pyproject.toml      # Package metadata and dependencies
```

## Run locally

### Requirements

- Python 3.10 or later
- Git

Clone the repository and enter the project directory:

```powershell
git clone https://github.com/vitorgrisolia/chatBtoCastillaBrasilia.git
cd chatBtoCastillaBrasilia
```

Create and activate a virtual environment on Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install the project:

```powershell
python -m pip install --upgrade pip
python -m pip install -e .
```

Start the terminal demonstration:

```powershell
python -m castilla_bot.cli
```

During the demonstration, enter `MENU` to return to the beginning, `ATENDENTE`
to request human support, or `SAIR` to close the application.

## Run the tests

```powershell
python -m unittest discover -s tests -v
```

The project has 43 automated cases covering menus, invalid input, contact
validation, private storage, migration, backup, retention, duplicate events,
Meta failures, inactivity timeout, human handoff, and restart behavior with
persistent sessions. Continuous integration runs them on Windows and Linux.

## Database and customer-data protection

Production mode stores records and sessions in
`data/private/castilla.sqlite3`. The private directory has restricted
permissions and is excluded from Git because it contains personal information.

Legacy JSONL files remain available after migration for review and recovery.
Do not delete them until record counts, an encrypted backup, and a restore have
all been verified. Imported pre-enrollments start as `needs_review`; after
review, they can be marked converted or unconverted. Only unconverted records
enter the school's 20-day retention process.

Administrative commands create and verify encrypted backups, never overwrite
an existing backup, and are not exposed through the webhook. Read the
[data-protection plan](docs/protecao-de-dados-v1.md) (in Portuguese) before
migrating records, changing statuses, or applying retention.

## WhatsApp Business setup

This project uses Meta's official WhatsApp Cloud API.

1. Create a **Business** application in Meta for Developers and add the
   **WhatsApp** product.
2. Configure a WhatsApp Business Account and phone number.
3. Obtain an access token, the **Phone Number ID**, and the Meta application
   secret. A permanent system-user token is recommended for production.
4. Copy the environment template:

```powershell
Copy-Item .env.exemple .env
```

5. Fill `.env` with the values from Meta:

```dotenv
WHATSAPP_VERIFY_TOKEN=create-your-own-secret-phrase
WHATSAPP_ACCESS_TOKEN=your-meta-access-token
WHATSAPP_PHONE_NUMBER_ID=your-whatsapp-phone-number-id
META_APP_SECRET=your-meta-application-secret
META_GRAPH_API_VERSION=v23.0
OPERATOR_TOKEN=create-a-long-random-secret-here
CASTILLA_ENV=production
CASTILLA_STORAGE_BACKEND=sqlite
CASTILLA_DB_PATH=data/private/castilla.sqlite3
CASTILLA_INACTIVITY_SECONDS=30
CASTILLA_BACKUP_KEY=your-44-character-fernet-key
```

Never commit the populated `.env` file or expose its values in screenshots,
logs, or documentation. The Fernet key ends with `=`, must not contain extra
spaces, and should be stored separately from backup files.

6. For development without Docker, start the webhook directly:

```powershell
python -m castilla_bot.whatsapp
```

Normal container execution is documented in [Docker](#docker). Do not run the
Python webhook and the container at the same time.

The default port is `8000`. It can be changed through the `PORT` environment
variable. `GET /` checks the process, `GET /ready` checks database access, and
`GET /webhook` and `POST /webhook` verify and receive Meta events. Production
mode (`CASTILLA_ENV=production`) refuses legacy JSONL storage.

To close service from WhatsApp Business itself, set up App/Cloud API
coexistence and subscribe the webhook to `smb_message_echoes`. The attendant
must send the phrase in the customer's conversation from the school's number.
The bot sends no reply on completion; it waits for the customer's next message.
Verify that Meta delivers this event for your account before relying on it.

As an alternative for an integrated attendant interface, call
`POST /operator/complete` with `Authorization: Bearer <OPERATOR_TOKEN>` and this
JSON body:

```json
{"customer_phone":"5561999999999","message":"atendimento finalizado"}
```

The phone number must match the identifier received by the webhook. This route
does not message the customer; it only resumes the bot for the next customer
message. Without `OPERATOR_TOKEN`, the route is disabled.

With `CASTILLA_STORAGE_BACKEND=sqlite`, sessions are also stored in the private
database, so restarting a single bot process does not release pending handoffs.
The legacy `jsonl` mode still keeps sessions only in memory and must not pass
the restart acceptance test. Keep one process (as in the Dockerfile); multiple
processes need additional coordination.

See the [human handoff test procedure](docs/teste-passagem-atendente.md) before
enabling this flow in production.
See the [critical 1.0 release criteria](docs/criterios-lancamento-v1.md).

## Expose the local webhook with Cloudflare Tunnel

A Cloudflare Quick Tunnel provides a temporary HTTPS URL for development and
demonstrations. Its `trycloudflare.com` address changes whenever the tunnel is
restarted and should not be used as a production endpoint. First keep exactly
one bot instance running — either the container or direct Python execution —
and confirm that `http://127.0.0.1:8000/ready` returns `ready`.

In a second PowerShell window, check whether `cloudflared` is available:

```powershell
cloudflared --version
```

If Windows does not recognize the command, use the executable's full path:

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" --version
```

Start the tunnel with HTTP/2:

```powershell
cloudflared tunnel --protocol http2 --url http://localhost:8000
```

Alternatively, use the full path:

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --protocol http2 --url http://localhost:8000
```

Cloudflare will display an address similar to:

```text
https://random-words.trycloudflare.com
```

Configure the following callback URL in Meta:

```text
https://random-words.trycloudflare.com/webhook
```

Use the exact value from `WHATSAPP_VERIFY_TOKEN` as the verification token.
Subscribe to `messages` and, to recognize `atendimento finalizado` typed in the
school's WhatsApp Business app, also confirm `smb_message_echoes`. The container
and tunnel must remain active during local testing.

Common issues:

- **`cloudflared` is not recognized:** reopen PowerShell or use the full path.
- **HTTP 502:** confirm that either the container or the Python webhook is
  responding on port `8000`.
- **DNS timeout or connection failure:** keep `--protocol http2`, disable the
  VPN for the test, and verify outbound firewall access.
- **Meta cannot validate the webhook:** check the `/webhook` suffix and ensure
  the verification token has no extra spaces.

## Docker

Build the image after configuring the required environment variables:

```powershell
docker build -t castilla-bot .
```

The database must remain outside the disposable container. Mount the project's
`data` directory before starting it:

```powershell
$castillaDataDir = (Resolve-Path ".\data").Path

docker run --rm --name castilla-bot `
  -p 8000:8000 `
  --env-file ".env" `
  --mount "type=bind,source=$castillaDataDir,target=/app/data" `
  castilla-bot
```

Without the mount, SQLite would live inside the container and be lost when the
container is removed. The container runs Gunicorn with one worker and exposes
port `8000`. Do not run `python -m castilla_bot.whatsapp` at the same time.

Check readiness from another PowerShell window:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/ready"
```

## Current scope and next steps

The main flow, private SQLite storage, validation, duplicate-event protection,
observable-failure handling, and inactivity timer are implemented. The
remaining development work for version 1.0 is:

- a restricted dashboard for bot, database, webhook, and Meta-failure health;
- restoring automatic timers after a container restart;
- an administrative panel for pre-enrollments and support requests;
- structured logs, external alerts, and delivery-status monitoring;
- an operational backup, restore, and retention routine with an audit trail;
- full testing with the school's real account, then version and changelog updates.

Permanent hosting and a stable HTTPS endpoint remain operational requirements
for replacing the Quick Tunnel in production.

## Security considerations

- Incoming Meta events are authenticated with `X-Hub-Signature-256`.
- Secrets are loaded from environment variables and `.env` is ignored by Git.
- Generated customer records are ignored by Git.
- Production deployments should use HTTPS, restricted access, encrypted
  storage, backups, retention rules, and controls appropriate for Brazil's
  General Data Protection Law (LGPD).
