# Chatbot Castilla Idiomas

Chatbot em Python para o fluxo de atendimento do Castilla Idiomas Brasília. O
núcleo não depende de uma plataforma específica e pode ser conectado depois ao
WhatsApp, Telegram ou a um site.

## Executar

Requer Python 3.10 ou superior.

```powershell
python -m castilla_bot.cli
```

Digite `MENU` a qualquer momento para voltar ao início, `ATENDENTE` para abrir
um atendimento humano e `SAIR` para fechar a demonstração.

## Testes

```powershell
python -m unittest discover -s tests -v
```

## Dados gerados

As solicitações são gravadas em `data/atendimentos.jsonl` e as matrículas em
`data/matriculas.jsonl`. Cada linha é um registro JSON independente.

## Integração com outros canais

Use uma identificação estável do cliente como `session_id` e envie cada texto
recebido para `CastillaBot.handle(session_id, mensagem)`. A string retornada é a
resposta que deve ser enviada ao cliente.

## WhatsApp Business (Cloud API oficial)

1. Crie um aplicativo do tipo **Business** em Meta for Developers e adicione o
   produto **WhatsApp**.
2. No painel de configuração da API, obtenha o token de acesso e o **Phone
   Number ID**. Para produção, use um token permanente de usuário do sistema.
3. Copie `.env.example` para `.env` e preencha os valores. O bot carrega esse
   arquivo automaticamente. O `.env` preenchido não deve ser enviado ao Git.
4. Instale e execute o webhook:

```powershell
python -m pip install -e .
Copy-Item .env.example .env
# Abra o arquivo .env e substitua todos os valores de exemplo pelos dados da Meta.
python -m castilla_bot.whatsapp
```

5. Publique o serviço em uma URL HTTPS. No painel do WhatsApp, configure a URL
   de callback como `https://seu-dominio/webhook`, informe a mesma frase secreta
   de `WHATSAPP_VERIFY_TOKEN` e assine o campo `messages`.

A rota `/` serve como verificação de saúde e `/webhook` recebe/verifica os
eventos. A porta padrão é 8000 e pode ser alterada pela variável `PORT`.
O `Dockerfile` incluído pode ser usado para publicar em uma hospedagem de
contêineres. O webhook valida `X-Hub-Signature-256` usando `META_APP_SECRET`.
