# PromoTracker

Agregador de promoções com notificação no Telegram, focado em três nichos:

- **Tênis de corrida** — Asics, Mizuno, Nike, Adidas, Olympikus, Fila, Brooks, Saucony
- **Maquiagem** — Vizzela, Dailus
- **Cabelo** — Lola Cosmetics

Roda **100% no GitHub Actions** com cron a cada 5 min. Sem servidor sempre ligado, sem banco de dados. Estado persiste num `data/state.json` versionado no próprio repo.

## Como funciona

```
.github/workflows/check.yml  cron */5 * * * *
   ↓
scripts/run_check.py
   ↓
Store(state.json) carrega
   ↓
PromobitSource.fetch()             7 categorias x ~10 itens
   ↓
classificar_e_filtrar()            filtra marcas-alvo + valida categoria
   ↓
gerar_eventos()                    persiste produto/oferta/historico no Store
   ↓
verificar antes de enviar          re-checa pagina de detalhe (availability + preco)
   ↓
notifier.telegram.send_message()   envia ate 10 notif por job
   ↓
revalidar_ofertas_ativas()         re-checa ofertas existentes
   ↓
Store.flush()                      grava state.json
   ↓
git commit + push                  versiona o novo estado
```

## Setup

### 1. Criar bot no Telegram

1. Abra o Telegram e procure **@BotFather**.
2. Envie `/newbot` e siga as instruções.
3. Copie o **token** (`123456789:ABCdef...`).
4. Procure **@userinfobot**, mande `/start` e copie seu **chat_id**.
5. **Mande qualquer mensagem pro seu bot novo** — bots não podem iniciar conversas.

### 2. Fork ou clonar este repo + push pro GitHub

O workflow precisa rodar num repo público pra ter cron 5-min sem custo.

### 3. Configurar GitHub Secrets

No repo: **Settings → Secrets and variables → Actions → New repository secret**.

Obrigatórios:
- `TELEGRAM_BOT_TOKEN` — token do BotFather
- `TELEGRAM_CHAT_ID` — chat_id (ou CSV `123,456` pra múltiplos)

Opcionais (WhatsApp via CallMeBot):
- `WHATSAPP_PHONE` — número com código do país sem `+` (ex: `5511999999999`)
- `WHATSAPP_APIKEY` — key do CallMeBot

### 4. Pronto

A cada 5 min o workflow roda automaticamente. Pra forçar uma execução agora: **Actions → PromoTracker check → Run workflow**.

## Rodar local

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
:: editar .env com TELEGRAM_BOT_TOKEN/CHAT_ID
python -m scripts.run_check
```

Cada run grava `data/state.json` no diretório atual.

## Ajustar limites de notificação

Edite `MIN_DESCONTO_PCT` (default 20), `MAX_NOTIFICACOES_POR_JOB` (default 10), `THROTTLE_SEGUNDOS` (default 3). Em produção (GH Actions), ajustar em `.github/workflows/check.yml` na seção `env`.

## Estrutura

```
app/
  config.py            Pydantic Settings (.env), now_br()
  store.py             JSON-backed state (Produto, Oferta, Historico, Notif, Fonte)
  coleta.py            Pipeline coleta -> classifica -> verify -> notifica
  revalidator.py       Re-checa ofertas ativas no detalhe + atualiza/remove
  sources/
    base.py            Source ABC, OfertaRaw, helpers (parse_preco, normalizar)
    brands.py          Marcas-alvo + variacoes + linhas Lola + modelos de corrida
    promobit.py        Parser de JSON-LD do Promobit
    registry.py        {nome -> SourceClass}
  matchers/
    brand_filter.py    Detecta marca-alvo no titulo
    category_filter.py Valida categoria (corrida exige modelo OU "tenis"+keyword)
    deduper.py         Por hash_unico, mantem menor preco
    pipeline.py        Orquestra os 3 acima
  notifier/
    telegram.py        send_message + format HTML
    whatsapp.py        CallMeBot (opcional)
    dispatcher.py      Despacha pro(s) canal(is) configurado(s)
    rules.py           gerar_eventos(): persist + decide o que notificar

scripts/
  run_check.py         Entry point CLI (chamado pelo GH Actions cron)

.github/workflows/
  check.yml            Cron 5 min + commit-back do state.json

data/
  state.json           Estado persistente (versionado)
  last_html/           HTML bruto da ultima coleta (gitignored, debug)
  http_cache/          Cache HTTP local (gitignored, so dev_mode)

tests/                 pytest + fixtures (74 testes)
```

## Adicionar marca/variação/modelo

Edite `app/sources/brands.py`:

- **Maquiagem nova marca**: adicionar em `MARCAS_MAQUIAGEM`
- **Variação de escrita**: adicionar na lista de variações da marca
- **Linha Lola nova**: adicionar em `LINHAS_LOLA`
- **Modelo de tênis novo**: adicionar em `MODELOS_CORRIDA`

## Quando o Promobit mudar de layout

Parser usa **JSON-LD Schema.org** (`<script type="application/ld+json">`), não classes CSS. Se um dia o run retornar `0 brutas` em todas categorias:

1. Ative `DEV_MODE=true` localmente, rode `python -m scripts.run_check`
2. Confira `data/last_html/promobit_*.html`
3. Veja se ainda tem `"@type": "ItemList"`
4. Ajuste `parse_listagem()` em `app/sources/promobit.py`
5. Atualize `tests/fixtures/promobit_listagem.html` e rode `pytest`

## Por que GitHub Actions e não um servidor

Tentamos:
- **Fly.io**: máquina ficou sendo suspendida (4 dias parada)
- **Vercel/Netlify serverless**: não dá pra ter SQLite ou rodar APScheduler
- **GitHub Actions** com cron 5 min em repo público: free, infinito, com Python nativo, sem suspensão. State versionado no próprio repo via `git push` no fim de cada run.

## Troubleshooting

| Sintoma | Causa provável | Fix |
|---|---|---|
| `0 brutas` em todas categorias | Promobit bloqueou IP / mudou layout | `DEV_MODE=true` local + ver `data/last_html/` |
| `0 brutas` em uma categoria só | URL daquela categoria mudou | Atualizar `URLS` em `promobit.py` |
| Telegram retorna 401 | Token errado | Conferir `TELEGRAM_BOT_TOKEN` |
| Telegram retorna 400 "chat not found" | Não abriu conversa com o bot | Manda `/start` pro bot manualmente |
| Workflow não dispara | Cron de repos sem atividade pode pausar — GitHub | Faça qualquer commit pra "acordar"; ou Actions → Run workflow manual |
| Conflito de push (race) | Dois runs concorrentes | O job ja faz `git pull --rebase`; se persistir, baixar concurrency pra 1 |

## Aviso legal

Uso pessoal. Respeita robots.txt e usa throttle de 3s/domínio. Não republicar nem usar comercialmente.
