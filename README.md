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
- Duplicate-event protection and retries after observable Meta failures. If Meta delivers a message but the confirmation is lost, the customer may receive it twice.
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
.env.example        # Development environment variable template
constraints.txt     # Pinned dependency versions for Docker and CI
Dockerfile          # Container image for deployment
docker-entrypoint.sh # Prepares the database folder and drops root privileges
fly.toml.example    # Permanent-hosting configuration template
pyproject.toml      # Package metadata and dependencies
```

## Setup and operations

The Portuguese README is the single source for operational instructions, so
the two files do not drift apart. See [README.pt-BR.md](README.pt-BR.md) for:

- what is implemented, what is covered by automated tests, and what has been
  validated on the school's real account (no bot flow so far);
- local installation (`python -m pip install -c constraints.txt -e .`) and the
  terminal demo (`python -m castilla_bot.cli`);
- running the tests (`python -m unittest discover -s tests -v`);
- WhatsApp Cloud API configuration, startup validation, and `.env.example`;
- Cloudflare Quick Tunnel, Docker, and the production runbook in
  [docs/hospedagem-v1.md](docs/hospedagem-v1.md);
- current scope and next steps.

## Security considerations

- Incoming Meta events are authenticated with `X-Hub-Signature-256`.
- Secrets are loaded from environment variables and `.env` is ignored by Git.
- Generated customer records are ignored by Git.
- Production deployments should use HTTPS, restricted access, encrypted
  storage, backups, retention rules, and controls appropriate for Brazil's
  General Data Protection Law (LGPD).
