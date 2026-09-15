from datetime import datetime, timezone

from app.database import Database
from app.models import Product, Profile


def product(product_id: str) -> Product:
    return Product(product_id, "Produto", "R$ 10", "", "", "", 0, None, "seller", "Vendedor", "https://www.olx.com.br/d/item")


def test_product_is_not_saved_twice(tmp_path):
    database = Database(tmp_path / "bot.sqlite3")
    database.add_profile(Profile("1:seller", "https://www.olx.com.br/usuarios/seller", "Vendedor", datetime.now(timezone.utc), True, 1))

    assert database.save_product("1:seller", product("item-1"), notified=True)
    assert not database.save_product("1:seller", product("item-1"), notified=True)

    assert len(database.recent_products()) == 1
    database.close()


def test_profile_can_be_paused(tmp_path):
    database = Database(tmp_path / "bot.sqlite3")
    database.add_profile(Profile("1:seller", "https://www.olx.com.br/usuarios/seller", "Vendedor", datetime.now(timezone.utc), True, 1))

    database.set_active("1:seller", False, 1)

    assert database.profiles(owner_chat_id=1, active_only=True) == []
    assert database.get_profile("1:seller", 1).active is False
    database.close()


def test_profiles_are_isolated_by_chat(tmp_path):
    database = Database(tmp_path / "bot.sqlite3")
    now = datetime.now(timezone.utc)
    database.add_profile(Profile("1:seller", "https://www.olx.com.br/usuarios/seller", "Vendedor", now, True, 1))
    database.add_profile(Profile("2:seller", "https://www.olx.com.br/usuarios/seller", "Vendedor", now, True, 2))

    assert len(database.profiles(owner_chat_id=1)) == 1
    assert len(database.profiles(owner_chat_id=2)) == 1
    assert database.profiles(owner_chat_id=3) == []
    database.close()
