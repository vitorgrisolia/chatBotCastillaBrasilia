# CastillaBot — Chatbot de atendimento pelo WhatsApp

[English](README.md) | [Português (Brasil)](README.pt-BR.md)

O CastillaBot é um chatbot desenvolvido em Python para o Castilla Idiomas
Brasília, uma escola brasileira de idiomas. Ele automatiza a primeira etapa do
atendimento pelo WhatsApp, apresenta informações sobre o curso e os planos,
recebe solicitações de pré-matrícula e encaminha o cliente para um atendente
quando necessário.

O núcleo de conversação não depende do WhatsApp. Ele pode ser reutilizado em um
terminal, site, integração com Telegram ou qualquer canal capaz de fornecer uma
identificação estável do cliente e trocar mensagens de texto.

## Destaques do projeto

- Fluxo de conversação baseado em regras e implementado como máquina de estados.
- Opções do menu principal desaparecem após serem selecionadas; as demais continuam disponíveis com a mesma numeração.
- Sessões separadas para vários clientes simultâneos.
- Fluxos de curso, metodologia, planos, suporte ao aluno e atendimento humano.
- Coleta de pré-matrícula com o plano e o valor escolhidos.
- Integração com a API oficial WhatsApp Cloud por meio de um webhook Flask.
- Verificação do webhook da Meta e validação de assinatura HMAC-SHA256.
- Persistência em JSON Lines com proteção contra gravações simultâneas.
- Injeção de dependências para testes isolados do bot e do webhook.
- Suporte a Docker e execução em produção com Gunicorn.
- Testes automatizados do fluxo de conversa e da integração com o WhatsApp.

## Fluxo de atendimento

```text
Menu de boas-vindas (opções restantes após cada consulta)
├── Informações sobre o curso
├── Metodologia
├── Planos e valores
├── Pré-matrícula
│   ├── Escolha do plano
│   ├── Dados do cliente
│   └── Confirmação do contato humano
├── Atendimento ao aluno
└── Encaminhamento para atendente
```

A pré-matrícula solicita nome completo, endereço, e-mail, CPF e WhatsApp. Após
a última resposta, o bot confirma o plano e o preço escolhidos e informa que um
atendente entrará em contato para concluir a matrícula.

## Como funciona

O `CastillaBot` processa uma mensagem por vez. Cada cliente é identificado por
um `session_id`, associado a uma `Session` mantida em memória com:

- a etapa atual da conversa;
- os dados já coletados;
- a posição do próximo campo a ser solicitado;
- as opções do menu principal já selecionadas.

O estado atual seleciona a função responsável por tratar cada nova mensagem.
Essa função valida a opção, atualiza a sessão e devolve a próxima resposta. Ao
final, pré-matrículas e solicitações de atendimento são armazenadas como objetos
JSON independentes em arquivos JSONL.

No WhatsApp, a Meta envia eventos ao webhook Flask. A aplicação verifica a
assinatura da requisição, extrai as mensagens de texto, utiliza o telefone do
remetente como identificador da sessão, executa o núcleo de conversação e envia
a resposta pela Graph API.

Após encaminhar o cliente a um atendente, o bot envia uma única confirmação e
permanece em silêncio, inclusive para `MENU` e `REINICIAR`. Se o número da
escola usa a coexistência do WhatsApp Business com a Cloud API e está inscrito
no evento `smb_message_echoes`, o atendente pode escrever `atendimento
finalizado` na própria conversa do cliente no WhatsApp Business. O webhook
recebe a cópia da mensagem enviada pela escola e reativa o bot. A mesma frase
enviada pelo cliente não libera o bot. Sem coexistência e sem esse evento, a
mensagem escrita no aplicativo não chega ao webhook; nesse caso, é necessária
uma interface integrada à rota protegida `POST /operator/complete`.

## Tecnologias utilizadas

- Python 3.10+
- Flask
- Requests
- python-dotenv
- Gunicorn em implantações Linux
- Meta WhatsApp Cloud API
- Python `unittest`
- Docker

## Estrutura do projeto

