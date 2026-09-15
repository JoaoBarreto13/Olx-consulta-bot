import json
import logging
import re
from datetime import datetime
from urllib.parse import urlparse

from curl_cffi.requests import AsyncSession
from bs4 import BeautifulSoup

from .models import Product

logger = logging.getLogger(__name__)

OLX_HOSTS = {"olx.com.br", "www.olx.com.br"}
PRODUCT_PATH = re.compile(r"/(?:d|item)/([^/?#]+)", re.IGNORECASE)


def normalize_profile_url(value: str) -> tuple[str, str]:
    value = value.strip()
    if not value:
        raise ValueError("Informe a URL ou o ID do vendedor.")
    if re.fullmatch(r"[A-Za-z0-9_-]+", value):
        value = f"https://www.olx.com.br/usuarios/{value}"
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in OLX_HOSTS:
        raise ValueError("A URL deve pertencer a www.olx.com.br.")
    parts = [part for part in parsed.path.split("/") if part]
    if not parts or parts[0].lower() not in {"usuarios", "usuario", "perfil", "user"}:
        raise ValueError("Use o link público do perfil, por exemplo: https://www.olx.com.br/usuarios/123.")
    seller_id = parts[-1]
    clean_url = f"https://www.olx.com.br/{parts[0]}/{seller_id}"
    return clean_url, seller_id


class OlxClient:
    def __init__(self, timeout: float = 20.0):
        self.session = AsyncSession(
            timeout=timeout,
            allow_redirects=True,
            impersonate="chrome",
        )

    async def close(self) -> None:
        await self.session.close()

    async def fetch_profile(self, profile_url: str, seller_id: str, seller_name: str = "") -> tuple[str, list[Product]]:
        response = await self.session.get(profile_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # Extrair dados do __NEXT_DATA__ (Next.js SSR)
        next_data = soup.find("script", id="__NEXT_DATA__")
        if next_data:
            try:
                data = json.loads(next_data.string or "{}")
                page_props = data.get("props", {}).get("pageProps", {})
                return self._parse_next_data(page_props, seller_id, seller_name)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Falha ao parsear __NEXT_DATA__: %s", e)

        # Fallback: tentar extrair do <title> e ld+json (páginas antigas)
        discovered_name = self._seller_name(soup) or seller_name or seller_id
        return discovered_name, []

    @staticmethod
    def _parse_next_data(page_props: dict, seller_id: str, fallback_name: str) -> tuple[str, list[Product]]:
        """Extrai nome do vendedor e produtos do __NEXT_DATA__ da OLX."""
        # Nome do vendedor
        profile_data = page_props.get("sellerProfileData", {})
        seller_name = profile_data.get("name", "") or fallback_name or seller_id
        seller_name = seller_name.strip()[:120]

        # Produtos: pageProps.ads.content
        ads_data = page_props.get("ads", {})
        ads_content = ads_data.get("content", []) if isinstance(ads_data, dict) else []

        products: list[Product] = []
        for ad in ads_content:
            if not isinstance(ad, dict):
                continue

            # ID do produto (listId)
            list_id = str(ad.get("listId", ""))
            if not list_id:
                continue

            # Link do anúncio
            link = ad.get("link", "")
            if not link:
                continue

            # Preço
            price_val = ad.get("price")
            if price_val:
                price = f"R$ {price_val}" if not str(price_val).startswith("R$") else str(price_val)
            else:
                price = ""

            # Localização
            location_parts = []
            loc = ad.get("location", "")
            if isinstance(loc, str) and loc:
                location_parts.append(loc)
            loc_distinct = ad.get("location_distinct", "")
            if isinstance(loc_distinct, str) and loc_distinct:
                location_parts.append(loc_distinct)
            location = ", ".join(location_parts) if location_parts else ""

            # Categoria (buscar nas properties)
            category = ""
            for prop in ad.get("properties", []):
                if isinstance(prop, dict) and prop.get("name") == "category":
                    category = prop.get("value", "")
                    break

            # Imagens
            image_list = ad.get("imageList", [])
            image_count = ad.get("numberOfImages", len(image_list) if isinstance(image_list, list) else 0)

            # Data de publicação
            posted_at = _parse_date(ad.get("date"))

            products.append(Product(
                id=list_id,
                title=ad.get("title", "Anúncio OLX")[:300],
                price=price,
                location=location,
                category=category,
                description=ad.get("description", ""),
                image_count=image_count,
                posted_at=posted_at,
                seller_id=seller_id,
                seller_name=seller_name,
                url=link.split("?")[0],
            ))

        logger.debug("__NEXT_DATA__: vendedor='%s', %d produto(s) extraído(s).", seller_name, len(products))
        return seller_name, products

    @staticmethod
    def _seller_name(soup: BeautifulSoup) -> str:
        for selector in ("h1", "meta[property='og:title']", "title"):
            node = soup.select_one(selector)
            value = node.get("content", "") if node and node.name == "meta" else node.get_text(" ", strip=True) if node else ""
            if value:
                return value.replace(" - OLX", "").replace("Perfil - ", "").strip()[:120]
        return ""


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
