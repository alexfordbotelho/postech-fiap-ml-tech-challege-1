import pandas as pd
from bs4 import BeautifulSoup
import json
import asyncio
import aiohttp
from typing import List, Dict, Optional
import logging
import datetime
from urllib.parse import urljoin, urlparse
import time
from pathlib import Path
from app.connection import Connection

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    # handlers=[
    #     logging.FileHandler(
    #         f"{Path.cwd()}/logs/extract/webscrapper_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_v3.log"),
    #     logging.StreamHandler()
    # ]
    )
logger = logging.getLogger(__name__)


class WebScraperAsync:
    """Versão assíncrona e otimizada do scraper com suporte a paginação"""

    def __init__(self, base_url: str, max_concurrent: int = 10):
        self.base_url = base_url.rstrip('/')
        self.max_concurrent = max_concurrent
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.close()

    async def fetch_page(self, url: str) -> Optional[str]:
        """Busca uma página de forma assíncrona"""
        try:
            async with self.session.get(url, ssl=False) as response:
                if response.status == 200:
                    return await response.text()
                logger.warning(f"Status {response.status} para {url}")
                return None
        except Exception as e:
            logger.error(f"Erro ao buscar {url}: {e}")
            return None

    def parse_catalog_links(self, html: str) -> List[Dict]:
        """Extrai links do catálogo"""
        soup = BeautifulSoup(html, 'html.parser')
        links = []

        for a in soup.find_all('a', href=True):
            href = a.get('href', '')
            text = a.get_text(strip=True)

            if 'catalogue/category' in href and text:
                links.append({
                    'text': text,
                    'link': urljoin(self.base_url, href)
                })

        return links

    def get_next_page_url(self, html: str, current_url: str) -> Optional[str]:
        """Extrai o URL da próxima página se existir"""
        soup = BeautifulSoup(html, 'html.parser')

        # Procurar pelo botão "next" na paginação
        next_li = soup.find('li', class_='next')
        if next_li:
            next_link = next_li.find('a')
            if next_link:
                next_href = next_link.get('href', '')
                if next_href:
                    # Construir URL completo para a próxima página
                    # A URL pode ser relativa, então precisamos construí-la corretamente
                    if next_href.startswith('http'):
                        return next_href
                    else:
                        # Pegar a URL base da categoria atual
                        base_category_url = '/'.join(current_url.split('/')[:-1]) + '/'
                        return urljoin(base_category_url, next_href)

        return None

    def parse_products_from_catalog(self, html: str, catalog_name: str) -> List[Dict]:
        """Extrai produtos de uma página de catálogo"""
        soup = BeautifulSoup(html, 'html.parser')
        list_rows_product = soup.find_all('ol', class_='row')
        products = []

        for list_rows in list_rows_product:
            list_product = list_rows.find_all(class_='product_pod')
            for product in list_product:
                try:
                    # Extrair informações básicas
                    image_container = product.find(class_='image_container')
                    if not image_container:
                        continue

                    img_elem = image_container.find('img')
                    link_elem = image_container.find('a')

                    if img_elem and link_elem:
                        image_url = urljoin(self.base_url, img_elem.get('src', ''))
                        detail_url = urljoin(self.base_url,
                                             link_elem.get('href').replace('../../../', 'catalogue/').replace('../../',
                                                                                                              'catalogue/'))

                        # Informações básicas do produto
                        title_elem = product.find('h3')
                        title = title_elem.get_text(strip=True) if title_elem else 'No title'

                        price_elem = product.find('p', class_='price_color')
                        price = price_elem.get_text(strip=True) if price_elem else 'No price'

                        products.append({
                            'catalog': catalog_name,
                            'image': image_url,
                            'title': title,
                            'price': price,
                            'detail_url': detail_url
                        })

                except Exception as e:
                    logger.error(f"Erro ao processar produto: {e}")
                    continue

        return products

    async def scrape_catalog_with_pagination(self, catalog_info: Dict) -> List[Dict]:
        """Scraping de um catálogo incluindo todas as páginas"""
        all_products = []
        current_url = catalog_info['link']
        catalog_name = catalog_info['text']
        page_num = 1

        logger.info(f"Iniciando scraping do catálogo: {catalog_name}")

        while current_url:
            logger.info(f"  Página {page_num} do catálogo {catalog_name}")

            # Buscar a página atual
            html = await self.fetch_page(current_url)
            if not html:
                break

            # Extrair produtos da página atual
            products = self.parse_products_from_catalog(html, catalog_name)
            all_products.extend(products)
            logger.info(f"    Encontrados {len(products)} produtos na página {page_num}")

            # Verificar se há próxima página
            next_url = self.get_next_page_url(html, current_url)
            if next_url:
                current_url = next_url
                page_num += 1
                # Pequena pausa para não sobrecarregar o servidor
                await asyncio.sleep(0.1)
            else:
                logger.info(f"  Finalizado catálogo {catalog_name} - Total: {len(all_products)} produtos")
                break

        return all_products

    def parse_product_details(self, html: str) -> Dict:
        """Extrai detalhes de um produto"""
        soup = BeautifulSoup(html, 'html.parser')
        details = {}

        try:
            # Título
            h1 = soup.find('h1')
            details['title'] = h1.get_text(strip=True) if h1 else 'No title'

            # Descrição
            article = soup.find('article', class_='product_page')
            if article:
                desc_elem = article.find('p', recursive=False)
                details['description'] = desc_elem.get_text(strip=True) if desc_elem else 'No description'

            # Tabela de informações
            info_fields = {
                'UPC': 'upc',
                'Product Type': 'product_type',
                'Price (excl. tax)': 'price_excl_tax',
                'Price (incl. tax)': 'price_incl_tax',
                'Tax': 'tax',
                'Availability': 'availability',
                'Number of reviews': 'number_of_reviews'
            }

            for label, field_name in info_fields.items():
                th = soup.find('th', string=label)
                if th:
                    td = th.find_next_sibling('td')
                    details[field_name] = td.get_text(strip=True) if td else 'N/A'
                else:
                    details[field_name] = 'N/A'

        except Exception as e:
            logger.error(f"Erro ao processar detalhes: {e}")

        return details

    async def scrape_all(self, limit_products: Optional[int] = None, skip_categories: List[str] = None) -> List[Dict]:
        """
        Executa o scraping completo com paginação

        Args:
            limit_products: Limita o número total de produtos a serem coletados
            skip_categories: Lista de categorias para pular (ex: ['Books'])
        """
        start_time = time.time()
        skip_categories = skip_categories or []

        # 1. Buscar página principal
        logger.info("Buscando página principal...")
        main_html = await self.fetch_page(self.base_url)
        if not main_html:
            logger.error("Falha ao buscar página principal")
            return []

        # 2. Extrair links dos catálogos
        catalog_links = self.parse_catalog_links(main_html)

        # Filtrar categorias se necessário
        if skip_categories:
            catalog_links = [cat for cat in catalog_links if cat['text'] not in skip_categories]

        logger.info(f"Encontrados {len(catalog_links)} catálogos para processar")

        # 3. Buscar páginas dos catálogos com paginação
        all_products = []
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def fetch_catalog_with_semaphore(catalog_info):
            async with semaphore:
                return await self.scrape_catalog_with_pagination(catalog_info)

        # Processar todos os catálogos em paralelo (com controle de concorrência)
        catalog_tasks = [fetch_catalog_with_semaphore(cat) for cat in catalog_links]
        catalog_results = await asyncio.gather(*catalog_tasks)

        for products in catalog_results:
            all_products.extend(products)

            # Se já temos produtos suficientes, parar de adicionar
            if limit_products and len(all_products) >= limit_products:
                all_products = all_products[:limit_products]
                break

        logger.info(f"Encontrados {len(all_products)} produtos no total")

        # Limitar número de produtos se especificado
        if limit_products and len(all_products) > limit_products:
            all_products = all_products[:limit_products]
            logger.info(f"Limitado a {limit_products} produtos conforme solicitado")

        # 4. Buscar detalhes dos produtos
        async def fetch_product_details(product):
            async with semaphore:
                html = await self.fetch_page(product['detail_url'])
                if html:
                    product['details'] = self.parse_product_details(html)
                return product

        logger.info(f"Buscando detalhes de {len(all_products)} produtos...")

        # Processar em lotes para evitar sobrecarga
        batch_size = 50
        final_products = []

        for i in range(0, len(all_products), batch_size):
            batch = all_products[i:i + batch_size]
            logger.info(
                f"Processando lote {i // batch_size + 1} de {(len(all_products) + batch_size - 1) // batch_size}")

            detail_tasks = [fetch_product_details(prod) for prod in batch]
            batch_results = await asyncio.gather(*detail_tasks)
            final_products.extend(batch_results)

            # Pequena pausa entre lotes
            if i + batch_size < len(all_products):
                await asyncio.sleep(0.5)

        elapsed_time = time.time() - start_time
        logger.info(f"Scraping completo em {elapsed_time:.2f} segundos")
        logger.info(f"Total de produtos coletados: {len(final_products)}")

        return final_products


