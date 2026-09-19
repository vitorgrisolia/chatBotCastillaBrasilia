# Critérios críticos para publicar a versão 1.0

A versão 1.0 **não está pronta** enquanto qualquer critério crítico abaixo
estiver pendente. Uma resposta de `GET /` ou um túnel temporário aberto não
provam que a Meta consegue entregar eventos ao número da escola.
Veja a [proposta de hospedagem permanente](hospedagem-v1.md).

| Prioridade | Critério | Prova exigida |
| --- | --- | --- |
| Crítica | Hospedagem permanente | Serviço sempre ligado, URL HTTPS estável, reinício automático, armazenamento persistente e backup restaurável. Quick Tunnel serve só para teste. |
| Crítica | Webhook da escola | Confirmar no painel/Graph API que a conta da escola está inscrita no endpoint correto, incluindo `messages` e, para encerrar pelo aplicativo, `smb_message_echoes`. Fazer teste real de entrada e saída. |
| Crítica | Falhas da Meta | Falhas de envio e eventos `failed` precisam ser detectados; um webhook com processamento incompleto não pode responder 200. Testar falha, reenvio do mesmo ID, lote parcialmente processado e reinício. |
| Crítica | Sessões e cadastros | Ativar banco privado após cópia e revisão dos arquivos antigos. Verificar que a passagem ao atendente continua silenciosa após reinício. |
| Crítica | Segurança dos dados | Definir quem acessa, onde ficam os backups, restauração e retenção; não remover arquivos antigos sem conferência. |

## Situação verificada em 18/09/2026

- Há um processo local do bot e um Cloudflare Quick Tunnel em execução. Eles
  **não** constituem hospedagem permanente.
- O `.env` atual não ativa `CASTILLA_STORAGE_BACKEND=sqlite`; as sessões em uso
  continuam em memória. Não reinicie o serviço esperando preservar passagens
  ao atendente antes de ativar a persistência com migração segura.
- O token configurado permitiu consultar o número de telefone na Graph API,
  mas isso **não comprova** a inscrição do webhook nem o recebimento de
  `smb_message_echoes` na conta da escola.
- Os testes automatizados de falha e reenvio são locais. A prova real no
  WhatsApp ainda precisa ser feita com o telefone de teste autorizado.
- O código agora valida o formato de e-mail e WhatsApp, recusa JSONL quando
  `CASTILLA_ENV=production` e oferece `GET /ready` para conferir o banco. Essas
  mudanças locais ainda não foram implantadas nem substituem o teste real.

## Limite do tratamento de falhas atual

Quando o envio falha de forma observável, o webhook devolve 503 para permitir
novo envio do evento, mantendo a resposta pendente. IDs de mensagens já
concluídas são lembrados por conversa para evitar reprocessamento comum. Isso
não garante “exatamente uma entrega” se a Meta receber a mensagem, mas a
conexão cair antes de confirmar o envio. Antes de liberar produção, defina a
política operacional para esse caso e monitore falhas de entrega. O código
foi preparado para **um processo**; execução concorrente em vários processos
exige coordenação transacional adicional.

Referências da Meta: [webhook HTTPS e estrutura dos eventos](https://www.postman.com/meta/whatsapp-business-platform/folder/tduohwq/webhook-payload-reference),
[inscrição da WABA](https://www.postman.com/meta/whatsapp-business-platform/folder/ypn8q0n/webhook-subscriptions),
[eventos de entrega com status `failed`](https://www.postman.com/meta/whatsapp-business-platform/folder/fuaee8l/statuses-object).
