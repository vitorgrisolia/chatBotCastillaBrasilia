# Hospedagem permanente — proposta para a versão 1.0

**Estado: preparada no projeto, ainda não contratada nem implantada.** A escola
precisa confirmar o orçamento e criar uma conta de hospedagem em seu próprio
nome. Não compartilhe senha, cartão ou chave da Meta em mensagens.

## Proposta inicial

Uma máquina Fly.io sempre ligada na região `gru` (São Paulo), com HTTPS e um
volume persistente para o SQLite. O arquivo `fly.toml.example` é apenas um
modelo: o nome do aplicativo precisa ser trocado antes da criação. O endereço
`*.fly.dev` pode ser usado inicialmente, sem comprar domínio.

O modelo desativa o desligamento por inatividade, configura uma checagem de
saúde e monta `/data` como volume. O bot deve rodar com **uma única máquina**:
volumes independentes não replicam o SQLite automaticamente. Esta solução é
simples para o início, mas uma falha do host pode causar indisponibilidade até
a recuperação. “Sempre ligado” não significa alta disponibilidade.

O volume tem snapshots diários pela plataforma, mas eles **não substituem** um
backup cifrado em outro local. Antes de migrar cadastros reais, definir destino
externo, chave, frequência, prazo de guarda e teste de restauração. O prazo de
20 dias das pré-matrículas não é automaticamente o prazo dos backups.

## Preparação já feita

- `Dockerfile` executa um único processo do webhook, com quatro threads, usando
  `exec` para que o Gunicorn receba o sinal de parada.
- `docker-entrypoint.sh` ajusta o dono da pasta do banco no volume e executa o
  serviço com o usuário `castilla`, sem privilégios.
- `constraints.txt` fixa as versões das dependências usadas no build.
- A CI constrói a imagem, inicia com SQLite temporário, consulta `/ready` e
  reinicia o contêiner usando o mesmo volume.
- `.dockerignore` impede que `.env`, cadastros e backups entrem no contexto de
  construção da imagem.
- `fly.toml.example` configura HTTPS, região, volume, checagem de saúde e
  armazenamento SQLite persistente, mas contém um nome ilustrativo.

## Roteiro de produção

O `.env.example` serve para desenvolvimento. Em produção, configure as
variáveis no cofre de segredos da hospedagem, nunca em arquivo versionado:

| Variável | Valor em produção |
| --- | --- |
| `CASTILLA_ENV` | `production` (só `development` e `production` são aceitos) |
| `CASTILLA_STORAGE_BACKEND` | `sqlite` (a aplicação recusa `jsonl` em produção) |
| `CASTILLA_DB_PATH` | caminho dentro do volume, por exemplo `/data/private/castilla.sqlite3` |
| `CASTILLA_INACTIVITY_SECONDS` | `30`, ou outro número finito maior que zero |
| `WHATSAPP_*`, `META_*` | valores reais da Meta, sem espaços nas pontas |
| `OPERATOR_TOKEN` | token longo e aleatório, ou vazio para desativar a rota |

1. Crie o volume persistente e monte-o em `/data` (no Fly.io, a seção
   `[mounts]` do `fly.toml.example`).
2. Mantenha **uma máquina e um processo**. Os bloqueios por conversa ficam em
   memória; outra instância não os enxerga.
3. Implante a imagem e confira `GET /ready`. A resposta `ready` confirma que o
   banco está acessível.
4. Reinicie a máquina uma vez e confira `GET /ready` de novo. Uma conversa em
   atendimento humano deve continuar em silêncio depois do reinício.
5. Se a inicialização falhar por configuração inválida, o log mostra o nome da
   variável. Corrija no cofre e implante de novo.

## Operação

Itens técnicos já definidos:

- **Verificação:** `GET /ready` pela checagem de saúde da hospedagem e
  `python -m castilla_bot.privacy_admin status` para contagens sem dados
  pessoais.
- **Backup externo:** `privacy_admin backup` e `verify-backup`, com a chave
  `CASTILLA_BACKUP_KEY` guardada longe das cópias. Detalhes em
  [proteção de dados](protecao-de-dados-v1.md).
- **Retorno após falha:** restaurar o último backup verificado com
  `restore-backup` em um banco novo, apontar `CASTILLA_DB_PATH` para ele e
  conferir `/ready`. Se a nova versão falhar, implante a imagem anterior; o
  callback da Meta só deve mudar depois do teste.
- **Solicitações de atendimento:** cada registro em `atendimentos` traz o
  campo `conversa` com o número do cliente.

Pendentes de decisão da escola: quem responde pelos atendimentos humanos e como
a equipe é avisada de uma nova solicitação, quem faz a verificação diária, onde
ficam os backups externos e com que frequência, e quem pode executar o retorno
após falha.

## O que falta antes da troca do WhatsApp

1. A escola confirma orçamento e cria/autoriza a conta de hospedagem e a forma
   de pagamento. Criar recurso pago não será feito sem essa escolha.
2. Implantar o contêiner com o nome real do aplicativo e configurar segredos
   somente no cofre da hospedagem, nunca no repositório.
3. Criar backup cifrado e verificado dos dados atuais, revisar a migração dos
   JSONL e restaurar o banco no volume privado. Preservar os arquivos antigos
   até conferir as contagens; não apagar cadastros automaticamente.
4. Implantar backup externo e monitoramento com alerta de indisponibilidade e
   de mensagens com status `failed`.
5. Testar a URL HTTPS pública, a verificação do webhook, a inscrição da WABA
   nos eventos `messages` e `smb_message_echoes`, a passagem para o atendente
   e o retorno após reinício.
6. Só então, em janela combinada, trocar o callback da Meta. Manter um plano
   de retorno caso o teste falhe.

Referências: [região São Paulo](https://fly.io/docs/reference/regions/),
[configuração de HTTPS, saúde e volume](https://fly.io/docs/reference/configuration/),
[limites e backups dos volumes](https://fly.io/docs/volumes/overview/),
[preços atuais](https://fly.io/docs/about/pricing/).