async def main_async():
    """Função principal para executar o scraper"""
    async with WebScraperAsync('https://books.toscrape.com/', max_concurrent=20) as scraper:
        # Você pode configurar para pular categorias específicas ou limitar produtos
        skip_categories = ['Books']  # Descomente para pular a categoria Books
        # skip_categories = []  # Processar todas as categorias

        products = await scraper.scrape_all(
            limit_products=None,  # Defina um número para limitar, ou None para todos
            skip_categories=skip_categories
        )

        # Salvar no MongoDB
        if products:
            try:
                mongoInsert = [d.copy() for d in products]
                collection = Connection().get_collection('books_async_paginated')
               
                if await collection.count_documents({}) > 0:
                    await collection.drop()
                    logger.info("Coleção existente removida antes do novo insert.")
               
                result = await collection.insert_many(mongoInsert)
                logger.info(f"Insert completo no MongoDB: {len(result.inserted_ids)} documentos")
            except Exception as e:
                logger.error(f"Erro ao inserir no MongoDB: {e}")

        # Salvar em arquivo JSON
        # output_file = f'{Path.cwd()}/output/products_async_paginated_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}_v3.json'
        # with open(output_file, 'w', encoding='utf-8') as f:
        #     json.dump(products, f, indent=2, ensure_ascii=False)

        # logger.info(f"Scraped {len(products)} produtos salvos em {output_file}")

        # Estatísticas por categoria
        from collections import Counter
        category_counts = Counter(p['catalog'] for p in products)
        logger.info("Produtos por categoria:")
        for category, count in category_counts.most_common():
            logger.info(f"  {category}: {count} produtos")

        return products

# if __name__ == "__main__":
#     asyncio.run(main_async())