# Configuração de e-mail

O DevPulse usa e-mail de dois jeitos, configurados separadamente:

| Papel | O que é | Onde configurar |
|---|---|---|
| **Remetente da newsletter** | Quem envia a TechDrops: `tech@newsletter.thedrops.com.br` | `config/sources.yaml` (`config.sender`) ou painel → Fontes |
| **Conta de recebimento** | A **sua** caixa, onde a TechDrops chega | `NEWSLETTER_MAILBOX_*` no `.env` |
| **Destinatário das edições** | Para onde os roteiros são enviados | `EMAIL_RECIPIENT` no `.env` ou painel → Configurações |
| **Conta de envio** | A conta SMTP que envia as edições | `SMTP_*` e `EMAIL_FROM` no `.env` |

O endereço da TechDrops nunca é usado como caixa de entrada nem como destinatário.

---

## 1. Leitura da newsletter (conta de recebimento)

O DevPulse lê **somente** mensagens do remetente configurado, em modo somente leitura, e guarda apenas título, link e um trecho de até 400 caracteres de cada matéria citada. Ele não armazena a newsletter inteira, e cada link é aberto e verificado na fonte original.

Primeiro, assine a TechDrops com a conta de recebimento. Depois escolha **uma** das opções abaixo.

### Opção A — Gmail API (recomendada para Gmail)

Permissão mínima: `https://www.googleapis.com/auth/gmail.readonly`.

1. Em <https://console.cloud.google.com/>, crie um projeto e ative a **Gmail API**.
2. *APIs e serviços → Tela de permissão OAuth*: tipo **Externo**, modo de teste, e adicione a sua conta como usuário de teste.
3. *Credenciais → Criar credenciais → ID do cliente OAuth → App para computador*. Anote o client ID e o secret.
4. No WSL (fora do container):
   ```bash
   python3 scripts/oauth_gmail.py --client-id SEU_CLIENT_ID --client-secret SEU_SECRET
   ```
   Autorize com a conta de recebimento. O script imprime `GMAIL_REFRESH_TOKEN=...`.
5. No `.env`:
   ```env
   NEWSLETTER_MAILBOX_PROVIDER=gmail
   NEWSLETTER_MAILBOX_ADDRESS=sua-conta@gmail.com
   GMAIL_CLIENT_ID=...
   GMAIL_CLIENT_SECRET=...
   GMAIL_REFRESH_TOKEN=...
   ```
6. Reinicie (`docker compose up -d`) e, no painel → Fontes → TechDrops → **Coletar**.

> Em apps OAuth no modo "teste", o Google pode expirar o refresh token após alguns dias. Se a coleta passar a falhar com "Falha ao renovar token OAuth", repita o passo 4. Publicar o app (mesmo só para uso próprio) evita essa expiração. Confira as regras atuais do Google.

### Opção B — Microsoft Graph (Outlook.com / Microsoft 365)

Permissão delegada mínima: `Mail.Read` (+ `offline_access`).

1. Em <https://entra.microsoft.com/> → *Registros de aplicativo → Novo registro*. Tipos de conta: "contas pessoais Microsoft" (Outlook.com) ou a sua organização.
2. *Autenticação*: ative **Permitir fluxos de cliente público**.
3. *Permissões de API*: Microsoft Graph → Delegadas → `Mail.Read`.
4. No WSL:
   ```bash
   python3 scripts/oauth_graph.py --client-id SEU_CLIENT_ID --tenant consumers   # ou o ID do seu tenant
   ```
5. No `.env`: `NEWSLETTER_MAILBOX_PROVIDER=graph`, `GRAPH_CLIENT_ID`, `GRAPH_TENANT_ID`, `GRAPH_REFRESH_TOKEN`.

### Opção C — IMAP autenticado

Use quando o provedor oferecer IMAP com senha de aplicativo. No Gmail: ative a verificação em duas etapas e crie uma senha de app em <https://myaccount.google.com/apppasswords>.

```env
NEWSLETTER_MAILBOX_PROVIDER=imap
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USERNAME=sua-conta@gmail.com
IMAP_PASSWORD=senha-de-app
IMAP_FOLDER=INBOX
```

A busca usa `FROM "remetente" SINCE data` e lê com `BODY.PEEK[]`, o que não marca a mensagem como lida.

---

## 2. Envio das edições (SMTP)

Exemplo com Gmail (requer verificação em duas etapas e senha de app):

```env
EMAIL_ENABLED=true
EMAIL_RECIPIENT=voce@exemplo.com
EMAIL_FROM=sua-conta@gmail.com
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USERNAME=sua-conta@gmail.com
SMTP_PASSWORD=senha-de-app
```

Outros provedores com SMTP autenticado (Outlook, Zoho, Brevo, Amazon SES, Resend, Mailgun…) funcionam da mesma forma. Use `SMTP_SECURITY=ssl` para a porta 465.

Para testar: painel → Configurações → "Enviar teste" no e-mail. Isso envia **uma mensagem real**, só quando você clica. A tela Entregas mostra o `Message-ID` e o status "aceita pelo provedor".

O que o DevPulse registra: tentativas, horário, `Message-ID`, aceitação pelo servidor SMTP e erros (sem senhas). O SMTP não informa se a mensagem chegou à caixa de entrada ou caiu no spam. Se a primeira edição não aparecer, olhe a pasta de spam e marque como "não é spam".

Formato: HTML responsivo + texto simples, com todos os roteiros completos no corpo. O link do painel citado no e-mail só abre no computador onde o DevPulse roda.
