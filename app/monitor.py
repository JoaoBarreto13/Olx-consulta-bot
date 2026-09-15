import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

from curl_cffi.requests.exceptions import HTTPError

from .database import Database
from .models import Product
from .olx import OlxClient

logger = logging.getLogger(__name__)
Notifier = Callable[[int, Product], Awaitable[None]]

# Constantes de backoff inteligente
MIN_INTERVAL_SECONDS = 15
BASE_BACKOFF_SECONDS = 90      # 1º bloqueio: ~1.5 minuto
MAX_BACKOFF_SECONDS = 900      # Limite máximo de pausa: 15 minutos


class Monitor:
    def __init__(self, database: Database, client: OlxClient, interval: int, notify: Notifier):
        self.database = database
        self.client = client
        self.interval = max(interval, MIN_INTERVAL_SECONDS)
        self.notify = notify
        self.consecutive_blocks: int = 0

    async def run(self) -> None:
        logger.info("Monitor iniciado com intervalo base de %ds e backoff inteligente ativo.", self.interval)
        while True:
            sleep_duration = self._calculate_sleep_duration()
            try:
                had_block = await self.check_all()
                if had_block:
                    self.consecutive_blocks += 1
                    backoff_wait = self._calculate_backoff_sleep()
                    logger.warning(
                        "⚠️ Bloqueio/Rate-limit detectado da OLX (ocorrência consecutiva #%d). "
                        "Backoff inteligente ativado: aguardando %ds (~%.1f min) antes da próxima tentativa.",
                        self.consecutive_blocks,
                        backoff_wait,
                        backoff_wait / 60,
                    )
                    await asyncio.sleep(backoff_wait)
                    continue
                else:
                    if self.consecutive_blocks > 0:
                        logger.info("✅ Conexão normalizada com a OLX. Backoff zerado.")
                        self.consecutive_blocks = 0
            except Exception:
                logger.exception("Falha inesperada no ciclo de monitoramento")

            # Intervalo normal com variação humana (jitter)
            await asyncio.sleep(sleep_duration)

    def _calculate_sleep_duration(self) -> float:
        """Adiciona variação aleatória (jitter de -15% a +25%) para quebrar padrões fixos de robô."""
        jitter_pct = random.uniform(-0.15, 0.25)
        duration = self.interval * (1.0 + jitter_pct)
        return max(duration, MIN_INTERVAL_SECONDS)

    def _calculate_backoff_sleep(self) -> int:
        """Calcula pausa exponencial com limite máximo e jitter aleatório."""
        # Multiplica por 2 a cada bloqueio consecutivo: 90s -> 180s -> 360s -> até 900s
        factor = 2 ** max(0, self.consecutive_blocks - 1)
        base = min(BASE_BACKOFF_SECONDS * factor, MAX_BACKOFF_SECONDS)
        jitter = random.randint(5, 25)
        return int(base + jitter)

    async def check_all(self) -> bool:
        """Executa a verificação em todos os perfis ativos. Retorna True se detectou bloqueio/rate-limit."""
        profiles = self.database.profiles(active_only=True)
        had_block = False

        if not profiles:
            return False

        logger.info("Iniciando ciclo de verificação para %d perfil(is) ativo(s).", len(profiles))

        for index, profile in enumerate(profiles):
            # Pausa de 2 a 4 segundos entre perfis para não disparar requisições em lote simultâneo
            if index > 0:
                inter_delay = random.uniform(2.0, 4.5)
                await asyncio.sleep(inter_delay)

            try:
                count = await self.check_profile(profile.id)
                logger.info("Perfil %s verificado com sucesso — %d novo(s) notificado(s).", profile.seller_name, count)
            except HTTPError as http_err:
                status = getattr(http_err.response, "status_code", 0) if hasattr(http_err, "response") else 0
                if status in {403, 429, 503}:
                    logger.warning("OLX retornou HTTP %s para o perfil %s", status, profile.id)
                    had_block = True
                    break
                logger.exception("Erro HTTP ao verificar perfil %s", profile.id)
            except Exception as err:
                # Verifica se a mensagem de erro contém indício de bloqueio
                err_msg = str(err).lower()
                if "403" in err_msg or "429" in err_msg or "forbidden" in err_msg:
                    logger.warning("Bloqueio detectado via exceção genérica para perfil %s: %s", profile.id, err)
                    had_block = True
                    break
                logger.exception("Falha ao verificar perfil %s", profile.id)

        return had_block

    async def check_profile(self, profile_id: str) -> int:
        profile = self.database.get_profile(profile_id)
        if not profile or not profile.active:
            return 0
        seller_id = profile.id.rsplit(":", 1)[-1]
        seller_name, products = await self.client.fetch_profile(profile.url, seller_id, profile.seller_name)
        is_baseline = not self.database.has_products_for_profile(profile.id)

        logger.info(
            "Perfil '%s' (baseline=%s): %d produto(s) encontrado(s) na página.",
            seller_name, is_baseline, len(products),
        )

        notified = 0
        for product in products:
            if product.seller_name != seller_name:
                product = Product(**{**product.__dict__, "seller_name": seller_name})
            is_new = self.database.save_product(profile.id, product, notified=not is_baseline)
            if is_new:
                if is_baseline:
                    logger.info("  [BASELINE] Produto salvo sem notificar: %s", product.title[:80])
                else:
                    logger.info("  [NOVO] Notificando produto: %s — %s", product.title[:80], product.price)
                    await self.notify(profile.owner_chat_id, product)
                    notified += 1
        self.database.update_last_check(profile.id)
        return notified
