# Bot de monitoramento OLX no Telegram

Bot multiusuário que monitora exclusivamente perfis públicos da OLX cadastrados por cada usuário ou grupo e envia notificações quando detecta anúncios novos.

## O que está implementado

- Limite configurável de perfis, com padrão de 1.
- Cadastro por URL pública ou ID do vendedor.
- SQLite para perfis, anúncios descobertos, histórico e deduplicação.
- Primeira consulta usada como linha de base: anúncios antigos não geram spam.
- Verificação periódica, padrão de 120 segundos.
- Notificação com título, preço, localização, categoria, descrição, fotos e link.
- Comandos `/adicionar_perfil`, `/listar_perfis`, `/remover_perfil`, `/pausar_perfil`, `/retomar_perfil`, `/historico`, `/status` e `/ajuda`.
- Cada usuário privado ou grupo possui seus próprios perfis, histórico, limite e notificações.
- O mesmo vendedor pode ser monitorado por vários chats sem misturar os dados.
- Confirmação inline antes de remover um perfil.

## Configuração

1. Crie um bot pelo [@BotFather](https://t.me/BotFather) e copie o token.
2. Crie o ambiente e instale as dependências:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install pytest pytest-asyncio
```

3. Copie `.env.example` para `.env` e preencha apenas `TELEGRAM_BOT_TOKEN`.
4. Inicie:

```bash
python -m app.main
```

O arquivo SQLite será criado em `data/olx_bot.sqlite3` por padrão. O `chat_id` é obtido automaticamente a cada comando no Telegram, então a mesma instância pode atender vários usuários e grupos.

## Testes

```bash
pytest -q
```

## Observações importantes

A OLX pode alterar HTML, endpoints, proteção anti-bot ou exigir autenticação. O parser usa JSON-LD e links visíveis como estratégias públicas e tolerantes, mas a coleta deve ser monitorada e ajustada se a estrutura do site mudar. O bot não contorna login, CAPTCHA, bloqueios ou controles de acesso.

O primeiro check cadastra os anúncios atuais como baseline. A partir do ciclo seguinte, somente IDs ainda não vistos são notificados.