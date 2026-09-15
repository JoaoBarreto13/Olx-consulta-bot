import asyncio
import logging
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .config import Settings
from .database import Database
from .models import Profile, Product
from .monitor import Monitor
from .olx import OlxClient, normalize_profile_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


HELP = """Comandos disponíveis:
/adicionar_perfil <URL ou ID>
/listar_perfis
/remover_perfil <número>
/pausar_perfil <número>
/retomar_perfil <número>
/historico [dias]
/status
/ajuda"""


def run() -> None:
    asyncio.run(main())


async def main() -> None:
    settings = Settings.from_env()
    database = Database(settings.database_path)
    client = OlxClient(settings.olx_timeout_seconds)
    bot = Bot(settings.telegram_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher()

    async def notify(chat_id: int, product: Product) -> None:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Abrir anúncio", url=product.url)]])
        await bot.send_message(chat_id, product.notification_text(), reply_markup=keyboard)

    monitor = Monitor(database, client, settings.check_interval_seconds, notify)

    @dispatcher.message(Command("start"))
    async def start(message: Message) -> None:
        await message.answer("Bot online.\n\n" + HELP)

    @dispatcher.message(Command("ajuda"))
    async def help_command(message: Message) -> None:
        await message.answer(HELP)

    @dispatcher.message(Command("adicionar_perfil"))
    async def add_profile(message: Message) -> None:
        argument = (message.text or "").split(maxsplit=1)
        if len(argument) != 2:
            await message.answer("Uso: /adicionar_perfil <URL ou ID>")
            return
        if len(database.profiles(owner_chat_id=message.chat.id)) >= settings.max_profiles:
            await message.answer(f"Limite atual: {settings.max_profiles} perfil(is). Remova um perfil antes de adicionar outro.")
            return
        try:
            url, seller_id = normalize_profile_url(argument[1])
            seller_name, _ = await client.fetch_profile(url, seller_id)
            profile_id = f"{message.chat.id}:{seller_id}"
            database.add_profile(Profile(profile_id, url, seller_name, datetime.now(timezone.utc), True, message.chat.id))
            await message.answer(f"✅ Perfil <b>{seller_name}</b> adicionado com sucesso!\nMonitoramento iniciado a cada {settings.check_interval_seconds}s.")
            await monitor.check_profile(profile_id)
        except Exception as error:
            logger.exception("Falha ao adicionar perfil")
            await message.answer(f"Não foi possível adicionar o perfil: {error}")

    @dispatcher.message(Command("listar_perfis"))
    async def list_profiles(message: Message) -> None:
        profiles = database.profiles(owner_chat_id=message.chat.id)
        if not profiles:
            await message.answer("Nenhum perfil monitorado.")
            return
        lines = []
        for index, profile in enumerate(profiles, 1):
            status = "ativo" if profile.active else "pausado"
            checked = profile.last_check.strftime("%d/%m %H:%M") if profile.last_check else "nunca"
            lines.append(f"{index}. {profile.seller_name} ({status})\n🔗 {profile.url}\n⏱️ Último check: {checked}")
        await message.answer("\n\n".join(lines))

    async def profile_from_index(message: Message) -> Profile | None:
        value = (message.text or "").split(maxsplit=1)
        if len(value) != 2 or not value[1].isdigit():
            await message.answer("Informe o número do perfil. Use /listar_perfis.")
            return None
        profiles = database.profiles(owner_chat_id=message.chat.id)
        index = int(value[1]) - 1
        if index < 0 or index >= len(profiles):
            await message.answer("Perfil não encontrado.")
            return None
        return profiles[index]

    @dispatcher.message(Command("pausar_perfil"))
    async def pause_profile(message: Message) -> None:
        profile = await profile_from_index(message)
        if profile:
            database.set_active(profile.id, False, message.chat.id)
            await message.answer(f"⏸️ Perfil {profile.seller_name} pausado.")

    @dispatcher.message(Command("retomar_perfil"))
    async def resume_profile(message: Message) -> None:
        profile = await profile_from_index(message)
        if profile:
            database.set_active(profile.id, True, message.chat.id)
            await message.answer(f"▶️ Perfil {profile.seller_name} retomado.")

    @dispatcher.message(Command("remover_perfil"))
    async def remove_profile(message: Message) -> None:
        profile = await profile_from_index(message)
        if profile:
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Confirmar remoção", callback_data=f"remove:{profile.id}"), InlineKeyboardButton(text="Cancelar", callback_data="remove:cancel")]])
            await message.answer(f"Você tem certeza que deseja remover {profile.seller_name}?", reply_markup=keyboard)

    @dispatcher.callback_query(F.data.startswith("remove:"))
    async def remove_callback(callback: CallbackQuery) -> None:
        if not callback.message:
            await callback.answer("Não autorizado.", show_alert=True)
            return
        profile_id = callback.data.split(":", 1)[1]
        if profile_id == "cancel":
            await callback.message.edit_text("Remoção cancelada.")
        else:
            database.remove_profile(profile_id, callback.message.chat.id)
            await callback.message.edit_text("✅ Perfil removido.")
        await callback.answer()

    @dispatcher.message(Command("historico"))
    async def history(message: Message) -> None:
        parts = (message.text or "").split()
        days = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 30
        rows = database.recent_products(days, owner_chat_id=message.chat.id)
        if not rows:
            await message.answer("Nenhum produto notificado nesse período.")
            return
        await message.answer("\n\n".join(f"🏷️ {row['title']}\n💰 {row['price'] or 'não informado'}\n🔗 {row['url']}" for row in rows))

    @dispatcher.message(Command("status"))
    async def status(message: Message) -> None:
        active = len(database.profiles(owner_chat_id=message.chat.id, active_only=True))
        await message.answer(f"✅ Bot online\nPerfis ativos: {active}\nIntervalo: {settings.check_interval_seconds}s")

    monitor_task = asyncio.create_task(monitor.run())
    try:
        await dispatcher.start_polling(bot)
    finally:
        monitor_task.cancel()
        await client.close()
        database.close()
        await bot.session.close()


if __name__ == "__main__":
    run()
