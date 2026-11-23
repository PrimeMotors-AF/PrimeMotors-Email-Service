# PrimeMotors-Email-Service

O serviço envia uma confirmação da proposta para o endereço cadastrado pelo
usuário e uma notificação separada para `PROPOSAL_NOTIFICATION_EMAIL`. O
destinatário do usuário vem do evento autenticado recebido do backend; o cliente
não escolhe livremente o destinatário.

Configure MySQL, SMTP, `SERVICE_TOKEN` e `PROPOSAL_NOTIFICATION_EMAIL` conforme
`.env.example`. Para a API executada fora do Docker, use `MYSQL_HOST=localhost`
e `MYSQL_PORT=3307`; dentro de uma rede Compose, use o nome do serviço e a porta
interna `3306`. `SERVICE_TOKEN` deve ser um segredo forte compartilhado somente
entre backend/consumer e serviço de email.

O limite de envio é persistido no MySQL e funciona entre réplicas do serviço:

- `EMAIL_RATE_LIMIT_PER_RECIPIENT`: confirmações por destinatário por janela
  (padrão: 5).
- `EMAIL_RATE_LIMIT_GLOBAL`: mensagens totais por janela (padrão: 100).
- `EMAIL_RATE_LIMIT_WINDOW_SECONDS`: duração da janela (padrão: 3600).

Após alterar o schema, aplique as migrations com `alembic upgrade head`. Eventos
excedendo o limite recebem HTTP 429 e o cabeçalho `Retry-After`. O serviço
registra separadamente o envio para o cliente e para a equipe, permitindo que
uma repetição do evento tente novamente somente mensagens ainda pendentes. As
respostas também informam `RateLimit-Limit`, `RateLimit-Remaining`,
`RateLimit-Reset` e `RateLimit-Policy`.

O envio também usa Redis para adquirir um lock atômico por proposta (`SET NX`)
com TTL de 120 segundos, evitando que réplicas processem a mesma proposta ao
mesmo tempo. Após o SMTP aceitar cada mensagem, o serviço grava uma chave de
sucesso separada para cliente/equipe, com TTL de 35 dias. Se a atualização no
MySQL falhar depois do envio, essa chave permite reconciliar o estado sem enviar
novamente. Os indicadores no MySQL continuam sendo o registro durável; a
idempotência não pode eliminar totalmente a janela de falha entre a aceitação
do e-mail pelo SMTP e a gravação do sucesso no Redis.

O consumer Redis usa o grupo `email-service`, recupera mensagens pendentes e
confirma com `XACK` somente depois do processamento. Para manter dados pessoais
fora do Stream, consulta uma rota interna autenticada do backend para obter o
payload completo. O Compose principal inicia backend, Redis, API/consumer e
MySQL do email juntos. Veja [`../docs/email-service.md`](../docs/email-service.md)
para fluxo, configuração e operação.