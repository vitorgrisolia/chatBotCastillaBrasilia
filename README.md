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
Welcome menu
├── Course information
│   ├── Methodology
│   ├── Plans and pricing
│   └── Pre-enrollment
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

## How it works

`CastillaBot` processes one message at a time. Each customer is identified by a
`session_id`, which maps to an in-memory `Session` containing:

- the current conversation state;
- the data already collected;
- the index of the next requested field.

The active state selects the appropriate handler for each incoming message. The
handler validates the menu option, updates the session, and returns the next
text response. Completed pre-enrollments and human-support requests are written
as independent JSON objects in JSONL files.

For WhatsApp, Meta sends events to the Flask webhook. The application verifies
the request signature, extracts incoming text messages, uses the sender's phone
number as the session identifier, runs the conversational core, and sends the
reply through the Graph API.

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
```

Never commit the populated `.env` file or expose its values in screenshots,
logs, or documentation.

6. Start the webhook:

```powershell
python -m castilla_bot.whatsapp
```

The default port is `8000`. It can be changed through the `PORT` environment
variable. `GET /` is the health endpoint, while `GET /webhook` and
`POST /webhook` verify and receive Meta events.

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

The container runs Gunicorn with two workers and exposes port `8000`.

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
