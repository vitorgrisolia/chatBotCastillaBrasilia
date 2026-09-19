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
- Validação de CPF, formato de e-mail e WhatsApp brasileiro com DDD.
- Integração com a API oficial WhatsApp Cloud por meio de um webhook Flask.
- Verificação do webhook da Meta e validação de assinatura HMAC-SHA256.
- Persistência de cadastros e sessões em banco SQLite privado no modo de produção.
- Prevenção de mensagens duplicadas e reenvio seguro após falhas observáveis da Meta.
- Encerramento do atendimento automático após 30 segundos sem interação.
- Migração controlada dos arquivos JSONL, backup cifrado e retenção de 20 dias.
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
CPF, formato do e-mail e número brasileiro de WhatsApp com DDD são validados
antes de avançar. Isso não confirma que o e-mail ou o telefone pertencem ao aluno.

## Como funciona

O `CastillaBot` processa uma mensagem por vez. Cada cliente é identificado por
um `session_id`, associado a uma `Session` mantida em memória no modo JSONL ou
persistida no banco SQLite privado quando o backend `sqlite` está ativo, com:

- a etapa atual da conversa;
- os dados já coletados;
- a posição do próximo campo a ser solicitado;
- as opções do menu principal já selecionadas.

O estado atual seleciona a função responsável por tratar cada nova mensagem.
Essa função valida a opção, atualiza a sessão e devolve a próxima resposta. Ao
final, pré-matrículas e solicitações de atendimento são armazenadas em JSONL
no modo de desenvolvimento ou no banco privado no modo de produção.

No WhatsApp, a Meta envia eventos ao webhook Flask. A aplicação verifica a
assinatura da requisição, extrai as mensagens de texto, utiliza o telefone do
remetente como identificador da sessão, executa o núcleo de conversação e envia
a resposta pela Graph API.

Durante o fluxo automático, cada mensagem do cliente reinicia um temporizador
de 30 segundos. Se não houver nova interação, o bot envia uma única mensagem de
encerramento, limpa aquela sessão e começa um atendimento novo na próxima
mensagem. O temporizador é cancelado ao entrar em atendimento humano: nessa
etapa, o bot continua aguardando o encerramento escrito pelo atendente.

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
├── bot.py              # Estados, menus, temporizador e regras de negócio
├── cli.py              # Interface local de terminal
├── private_storage.py  # SQLite privado, backup, migração e retenção
├── privacy_admin.py    # Administração local e segura dos dados
├── storage.py          # Persistência JSONL legada para desenvolvimento
├── validation.py       # Validação de CPF, e-mail e WhatsApp
├── whatsapp.py         # Webhook Flask e cliente da Graph API da Meta
└── __init__.py
tests/
├── test_bot.py
├── test_private_storage.py
├── test_validation.py
└── test_whatsapp.py
.github/workflows/ci.yml # Testes automáticos no GitHub
.env.exemple        # Modelo das variáveis de ambiente
Dockerfile          # Imagem de contêiner para publicação
fly.toml.example    # Modelo de hospedagem permanente
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

O projeto possui 43 casos automatizados para menus, respostas inválidas,
validação de contatos, banco privado, migração, backup, retenção, mensagens
duplicadas, falhas da Meta, temporizador, passagem ao atendente e reinício com
sessões persistentes. A rotina de integração contínua executa esses testes em
Windows e Linux quando as mudanças são enviadas ao GitHub.

## Banco de dados e proteção dos cadastros

No modo de produção, cadastros e sessões são armazenados em
`data/private/castilla.sqlite3`. O diretório recebe permissões restritas e é
ignorado pelo Git porque contém informações pessoais.

Os arquivos JSONL antigos continuam preservados após a migração para permitir
conferência e recuperação. Eles não devem ser apagados até que as contagens, o
backup cifrado e uma restauração tenham sido verificados. Pré-matrículas antigas
entram como `needs_review`; depois da conferência, podem ser marcadas como
convertidas ou não convertidas. Somente as não convertidas entram na retenção de
20 dias definida pela escola.

