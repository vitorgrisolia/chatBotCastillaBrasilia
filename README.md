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

As solicitações são gravadas em `data/atendimentos.jsonl` e as pré-matrículas
em `data/pre_matriculas.jsonl`. Cada linha é um registro JSON independente.

## Integração com outros canais

Use uma identificação estável do cliente como `session_id` e envie cada texto
recebido para `CastillaBot.handle(session_id, mensagem)`. A string retornada é a
resposta que deve ser enviada ao cliente.

## WhatsApp Business (Cloud API oficial)

1. Crie um aplicativo do tipo **Business** em Meta for Developers e adicione o
   produto **WhatsApp**.
2. No painel de configuração da API, obtenha o token de acesso e o **Phone
   Number ID**. Para produção, use um token permanente de usuário do sistema.
3. Copie `.env.exemple` para `.env` e preencha os valores. O bot carrega esse
   arquivo automaticamente. O `.env` preenchido não deve ser enviado ao Git.
4. Instale e execute o webhook:

```powershell
python -m pip install -e .
Copy-Item .env.exemple .env
# Abra o arquivo .env e substitua todos os valores de exemplo pelos dados da Meta.
python -m castilla_bot.whatsapp
```

### Iniciar o Cloudflare Tunnel no Windows

O Cloudflare Quick Tunnel publica temporariamente o webhook local em uma URL
HTTPS. Ele deve ser usado somente para testes e demonstrações, pois o endereço
`trycloudflare.com` muda sempre que o túnel é reiniciado.

1. Abra o primeiro PowerShell na pasta do projeto e inicie o bot:

```powershell
cd "C:\Users\griso\Documents\ChatGPT\Criacao de BOT"
python -m castilla_bot.whatsapp
```

Mantenha essa janela aberta. O Flask deve informar que está executando na porta
8000. Em outra janela, o servidor local pode ser testado com:

```powershell
Invoke-WebRequest http://localhost:8000/
```

2. Abra um segundo PowerShell e confirme se o `cloudflared` está acessível:

```powershell
cloudflared --version
```

Se o comando não for reconhecido, feche e abra novamente o PowerShell. Também é
possível executar diretamente o arquivo instalado:

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" --version
```

3. Ainda no segundo PowerShell, inicie o túnel apontando para a porta do bot:

```powershell
& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --protocol http2 --url http://localhost:8000
```

Se o comando `cloudflared` já estiver sendo reconhecido, a forma abreviada é:

```powershell
cloudflared tunnel --protocol http2 --url http://localhost:8000
```

Use somente o endereço `http://localhost:8000` no comando. Não copie colchetes,
parênteses, barras invertidas ou a formatação de link do navegador.

4. Aguarde o terminal mostrar uma URL semelhante a:

```text
https://palavras-aleatorias.trycloudflare.com
```

5. No painel da Meta, configure a URL de callback acrescentando `/webhook`:

```text
https://palavras-aleatorias.trycloudflare.com/webhook
```

Informe exatamente o mesmo valor configurado em `WHATSAPP_VERIFY_TOKEN` e
assine o campo `messages`. As duas janelas do PowerShell precisam permanecer
abertas durante o teste.

Problemas comuns:

- **`cloudflared` não reconhecido:** use o caminho completo do executável
  mostrado acima.
- **Erro 502:** confirme que `python -m castilla_bot.whatsapp` está em execução
  e ouvindo na porta 8000.
- **`i/o timeout` ou falha de conexão:** mantenha a opção `--protocol http2`,
  teste sem VPN e verifique se o firewall permite a conexão de saída.
- **Meta não valida o webhook:** confirme o sufixo `/webhook` e compare o token
  de verificação sem espaços extras.

Para produção, não use o Quick Tunnel. Publique o bot em uma hospedagem estável
ou configure um Cloudflare Tunnel nomeado com domínio permanente.

A rota `/` serve como verificação de saúde e `/webhook` recebe/verifica os
eventos. A porta padrão é 8000 e pode ser alterada pela variável `PORT`.
O `Dockerfile` incluído pode ser usado para publicar em uma hospedagem de
contêineres. O webhook valida `X-Hub-Signature-256` usando `META_APP_SECRET`.
