"""
Scraper para procyclingstats.com — obtém resultados de etapas do Giro d'Italia.
"""

import unicodedata

import requests
from bs4 import BeautifulSoup

from config import PCS_BASE_URL, RACE_SLUG, RACE_YEAR


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
    Obtém os resultados de uma etapa do PCS.
    Devolve lista de dicts com {position, rider, rider_normalized}.
    """
    url = f"{PCS_BASE_URL}/race/{RACE_SLUG}/{RACE_YEAR}/stage-{stage_number}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
    }

    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    results = _parse_results(soup)

    if not results:
        raise ValueError(
            f"Sem resultados para a etapa {stage_number}. "
            "A etapa ainda não foi disputada ou a estrutura da página mudou."
        )

    return sorted(results, key=lambda x: x["position"])


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
            rider_link = row.find("a", href=lambda h: h and "/rider/" in h)
            if not rider_link:
                continue

            pcs_name = rider_link.get_text(strip=True)
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