Os comandos administrativos criam e verificam backups cifrados, nunca
sobrescrevem uma cópia existente e não ficam expostos pelo webhook. Consulte
[Proteção de dados — versão 1.0](docs/protecao-de-dados-v1.md) antes de migrar,
alterar status ou executar a retenção.

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
CASTILLA_ENV=production
CASTILLA_STORAGE_BACKEND=sqlite
CASTILLA_DB_PATH=data/private/castilla.sqlite3
CASTILLA_INACTIVITY_SECONDS=30
CASTILLA_BACKUP_KEY=chave-fernet-de-44-caracteres
```

Nunca envie o `.env` preenchido ao Git nem exponha seus valores em capturas de
tela, logs ou documentos. A chave Fernet termina com `=`, não pode conter
espaços extras e deve ser guardada separadamente dos arquivos de backup.

6. Para desenvolvimento sem Docker, inicie o webhook diretamente:

```powershell
python -m castilla_bot.whatsapp
```

A execução normal pelo contêiner está descrita na seção [Docker](#docker). Não
execute o webhook pelo Python e pelo contêiner ao mesmo tempo.

A porta padrão é `8000` e pode ser alterada pela variável `PORT`. A rota
`GET /` verifica o processo, `GET /ready` confirma o acesso ao banco e
`GET /webhook` e `POST /webhook` verificam e recebem os eventos da Meta. Quando
`CASTILLA_ENV=production`, a aplicação recusa o backend JSONL.

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

Com `CASTILLA_STORAGE_BACKEND=sqlite`, as sessões também ficam no banco privado:
reiniciar um único processo do bot não libera atendimentos pendentes. O modo
antigo (`jsonl`) ainda mantém as sessões só na memória e **não deve ser usado
para aprovar o teste de reinício**. Mantenha um único processo (como no
Dockerfile); múltiplos processos exigem coordenação adicional.

Veja o [roteiro de teste da passagem para o atendente](docs/teste-passagem-atendente.md)
antes de liberar esse fluxo em produção.
Veja também os [critérios críticos de lançamento da 1.0](docs/criterios-lancamento-v1.md).

## Publicar o webhook local com Cloudflare Tunnel

O Cloudflare Quick Tunnel fornece uma URL HTTPS temporária para desenvolvimento
e demonstrações. O endereço `trycloudflare.com` muda sempre que o túnel é
reiniciado e não deve ser utilizado em produção. Primeiro deixe uma única
instância do bot funcionando — pelo contêiner ou diretamente pelo Python — e
confirme que `http://127.0.0.1:8000/ready` retorna `ready`.

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

Utilize exatamente o valor de `WHATSAPP_VERIFY_TOKEN` como token de verificação.
Assine o campo `messages` e, para reconhecer `atendimento finalizado` digitado
no WhatsApp Business da escola, confirme também `smb_message_echoes`. O
contêiner e o túnel precisam permanecer ativos durante os testes locais.

Problemas comuns:

- **`cloudflared` não reconhecido:** reabra o PowerShell ou utilize o caminho
  completo do executável.
- **Erro HTTP 502:** confirme que o contêiner ou o webhook Python está
  respondendo na porta `8000`.
- **Timeout de DNS ou falha de conexão:** mantenha `--protocol http2`, desligue
  a VPN durante o teste e confira as permissões de saída do firewall.
- **A Meta não valida o webhook:** confira o sufixo `/webhook` e confirme que o
  token de verificação não possui espaços adicionais.

## Docker

Depois de configurar as variáveis de ambiente, construa a imagem:

```powershell
docker build -t castilla-bot .
```

O banco precisa permanecer fora do contêiner. No PowerShell, monte a pasta
`data` do projeto antes de iniciar:

```powershell
$castillaDataDir = (Resolve-Path ".\data").Path

docker run --rm --name castilla-bot `
  -p 8000:8000 `
  --env-file ".env" `
  --mount "type=bind,source=$castillaDataDir,target=/app/data" `
  castilla-bot
```

Sem o `--mount`, o SQLite ficaria dentro do contêiner e seria perdido quando o
contêiner fosse removido. O contêiner utiliza Gunicorn com um processo e expõe
a porta `8000`. Não execute simultaneamente `python -m castilla_bot.whatsapp`.

Em outro PowerShell, confirme a prontidão:

```powershell
Invoke-RestMethod "http://127.0.0.1:8000/ready"
```

## Escopo atual e próximos passos

O fluxo principal, o SQLite privado, as validações, a proteção contra eventos
duplicados, o tratamento de falhas observáveis e o temporizador já estão
implementados. Para fechar o desenvolvimento da versão 1.0, permanecem:

- dashboard restrito para saúde do bot, banco, webhook e falhas da Meta;
- restauração dos temporizadores automáticos após reinício do contêiner;
- painel administrativo para pré-matrículas e solicitações de atendimento;
- logs estruturados, alertas externos e acompanhamento de entrega;
- rotina operacional de backup, restauração e retenção com registro das ações;
- teste completo na conta real da escola, atualização da versão e changelog.

A hospedagem permanente e o endereço HTTPS estável continuam sendo requisitos
operacionais para substituir o Quick Tunnel em produção.

## Considerações de segurança

- Os eventos recebidos da Meta são autenticados por `X-Hub-Signature-256`.
- Os segredos são carregados por variáveis de ambiente e o `.env` é ignorado
  pelo Git.
- Os arquivos gerados com dados dos clientes são ignorados pelo Git.
- A implantação em produção deve utilizar HTTPS, acesso restrito, armazenamento
  criptografado, cópias de segurança, regras de retenção e controles adequados à
  Lei Geral de Proteção de Dados (LGPD).