```text
castilla_bot/
├── bot.py          # Estados da conversa, menus e regras de negócio
├── cli.py          # Interface local de terminal
├── storage.py      # Persistência JSONL segura entre threads
├── whatsapp.py     # Webhook Flask e cliente da Graph API da Meta
└── __init__.py
tests/
├── test_bot.py
└── test_whatsapp.py
.env.exemple        # Modelo das variáveis de ambiente
Dockerfile          # Imagem de contêiner para publicação
pyproject.toml      # Metadados e dependências do pacote
```

## Executar localmente

### Requisitos

- Python 3.10 ou superior
- Git

Clone o repositório e entre na pasta do projeto:

```powershell
git clone https://github.com/vitorgrisolia/chatBtoCastillaBrasilia.git
cd chatBtoCastillaBrasilia
```

Crie e ative um ambiente virtual no Windows:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Instale o projeto:

```powershell
python -m pip install --upgrade pip
python -m pip install -e .
```

Inicie a demonstração no terminal:

```powershell
python -m castilla_bot.cli
```

Durante a demonstração, digite `MENU` para ver as opções ainda não selecionadas,
`REINICIAR` para começar uma nova conversa, `ATENDENTE` para solicitar atendimento
humano ou `SAIR` para encerrar a aplicação. A numeração permanece fixa; uma opção
de pré-matrícula só desaparece após o envio dos dados. Se o usuário voltar ao
menu antes de concluir, ela continua disponível.

## Executar os testes

```powershell
python -m unittest discover -s tests -v
```

Os testes verificam a navegação pelos menus, respostas inválidas, persistência
da pré-matrícula, atendimento humano, validação do webhook, assinaturas dos
eventos, eventos de status e o comportamento da primeira mensagem.

## Dados gerados

Uma camada opcional de banco SQLite privado, revisão de cadastros antigos,
backup cifrado e retenção de pré-matrículas pendentes por 20 dias está em
preparação para a versão 1.0. Ela **não é ativada automaticamente** e não apaga
os arquivos existentes. Veja [Proteção de dados — versão 1.0](docs/protecao-de-dados-v1.md).

A persistência local grava os registros em:

- `data/pre_matriculas.jsonl` para solicitações de pré-matrícula;
- `data/atendimentos.jsonl` para solicitações de atendimento humano.

Cada linha contém um objeto JSON independente em UTF-8. Esses arquivos são
ignorados pelo Git porque podem conter informações pessoais.

## Configurar o WhatsApp Business

O projeto utiliza a API oficial WhatsApp Cloud da Meta.

1. Crie um aplicativo do tipo **Business** no Meta for Developers e adicione o
   produto **WhatsApp**.
2. Configure uma conta do WhatsApp Business e um número de telefone.
3. Obtenha o token de acesso, o **Phone Number ID** e a chave secreta do
   aplicativo. Em produção, recomenda-se um token permanente de usuário do
   sistema.
4. Copie o modelo de variáveis de ambiente:

```powershell
Copy-Item .env.exemple .env
```

5. Preencha o `.env` com os dados fornecidos pela Meta:

```dotenv
WHATSAPP_VERIFY_TOKEN=crie-sua-frase-secreta
WHATSAPP_ACCESS_TOKEN=seu-token-de-acesso-da-meta
WHATSAPP_PHONE_NUMBER_ID=id-do-numero-do-whatsapp
META_APP_SECRET=chave-secreta-do-aplicativo-meta
META_GRAPH_API_VERSION=v23.0
OPERATOR_TOKEN=crie-um-token-longo-e-aleatorio-aqui
```

Nunca envie o `.env` preenchido ao Git nem exponha seus valores em capturas de
tela, logs ou documentos.

6. Inicie o webhook:

```powershell
python -m castilla_bot.whatsapp
```

A porta padrão é `8000` e pode ser alterada pela variável `PORT`. A rota
`GET /` verifica a saúde do serviço; `GET /webhook` e `POST /webhook` verificam
e recebem os eventos da Meta.

Para encerrar pelo próprio WhatsApp Business, configure a coexistência da conta
com a Cloud API e inscreva o webhook no campo `smb_message_echoes`. A frase
deve ser enviada na conversa com o cliente, pelo número da escola. O bot não
envia nenhuma resposta no momento do encerramento; ele aguarda a próxima
mensagem do cliente. Confirme que a Meta entrega esse evento na sua conta antes
de depender desse fluxo.

