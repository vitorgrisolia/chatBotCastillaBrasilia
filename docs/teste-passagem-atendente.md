# Teste real da passagem para o atendente (versão 1.0)

Este roteiro **ainda não é um resultado de teste real**. Os testes automatizados
simulam eventos assinados da Meta; a aprovação final exige uma conversa de
teste no WhatsApp da escola, com uma pessoa respondendo pela própria conta.

## Antes de começar

- Combine uma janela de teste. Não altere o webhook da escola durante
  atendimento de alunos sem planejar a troca e a volta.
- Use somente um telefone pessoal autorizado para teste; não use um aluno.
- Confirme que o número da escola está em coexistência entre WhatsApp Business
  e Cloud API e que o campo `smb_message_echoes` está assinado. Sem esse evento,
  a frase digitada no aplicativo da escola não chega ao bot.
- Use `CASTILLA_STORAGE_BACKEND=sqlite` e siga a migração segura descrita em
  `protecao-de-dados-v1.md` antes de trocar o serviço. O modo `jsonl` perde o
  estado após reiniciar.
- Mantenha apenas um processo do bot durante este teste. O webhook deve estar
  acessível por HTTPS e a assinatura da Meta deve ser verificada.

## Sequência e resultado esperado

1. Do telefone de teste, envie `Olá` para a escola. O bot deve mostrar o menu.
2. Envie `6`, informe o nome de teste e o assunto. O bot deve responder com
   **um único** aviso de que o atendente continuará a conversa.
3. Ainda pelo telefone de teste, envie `MENU`, `REINICIAR`, uma pergunta e até
   `atendimento finalizado`. O bot não deve responder a nenhuma delas.
4. Reinicie **um único** processo do bot durante a espera. Envie mais uma
   mensagem do telefone de teste. O bot deve continuar em silêncio.
5. Pelo WhatsApp Business **da escola**, na conversa com esse telefone, escreva
   algo que não seja a frase de encerramento. O bot deve permanecer calado.
6. Ainda pela conta da escola, escreva exatamente `atendimento finalizado`
   (maiúsculas e espaços nas pontas são aceitos). O bot não envia mensagem de
   confirmação; o webhook deve registrar que reconheceu o encerramento.
7. Do telefone de teste, envie `MENU`. Só agora o bot deve voltar a responder.

## Critérios para aprovar

- O aviso da etapa 2 aparece uma vez, inclusive se a Meta repetir o evento.
- Nenhuma mensagem automática aparece entre as etapas 2 e 6, mesmo após
  reiniciar o serviço.
- A frase enviada pelo **cliente** não libera o bot; só a mensagem de saída da
  conta da escola, recebida como `smb_message_echoes`, libera aquela conversa.
- A mensagem da conta da escola não libera a conversa de outro telefone.
- Se não chegar o evento `smb_message_echoes`, o teste **falhou**. Não assuma
  que a frase digitada pelo atendente foi reconhecida; verifique a configuração
  de coexistência ou use uma interface própria com a rota protegida.

Os logs desta passagem registram apenas os marcos “aviso enviado” e
“atendimento encerrado”, sem texto da conversa ou número de telefone. Não
publique capturas de tela com dados pessoais em issues ou apresentações.

Este teste não substitui os testes de falha de envio pela Meta, mensagens
duplicadas em outras etapas e operação com vários processos.
