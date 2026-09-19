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
- Official WhatsApp Cloud API integration through a Flask webhook.
- Meta webhook verification and HMAC-SHA256 request signature validation.
- Thread-safe JSON Lines persistence for pre-enrollments and support requests.
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
`session_id`, which maps to a `Session` held in memory by default or persisted
in private SQLite storage when enabled, containing:

- the current conversation state;
- the data already collected;
- the index of the next requested field;
- the main-menu options already selected.

The active state selects the appropriate handler for each incoming message. The
handler validates the menu option, updates the session, and returns the next
text response. Completed pre-enrollments and human-support requests are written
to JSONL by default or to private SQLite storage when enabled.

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
├── bot.py          # Conversation states, menus, and business rules
├── cli.py          # Local terminal interface
├── storage.py      # Thread-safe JSONL persistence
├── whatsapp.py     # Flask webhook and Meta Graph API client
└── __init__.py
tests/
├── test_bot.py
└── test_whatsapp.py
.env.exemple        # Environment variable template
Dockerfile          # Container image for deployment
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

The test suite covers menu navigation, invalid input, pre-enrollment
persistence, human handoff, webhook verification, webhook signatures, status
events, and the first-message behavior.

## Generated data

An optional private SQLite storage layer, legacy-record review, encrypted
backups, and 20-day retention for unconverted pre-enrollments are being
prepared for version 1.0. They are **not enabled automatically** and do not
delete existing files. See the [data-protection plan](docs/protecao-de-dados-v1.md)
(in Portuguese).

The local storage layer writes records to:

- `data/pre_matriculas.jsonl` for pre-enrollment requests;
- `data/atendimentos.jsonl` for human-support requests.

Each line is an independent UTF-8 JSON object. These generated files are
excluded from Git because they may contain personal information.

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
```

Never commit the populated `.env` file or expose its values in screenshots,
logs, or documentation.

6. Start the webhook:

```powershell
python -m castilla_bot.whatsapp
```

The default port is `8000`. It can be changed through the `PORT` environment
variable. `GET /` checks the process and `GET /ready` checks database access
when SQLite is enabled. Production mode (`CASTILLA_ENV=production`) refuses
legacy JSONL storage. `GET /webhook` and
`POST /webhook` verify and receive Meta events.

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
restarted and should not be used as a production endpoint.

Keep the bot running in the first PowerShell window:

```powershell
python -m castilla_bot.whatsapp
```

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

Use the exact value from `WHATSAPP_VERIFY_TOKEN` as the verification token and
subscribe the webhook to the `messages` field. Both PowerShell windows must
remain open during local testing.

Common issues:

- **`cloudflared` is not recognized:** reopen PowerShell or use the full path.
- **HTTP 502:** confirm that the Python webhook is running on port `8000`.
- **DNS timeout or connection failure:** keep `--protocol http2`, disable the
  VPN for the test, and verify outbound firewall access.
- **Meta cannot validate the webhook:** check the `/webhook` suffix and ensure
  the verification token has no extra spaces.

## Docker

Build and run the container after configuring the required environment
variables:

```powershell
docker build -t castilla-bot .
docker run --rm -p 8000:8000 --env-file .env castilla-bot
```

The container runs Gunicorn with one worker and exposes port `8000`.

## Current scope and next steps

This version is intentionally lightweight and suitable for demonstrations,
learning, and initial business validation. Before scaling it for production,
the main planned improvements are:

- persistent session storage, such as PostgreSQL or Redis;
- a database with encryption and access controls for customer data;
- CPF, email, and phone-number validation;
- structured logs, monitoring, and delivery-status tracking;
- retries and idempotency for Graph API requests;
- a permanent deployment and stable HTTPS domain;
- an administrative dashboard for leads and support requests.

## Security considerations

- Incoming Meta events are authenticated with `X-Hub-Signature-256`.
- Secrets are loaded from environment variables and `.env` is ignored by Git.
- Generated customer records are ignored by Git.
- Production deployments should use HTTPS, restricted access, encrypted
  storage, backups, retention rules, and controls appropriate for Brazil's
  General Data Protection Law (LGPD).
