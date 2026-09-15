import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import Product, Profile


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                id TEXT PRIMARY KEY,
                owner_chat_id INTEGER NOT NULL,
                url TEXT NOT NULL,
                seller_name TEXT NOT NULL,
                added_at TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                last_check TEXT
            );
            CREATE TABLE IF NOT EXISTS products (
                id TEXT NOT NULL,
                profile_id TEXT NOT NULL,
                title TEXT NOT NULL,
                price TEXT,
                location TEXT,
                category TEXT,
                description TEXT,
                image_count INTEGER NOT NULL DEFAULT 0,
                posted_at TEXT,
                seller_id TEXT,
                seller_name TEXT,
                url TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ativo',
                notified_at TEXT,
                FOREIGN KEY(profile_id) REFERENCES profiles(id),
                PRIMARY KEY (id, profile_id)
            );
            """
        )
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(profiles)")}
        if "owner_chat_id" not in columns:
            self.connection.execute("ALTER TABLE profiles ADD COLUMN owner_chat_id INTEGER NOT NULL DEFAULT 0")
        self.connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS profiles_owner_url ON profiles(owner_chat_id, url)")
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def profiles(self, owner_chat_id: int | None = None, active_only: bool = False) -> list[Profile]:
        clauses = []
        parameters: list[object] = []
        if owner_chat_id is not None:
            clauses.append("owner_chat_id = ?")
            parameters.append(owner_chat_id)
        if active_only:
            clauses.append("active = 1")
        query = "SELECT * FROM profiles"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY added_at"
        rows = self.connection.execute(query, parameters).fetchall()
        return [self._profile(row) for row in rows]

    def get_profile(self, profile_id: str, owner_chat_id: int | None = None) -> Profile | None:
        query = "SELECT * FROM profiles WHERE id = ?"
        parameters: list[object] = [profile_id]
        if owner_chat_id is not None:
            query += " AND owner_chat_id = ?"
            parameters.append(owner_chat_id)
        row = self.connection.execute(query, parameters).fetchone()
        return self._profile(row) if row else None

    def add_profile(self, profile: Profile) -> None:
        self.connection.execute(
            "INSERT INTO profiles (id, owner_chat_id, url, seller_name, added_at, active) VALUES (?, ?, ?, ?, ?, ?)",
            (profile.id, profile.owner_chat_id, profile.url, profile.seller_name, profile.added_at.isoformat(), int(profile.active)),
        )
        self.connection.commit()

    def remove_profile(self, profile_id: str, owner_chat_id: int | None = None) -> None:
        query = "DELETE FROM profiles WHERE id = ?"
        parameters: list[object] = [profile_id]
        if owner_chat_id is not None:
            query += " AND owner_chat_id = ?"
            parameters.append(owner_chat_id)
        self.connection.execute(query, parameters)
        self.connection.commit()

    def set_active(self, profile_id: str, active: bool, owner_chat_id: int | None = None) -> None:
        query = "UPDATE profiles SET active = ? WHERE id = ?"
        parameters: list[object] = [int(active), profile_id]
        if owner_chat_id is not None:
            query += " AND owner_chat_id = ?"
            parameters.append(owner_chat_id)
        self.connection.execute(query, parameters)
        self.connection.commit()

    def update_last_check(self, profile_id: str) -> None:
        self.connection.execute(
            "UPDATE profiles SET last_check = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), profile_id),
        )
        self.connection.commit()

    def has_products_for_profile(self, profile_id: str) -> bool:
        row = self.connection.execute("SELECT 1 FROM products WHERE profile_id = ? LIMIT 1", (profile_id,)).fetchone()
        return row is not None

    def save_product(self, profile_id: str, product: Product, notified: bool) -> bool:
        now = datetime.now(timezone.utc).isoformat() if notified else None
        cursor = self.connection.execute(
            """INSERT OR IGNORE INTO products
            (id, profile_id, title, price, location, category, description, image_count,
             posted_at, seller_id, seller_name, url, status, notified_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (product.id, profile_id, product.title, product.price, product.location, product.category,
             product.description, product.image_count, product.posted_at.isoformat() if product.posted_at else None,
             product.seller_id, product.seller_name, product.url, product.status, now),
        )
        self.connection.commit()
        return cursor.rowcount > 0

    def recent_products(self, days: int = 30, limit: int = 20, owner_chat_id: int | None = None) -> list[sqlite3.Row]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        query = """SELECT products.* FROM products
                   JOIN profiles ON profiles.id = products.profile_id
                   WHERE products.notified_at IS NOT NULL AND products.notified_at >= ?"""
        parameters: list[object] = [since]
        if owner_chat_id is not None:
            query += " AND profiles.owner_chat_id = ?"
            parameters.append(owner_chat_id)
        query += " ORDER BY products.notified_at DESC LIMIT ?"
        parameters.append(limit)
        return self.connection.execute(query, parameters).fetchall()

    @staticmethod
    def _profile(row: sqlite3.Row) -> Profile:
        return Profile(
            id=row["id"], url=row["url"], seller_name=row["seller_name"],
            owner_chat_id=row["owner_chat_id"],
            added_at=datetime.fromisoformat(row["added_at"]), active=bool(row["active"]),
            last_check=datetime.fromisoformat(row["last_check"]) if row["last_check"] else None,
        )
