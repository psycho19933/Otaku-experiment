# -*- coding: utf-8 -*-
import re
import urllib.parse
import urllib.request
from bs4 import BeautifulSoup

class Sources:
    def __init__(self):
        self.base_url = "https://anime-jl.net"
        self.search_url = "https://anime-jl.net/?s="
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
            'Referer': 'https://anime-jl.net/'
        }

    def _http_get(self, url):
        """Realiza peticiones HTTP simulando un navegador."""
        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.read().decode('utf-8', errors='ignore')
        except Exception:
            return None

    def _clean_title(self, title):
        """Limpia caracteres especiales para mejorar la búsqueda."""
        if not title:
            return ""
        title = re.sub(r'\(.*?\)|\[.*?\]', '', title)
        title = re.sub(r'[^\w\s]', ' ', title)
        return " ".join(title.split()).strip()

    def get_sources(self, *args, **kwargs):
        """
        Punto de entrada compatible con Otaku.
        Soporta argumentos posicionales o por nombre (titles, episode, etc.)
        """
        titles = []
        episode = "1"

        # Otaku suele pasar: get_sources(titles, episode, ...)
        if len(args) >= 1:
            if isinstance(args[0], dict):
                titles.extend([v for v in args[0].values() if isinstance(v, str)])
            elif isinstance(args[0], list):
                titles.extend(args[0])
            elif isinstance(args[0], str):
                titles.append(args[0])

        if len(args) >= 2:
            episode = str(args[1])
        elif 'episode' in kwargs:
            episode = str(kwargs['episode'])

        if 'titles' in kwargs:
            t = kwargs['titles']
            if isinstance(t, dict):
                titles.extend([v for v in t.values() if isinstance(v, str)])
            elif isinstance(t, list):
                titles.extend(t)

        sources = []
        anime_urls = []

        # 1. Buscar en Anime-JL probando las variantes del título
        for t in titles:
            clean = self._clean_title(t)
            if not clean:
                continue
            search_query = urllib.parse.quote_plus(clean)
            html = self._http_get(f"{self.search_url}{search_query}")
            if not html:
                continue

            soup = BeautifulSoup(html, 'html.parser')

            # Anime-JL lista los resultados dentro de artículos / tarjetas
            for card in soup.select('article, .item, .post, .animelist-item'):
                link = card.find('a', href=True)
                if link and '/ver/' not in link['href']:  # Evitar episodios sueltos en el buscador
                    href = link['href']
                    if href.startswith('/'):
                        href = self.base_url + href
                    if href not in anime_urls:
                        anime_urls.append(href)

            if anime_urls:
                break

        if not anime_urls:
            return sources

        # 2. Localizar el episodio objetivo
        ep_url = None
        target_ep = str(episode)

        for a_url in anime_urls:
            anime_html = self._http_get(a_url)
            if not anime_html:
                continue

            soup_anime = BeautifulSoup(anime_html, 'html.parser')
            # Buscar todos los enlaces a episodios
            ep_links = soup_anime.find_all('a', href=True)
            for a in ep_links:
                href = a['href']
                text = a.get_text()

                # Coincidencia por URL (ej: /episodio-48 o -48/) o por texto (ej: "Episodio 48")
                pattern = rf'(?:episodio|capitulo|cap)[^\d]*0*{target_ep}(?:[^\d]|$)'
                if re.search(pattern, href, re.IGNORECASE) or re.search(pattern, text, re.IGNORECASE):
                    ep_url = href if href.startswith('http') else self.base_url + href
                    break

            if ep_url:
                break

        if not ep_url:
            return sources

        # 3. Extraer enlaces de los reproductores del episodio
        ep_html = self._http_get(ep_url)
        if not ep_html:
            return sources

        soup_ep = BeautifulSoup(ep_html, 'html.parser')

        raw_embeds = []

        # a) Buscar iframes directos
        for iframe in soup_ep.find_all('iframe'):
            src = iframe.get('src') or iframe.get('data-src')
            if src and not src.startswith(('about:', 'javascript:')):
                raw_embeds.append(src)

        # b) Buscar scripts con data de servidores (ej. pestañas tab / video lists)
        for s in soup_ep.find_all('script'):
            if s.string and ('video' in s.string or 'player' in s.string):
                found = re.findall(r'(https?://[^\s"\'<>]+(?:streamwish|filemoon|mega\.nz|mp4upload|dood|streamtape)[^\s"\'<>]*)', s.string)
                raw_embeds.extend(found)

        # 4. Formatear para Kodi / Otaku
        seen = set()
        for link in raw_embeds:
            if link.startswith('//'):
                link = 'https:' + link

            if link in seen:
                continue
            seen.add(link)

            # Identificar nombre del servidor
            server_name = "Embed"
            lower_link = link.lower()
            if "mega.nz" in lower_link:
                server_name = "Mega"
            elif "streamwish" in lower_link or "wishembed" in lower_link:
                server_name = "Streamwish"
            elif "filemoon" in lower_link:
                server_name = "Filemoon"
            elif "mp4upload" in lower_link:
                server_name = "Mp4Upload"
            elif "streamtape" in lower_link:
                server_name = "Streamtape"
            elif "yourupload" in lower_link:
                server_name = "YourUpload"

            sources.append({
                'release_title': f"Anime-JL Ep {episode} [{server_name}]",
                'name': server_name,
                'source': server_name,
                'quality': '1080p',
                'language': 'es',
                'url': link,
                'provider': 'animejl',
                'direct': False,       # Indica a Otaku que use ResolveURL
                'debridonly': False,
                'hash': '',
                'size': 'NA',
                'info': ['LAT/SUB']
            })

        return sources