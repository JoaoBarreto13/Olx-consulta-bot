from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Profile:
    id: str
    url: str
    seller_name: str
    added_at: datetime
    active: bool
    owner_chat_id: int = 0
    last_check: datetime | None = None


@dataclass(frozen=True)
class Product:
    id: str
    title: str
    price: str
    location: str
    category: str
    description: str
    image_count: int
    posted_at: datetime | None
    seller_id: str
    seller_name: str
    url: str
    status: str = "ativo"

    def notification_text(self) -> str:
        description = " ".join(self.description.split())[:100]
        if len(self.description) > 100:
            description += "..."
        posted = self.posted_at.strftime("%d/%m/%Y %H:%M") if self.posted_at else "não informado"
        return (
            f"🔔 NOVO PRODUTO - {self.seller_name}\n\n"
            f"🏷️ Título: {self.title}\n"
            f"💰 Preço: {self.price or 'não informado'}\n"
            f"📍 Localização: {self.location or 'não informado'}\n"
            f"🏢 Categoria: {self.category or 'não informado'}\n\n"
            f"📸 Fotos: {self.image_count}\n"
            f"✏️ Descrição: {description or 'não informada'}\n\n"
            f"🔗 Link: {self.url}\n"
            f"⏰ Postado em: {posted}\n\n"
            f"👤 Vendedor: {self.seller_name}"
        )
