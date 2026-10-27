# Configuração do WhatsApp Business Platform

O DevPulse usa a **Cloud API oficial da Meta** (`graph.facebook.com/{versão}/{phone_number_id}/messages`). Ele não usa automação do WhatsApp Web. O canal começa **desativado** (`WHATSAPP_ENABLED=false`) e só envia quando todas as condições abaixo forem atendidas. Antes disso, cada edição registra a entrega como "desativada" ou "bloqueada", com o motivo.

## O que você precisa

1. Uma conta no **Meta Business** (business.facebook.com) e um app no **Meta for Developers** com o produto *WhatsApp*.
2. Um **número de telefone de envio** registrado na WhatsApp Business Platform. Ele não pode ser o mesmo número do seu WhatsApp pessoal em uso. O app de testes da Meta oferece um número de teste, que serve para começar.
3. Um **token de acesso permanente**: em *Configurações do negócio → Usuários do sistema*, crie um usuário do sistema, atribua o app e a conta do WhatsApp e gere um token com `whatsapp_business_messaging` (e `whatsapp_business_management` para gerenciar templates). O token temporário do painel de testes expira em 24 h.
4. O **Phone number ID** (não é o número em si), exibido em *WhatsApp → Configuração da API*.
5. **Opt-in** do destinatário: o número que vai receber precisa ter concordado em receber mensagens desse número comercial. No número de teste da Meta, ele também precisa estar na lista de destinatários permitidos.
6. Um **template aprovado**. Mensagens iniciadas pela empresa fora da janela de 24 h de atendimento só podem ser templates.

## Template sugerido

Crie em *WhatsApp Manager → Modelos de mensagem*:

- Nome: `devpulse_edicao`
- Idioma: Português (BR) — `pt_BR`
- Categoria: a Meta define na análise. Um resumo diário que você mesmo assinou costuma ser enviado como *Utilidade*, mas pode ser reclassificado como *Marketing*, que tem preço diferente.
- Corpo:

```
DevPulse AI — edição de {{1}}: {{2}} roteiro(s) disponível(is).
{{3}}
Os roteiros completos foram enviados para o seu e-mail.
```

O DevPulse preenche:

- `{{1}}`: data da edição
- `{{2}}`: quantidade
- `{{3}}`: lista compacta "1) título (duração) fonte: link …"

A Meta não aceita quebras de linha nem tabulações dentro dos parâmetros, e o sistema já os higieniza. Veja o exemplo real em [examples/whatsapp-exemplo.txt](examples/whatsapp-exemplo.txt).

Se você usar outro template, ajuste o número de variáveis do corpo para 3 ou adapte `build_whatsapp` em `backend/devpulse/scheduler/deliveries.py`.

## `.env`

```env
WHATSAPP_ENABLED=true
WHATSAPP_ACCESS_TOKEN=token-permanente-do-usuario-do-sistema
WHATSAPP_PHONE_NUMBER_ID=123456789012345
WHATSAPP_API_VERSION=v23.0
WHATSAPP_RECIPIENT=+5598999999999
WHATSAPP_RECIPIENT_OPT_IN=true
WHATSAPP_MODE=template
WHATSAPP_TEMPLATE_NAME=devpulse_edicao
WHATSAPP_TEMPLATE_LANGUAGE=pt_BR
```

`WHATSAPP_API_VERSION` deve ser uma versão ainda suportada pela Meta. Confira o changelog da Graph API e atualize quando a sua for descontinuada. O destinatário e o opt-in também podem ser alterados no painel → Configurações. O número é validado no formato E.164.

**Modo `text`**: envia a mensagem formatada completa, sem template. Só funciona dentro da janela de 24 h, ou seja, se você mandou uma mensagem para o número comercial nas últimas 24 h. Fora dela, a API retorna o erro 131047, e o DevPulse registra a falha com a sugestão de usar `template`.

## Comportamento do DevPulse

| Situação | Resultado |
|---|---|
| Canal desativado | Entrega `disabled` (registrada, sem envio) |
| Token, phone number ID ou template ausentes | `blocked`, listando o que falta |
| Número fora do E.164 ou sem opt-in | `blocked` |
| HTTP 401 / código 190 (token inválido/expirado) | `failed_auth`, sem nova tentativa |
| 429, 5xx, limites de taxa (130429, 131056…) | `retrying` com intervalo crescente (até 5 tentativas) |
| 131047 (fora da janela de 24 h) | `failed`, com orientação |
| Aceito pela API | `sent` + `wamid` em "Identificador do provedor" |
| Queda durante o envio | `needs_review`, sem reenvio automático (evita duplicar) |

"Aceita" significa que a API recebeu a mensagem. Os status de entrega e leitura chegam por **webhook**, que exige uma URL pública HTTPS. Como o DevPulse roda só localmente, isso não foi habilitado. Se um dia você expuser um endpoint seguro (por exemplo, com um túnel autenticado), dá para acrescentar um receptor de webhooks sem mudar o restante.

## Teste

Painel → Configurações → WhatsApp → **Enviar teste**. É um envio real, feito só quando você confirma. Os testes automatizados nunca enviam mensagens: o envio real fica bloqueado em `APP_ENV=test`, a não ser que você rode explicitamente `RUN_EXTERNAL_TESTS=1 ALLOW_REAL_SENDS_IN_TESTS=true pytest tests/external`.
