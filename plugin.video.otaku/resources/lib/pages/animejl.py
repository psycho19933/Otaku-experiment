# -*- coding: utf-8 -*-
import re
import urllib.parse
from bs4 import BeautifulSoup
from resources.lib.ui import client, control, database

class sources:
    def __init__(self):
        self.base_url = "https://anime-jl.net"
        self.search_url = "https://anime-jl.net/?s="

    def _get_html(self, url):
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Referer': self.base_url + '/',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8'
        }
        try:
            return client.request(url, headers=headers)
        except Exception:
            return None

    def _clean_title(self, title):
        if not title:
            return ""
        # Quitar paréntesis, corchetes y caracteres que rompen el buscador de WordPress
        clean = re.sub(r'\(.*?\)|\[.*?\]', '', title)
        clean = re.sub(r'[^\w\s]', ' ', clean)
        return " ".join(clean.split()).strip()

    def get_sources(self, anilist_id, mal_id, episode, status=None, media_type=None, rescrape=False, **kwargs):
        """
        Firma nativa de Otaku para invocar scrapers en resources/lib/pages/
        """
        sources_list = []
        episode = str(episode)

        # 1. Obtener los nombres del anime desde la base de datos interna de Otaku
        titles_to_try = []
        try:
            show = database.get_show(anilist_id)
            if show:
                if show.get('name'):
                    titles_to_try.append(show.get('name'))
                if show.get('ename'):
                    titles_to_try.append(show.get('ename'))
                # Sinónimos o nombres en español si existen
                alt_titles = show.get('titles', [])
                if isinstance(alt_titles, list):
                    titles_to_try.extend(alt_titles)
        except Exception:
            pass

        # Fallback si se pasaron títulos directamente por kwargs
        if not titles_to_try and 'titles' in kwargs:
            t = kwargs['titles']
            titles_to_try = list(t.values()) if isinstance(t, dict) else list(t)

        anime_url = None

        # 2. Buscar el anime en Anime-JL probando las variantes de título
        for t in titles_to_try:
            query = self._clean_title(t)
            if not query:
                continue

            search_url = f"{self.search_url}{urllib.parse.quote_plus(query)}"
            html = self._get_html(search_url)
            if not html:
                continue

            soup = BeautifulSoup(html, 'html.parser')

            # En Anime-JL los resultados se listan en <article> o divs con clase post/item
            for item in soup.select('article, .item, .post, .anime-card'):
                link = item.find('a', href=True)
                if not link:
                    continue
                href = link['href']

                # Evitar que tome un link directo a un episodio en la búsqueda general
                if '/episodio' not in href and '/ver/' not in href:
                    anime_url = href if href.startswith('http') else self.base_url + href
                    break
                elif not anime_url:
                    # Si no hay ficha de anime, tomar el enlace base
                    anime_url = href

            if anime_url:
                break

        if not anime_url:
            return sources_list

        # 3. Localizar el enlace del episodio específico
        ep_url = None
        anime_html = self._get_html(anime_url)
        if anime_html:
            soup_anime = BeautifulSoup(anime_html, 'html.parser')
            # Buscar en todos los enlaces de capítulos dentro de la ficha del anime
            for a in soup_anime.find_all('a', href=True):
                href = a['href']
                text = a.get_text().strip().lower()

                # Patrón que busca "episodio X", "capitulo X" o slugs como "-X/"
                ep_pattern = rf'(?:episodio|capitulo|cap)[^\d]*0*{episode}(?:[^\d]|$)'
                slug_pattern = rf'[-_/]0*{episode}/?$'

                if re.search(ep_pattern, text) or re.search(ep_pattern, href) or re.search(slug_pattern, href):
                    ep_url = href if href.startswith('http') else self.base_url + href
                    break

        # Si no lo halló en la ficha, probar búsqueda directa del episodio
        if not ep_url and titles_to_try:
            direct_search = f"{self.search_url}{urllib.parse.quote_plus(self._clean_title(titles_to_try[0]) + ' episodio ' + episode)}"
            search_html = self._get_html(direct_search)
            if search_html:
                soup_direct = BeautifulSoup(search_html, 'html.parser')
                first_res = soup_direct.select_one('article a, .item a, .post a')
                if first_res and first_res.get('href'):
                    ep_url = first_res['href']

        if not ep_url:
            return sources_list

        # 4. Extraer los reproductores de video (embeds/iframes)
        ep_html = self._get_html(ep_url)
        if not ep_html:
            return sources_list

        soup_ep = BeautifulSoup(ep_html, 'html.parser')
        raw_links = []

        # Extraer iframes directos
        for iframe in soup_ep.find_all('iframe'):
            src = iframe.get('src') or iframe.get('data-src')
            if src and not src.startswith(('about:', 'javascript:')):
                raw_links.append(src)

        # Extraer enlaces embebidos dentro de scripts o tabs del reproductor
        for script in soup_ep.find_all('script'):
            if script.string and any(k in script.string for k in ['streamwish', 'filemoon', 'mega.nz', 'streamtape', 'mp4upload']):
                urls = re.findall(r'(https?://[^\s"\'<>]+(?:streamwish|filemoon|mega\.nz|streamtape|mp4upload|yourupload)[^\s"\'<>]*)', script.string)
                raw_links.extend(urls)

        # 5. Formatear la lista según el estándar que Otaku espera
        seen = set()
        for link in raw_links:
            if link.startswith('//'):
                link = 'https:' + link

            if link in seen:
                continue
            seen.add(link)

            # Detectar el nombre del hoster para ResolveURL
            server_name = "Embed"
            low = link.lower()
            if "mega.nz" in low:
                server_name = "Mega"
            elif "streamwish" in low or "wishembed" in low:
                server_name = "Streamwish"
            elif "filemoon" in low:
                server_name = "Filemoon"
            elif "streamtape" in low:
                server_name = "Streamtape"
            elif "mp4upload" in low:
                server_name = "Mp4Upload"
            elif "yourupload" in low:
                server_name = "YourUpload"

            sources_list.append({
                'release_title': f"Anime-JL Ep {episode} [{server_name}]",
                'hash': '',
                'name': server_name,
                'quality': '1080p',
                'debrid_provider': '',
                'provider': 'animejl',
                'size': 'NA',
                'info': ['ES/LAT'],
                'lang': 2,           # 2 indica SUB / audio con subtítulos en Otaku
                'url': link,
                'direct': False      # Indica a Otaku que resuelva el link mediante ResolveURL
            })

        return sources_list
