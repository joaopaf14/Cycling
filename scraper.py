"""
Scraper para procyclingstats.com — obtém resultados de etapas de uma corrida (config.RACE_SLUG).
Usa cloudscraper para contornar a proteção Cloudflare do PCS.
"""

import os
import time
import unicodedata

import cloudscraper
import requests
from bs4 import BeautifulSoup

from config import PCS_BASE_URL, RACE_SLUG, RACE_YEAR

# Se definida (ex.: secret do GitHub Actions), usada como último recurso quando o
# pedido direto falha sempre — encaminha o pedido através de um serviço de
# "unblocking" (ScraperAPI-compatível: GET https://api.scraperapi.com/?api_key=...&url=...)
# em vez de sair diretamente do IP do runner.
PROXY_API_KEY = os.environ.get("SCRAPER_API_KEY")
PROXY_ENDPOINT = "https://api.scraperapi.com/"


def normalize_name(name: str) -> str:
    """Normaliza nome: minúsculas, sem acentos, espaços simples."""
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    return " ".join(name.lower().split())


def pcs_to_standard_name(pcs_name: str) -> str:
    """
    Converte o formato PCS ('POGACAR Tadej') para formato legível ('Tadej Pogacar').
    Também lida com apelidos compostos ('VAN DER POEL Mathieu' → 'Mathieu Van Der Poel').
    """
    parts = pcs_name.strip().split()
    if not parts:
        return pcs_name

    # O PCS coloca o apelido em maiúsculas no início
    i = 0
    while i < len(parts) and parts[i].isupper():
        i += 1

    last_name = " ".join(parts[:i]) if i > 0 else parts[0]
    first_name = " ".join(parts[i:]) if i < len(parts) else ""

    if first_name:
        return f"{first_name} {last_name.title()}"
    return last_name.title()


def get_stage_results(stage_number: int) -> list[dict]:
    """
    Obtém os resultados de uma etapa do PCS via cloudscraper.
    Devolve lista de dicts com {position, rider, rider_normalized}.
    """
    url = f"{PCS_BASE_URL}/race/{RACE_SLUG}/{RACE_YEAR}/stage-{stage_number}/result/result"
    return _fetch_and_parse(url, stage_number, label="resultados")


def get_gc_results(stage_number: int) -> list[dict]:
    """
    Obtém a Classificação Geral (GC) individual após uma etapa, em vez do
    resultado da própria etapa.

    Útil para etapas como um CRE (contrarrelógio por equipas), em que o
    resultado da etapa em si é organizado por equipa e não reflecte bem a
    posição individual de cada corredor — a GC após essa etapa já vem
    ordenada por corredor.
    """
    url = f"{PCS_BASE_URL}/race/{RACE_SLUG}/{RACE_YEAR}/stage-{stage_number}-gc"
    return _fetch_and_parse(url, stage_number, label="classificação geral")


def _parse_and_validate(html: str, stage_number: int, label: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results = _parse_results(soup)

    if not results:
        raise ValueError(
            f"Sem {label} para a etapa {stage_number}. "
            "A etapa ainda não foi disputada ou a estrutura da página mudou."
        )

    return sorted(results, key=lambda x: x["position"])


def _fetch_direct(url: str) -> str:
    scraper = cloudscraper.create_scraper()
    resp = scraper.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def _fetch_via_proxy(url: str) -> str:
    """
    Vai buscar a página através de um serviço externo de 'unblocking', em vez de
    diretamente — útil quando o IP do runner (ex.: GitHub Actions) está a ser
    bloqueado pela Cloudflare do PCS, algo que não controlamos.
    Só é chamada se SCRAPER_API_KEY estiver definida (ex.: como secret do GitHub).
    """
    resp = requests.get(
        PROXY_ENDPOINT,
        params={"api_key": PROXY_API_KEY, "url": url},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.text


def _fetch_and_parse(url: str, stage_number: int, label: str, max_attempts: int = 3) -> list[dict]:
    last_exc: Exception | None = None

    # 1) Tentativas diretas (com pequeno backoff entre elas)
    for attempt in range(1, max_attempts + 1):
        try:
            html = _fetch_direct(url)
            return _parse_and_validate(html, stage_number, label)
        except ValueError:
            # Sem dados = etapa ainda não disputada. Repetir não vai ajudar.
            raise
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts:
                time.sleep(5 * attempt)

    # 2) Último recurso: se houver um proxy configurado, tenta por aí
    #    (ex.: bloqueio persistente de IP que os retries diretos não resolvem)
    if PROXY_API_KEY:
        try:
            html = _fetch_via_proxy(url)
            return _parse_and_validate(html, stage_number, label)
        except ValueError:
            raise
        except Exception as exc:
            last_exc = exc

    raise last_exc


def _parse_results(soup: BeautifulSoup) -> list[dict]:
    """
    Percorre todas as tabelas HTML à procura de linhas com posição numérica
    e um link de corredor (/rider/).
    """
    results = []
    seen_positions = set()

    for table in soup.find_all("table"):
        table_results = []
        rows = table.find_all("tr")

        for row in rows:
            cols = row.find_all("td")
            if not cols:
                continue

            pos_text = cols[0].get_text(strip=True)
            if not pos_text.isdigit():
                continue
            position = int(pos_text)
            if position in seen_positions:
                continue

            # Procura link de corredor em qualquer coluna da linha
            rider_link = row.find("a", href=lambda h: h and "rider/" in h)
            if not rider_link:
                continue

            # O PCS usa <span class="uppercase">Lastname</span> Firstname
            last_span = rider_link.find("span", class_="uppercase")
            if last_span:
                last_name = last_span.get_text(strip=True)
                # Primeiro nome: texto que não está dentro do span
                last_span.extract()
                first_name = rider_link.get_text(strip=True)
                pcs_name = f"{last_name.upper()} {first_name}".strip()
            else:
                pcs_name = rider_link.get_text(separator=" ", strip=True)
            standard_name = pcs_to_standard_name(pcs_name)

            table_results.append(
                {
                    "position": position,
                    "rider": standard_name,
                    "rider_normalized": normalize_name(pcs_name),
                }
            )
            seen_positions.add(position)

        if len(table_results) >= 10:
            results = table_results
            break

    return results
