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

- `Dockerfile` executa um único processo do webhook.
- `.dockerignore` impede que `.env`, cadastros e backups entrem no contexto de
  construção da imagem.
- `fly.toml.example` configura HTTPS, região, volume, checagem de saúde e
  armazenamento SQLite persistente, mas contém um nome ilustrativo.

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