Como alternativa para uma interface de atendimento integrada, use
`POST /operator/complete` com o cabeçalho
`Authorization: Bearer <OPERATOR_TOKEN>` e este corpo JSON:

```json
{"customer_phone":"5561999999999","message":"atendimento finalizado"}
```

O telefone precisa ser o mesmo identificador recebido no webhook. A rota não
envia mensagem ao cliente; ela apenas reativa o bot para a próxima mensagem.
Sem `OPERATOR_TOKEN`, a rota fica desativada.

As sessões ainda ficam na memória: use um único processo do bot (o Dockerfile
já está configurado assim). Reiniciar o serviço apaga o estado dos atendimentos
em andamento; antes de operar em produção com múltiplos processos, será
necessário persistir as sessões em um armazenamento compartilhado.

## Publicar o webhook local com Cloudflare Tunnel

O Cloudflare Quick Tunnel fornece uma URL HTTPS temporária para desenvolvimento
e demonstrações. O endereço `trycloudflare.com` muda sempre que o túnel é
reiniciado e não deve ser utilizado em produção.

Mantenha o bot em execução na primeira janela do PowerShell:

```powershell
python -m castilla_bot.whatsapp
```

Em uma segunda janela, verifique se o `cloudflared` está disponível:

```powershell
cloudflared --version
```

Se o Windows não reconhecer o comando, utilize o caminho completo:

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" --version
```

Inicie o túnel utilizando HTTP/2:

```powershell
cloudflared tunnel --protocol http2 --url http://localhost:8000
```

Também é possível utilizar o caminho completo:

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --protocol http2 --url http://localhost:8000
```

O Cloudflare exibirá um endereço semelhante a:

```text
https://palavras-aleatorias.trycloudflare.com
```

Configure no painel da Meta a seguinte URL de callback:

```text
https://palavras-aleatorias.trycloudflare.com/webhook
```

Utilize exatamente o valor de `WHATSAPP_VERIFY_TOKEN` como token de verificação
e assine o webhook no campo `messages`. As duas janelas do PowerShell precisam
permanecer abertas durante os testes locais.

Problemas comuns:

- **`cloudflared` não reconhecido:** reabra o PowerShell ou utilize o caminho
  completo do executável.
- **Erro HTTP 502:** confirme que o webhook Python está executando na porta
  `8000`.
- **Timeout de DNS ou falha de conexão:** mantenha `--protocol http2`, desligue
  a VPN durante o teste e confira as permissões de saída do firewall.
- **A Meta não valida o webhook:** confira o sufixo `/webhook` e confirme que o
  token de verificação não possui espaços adicionais.

## Docker

Depois de configurar as variáveis de ambiente, construa e execute o contêiner:

```powershell
docker build -t castilla-bot .
docker run --rm -p 8000:8000 --env-file .env castilla-bot
```

O contêiner utiliza Gunicorn com um processo e expõe a porta `8000`.

## Escopo atual e próximos passos

Esta versão foi mantida propositalmente simples e é adequada para demonstração,
aprendizado e validação inicial do negócio. Antes de ampliar seu uso em
produção, as principais melhorias planejadas são:

- sessões persistentes em PostgreSQL ou Redis;
- banco de dados com criptografia e controle de acesso aos dados dos clientes;
- validação de CPF, e-mail e telefone;
- logs estruturados, monitoramento e acompanhamento de entrega;
- novas tentativas e idempotência nas chamadas da Graph API;
- hospedagem permanente com domínio HTTPS estável;
- painel administrativo para leads e solicitações de atendimento.

## Considerações de segurança

- Os eventos recebidos da Meta são autenticados por `X-Hub-Signature-256`.
- Os segredos são carregados por variáveis de ambiente e o `.env` é ignorado
  pelo Git.
- Os arquivos gerados com dados dos clientes são ignorados pelo Git.
- A implantação em produção deve utilizar HTTPS, acesso restrito, armazenamento
  criptografado, cópias de segurança, regras de retenção e controles adequados à
  Lei Geral de Proteção de Dados (LGPD).
