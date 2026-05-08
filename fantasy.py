"""
Motor de pontuação da Fantasy Cycling.

Regras:
  - Cada participante escolhe 3 corredores antes da volta.
  - Em cada etapa, conta apenas o melhor corredor (menor posição).
  - Pontos da etapa = posição do melhor corredor.
  - Se o corredor ganhar a etapa (1.º), aplica-se um bónus de −50 pontos.
  - Objetivo: ter o menor total de pontos no final da volta.
"""

import json
import os

from config import (
    PARTICIPANTS_FILE,
    RESULTS_FILE,
    STAGE_WIN_BONUS,
)
from scraper import normalize_name


# ---------------------------------------------------------------------------
# Persistência
# ---------------------------------------------------------------------------

def load_participants() -> list[dict]:
    if not os.path.exists(PARTICIPANTS_FILE):
        return []
    with open(PARTICIPANTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_participants(participants: list[dict]) -> None:
    os.makedirs(os.path.dirname(PARTICIPANTS_FILE), exist_ok=True)
    with open(PARTICIPANTS_FILE, "w", encoding="utf-8") as f:
        json.dump(participants, f, ensure_ascii=False, indent=2)


def load_results() -> list[dict]:
    if not os.path.exists(RESULTS_FILE):
        return []
    with open(RESULTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_results(results: list[dict]) -> None:
    os.makedirs(os.path.dirname(RESULTS_FILE), exist_ok=True)
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Lógica de matching
# ---------------------------------------------------------------------------

def _names_match(participant_name_norm: str, result_name_norm: str) -> bool:
    """
    Verifica se o nome do participante corresponde ao nome do resultado.
    Estratégia: correspondência exacta, substring, ou pelo menos 2 palavras em comum.
    """
    if participant_name_norm in result_name_norm:
        return True
    if result_name_norm in participant_name_norm:
        return True
    # Correspondência por palavras: exige pelo menos 2 palavras em comum (>=3 chars)
    p_words = {w for w in participant_name_norm.split() if len(w) >= 3}
    r_words = {w for w in result_name_norm.split() if len(w) >= 3}
    return len(p_words & r_words) >= 2


def find_all_positions(
    participant_riders: list[str],
    stage_results: list[dict],
) -> list[dict]:
    """
    Devolve a posição de cada corredor do participante na etapa.
    Cada entrada: {rider_name, position} ou {rider_name, position: None}.
    """
    details = []
    for original_name in participant_riders:
        rider_norm = normalize_name(original_name)
        found = None
        for result in stage_results:
            if _names_match(rider_norm, result["rider_normalized"]):
                found = {"rider_name": result["rider"], "position": result["position"]}
                break
        if found is None:
            found = {"rider_name": original_name, "position": None}
        details.append(found)
    return details


def find_best_position(
    participant_riders: list[str],
    stage_results: list[dict],
) -> tuple[int, str] | None:
    """
    Devolve (posição, nome_corredor) para o melhor corredor do participante.
    Devolve None se nenhum corredor estiver classificado.
    """
    details = find_all_positions(participant_riders, stage_results)
    classified = [d for d in details if d["position"] is not None]
    if not classified:
        return None
    best = min(classified, key=lambda d: d["position"])
    return (best["position"], best["rider_name"])


# ---------------------------------------------------------------------------
# Pontuação
# ---------------------------------------------------------------------------

def calculate_stage_points(position: int) -> int:
    """Pontos de uma etapa = posição (+ bónus se vitória)."""
    return position + (STAGE_WIN_BONUS if position == 1 else 0)


def process_stage(stage_number: int, stage_results: list[dict]) -> list[dict]:
    """
    Calcula a pontuação de todos os participantes numa etapa.
    Devolve lista de dicts com os resultados individuais.
    """
    participants = load_participants()
    stage_scores = []

    for p in participants:
        best = find_best_position(p["riders"], stage_results)
        riders_detail = find_all_positions(p["riders"], stage_results)

        if best is None:
            stage_scores.append(
                {
                    "participant": p["name"],
                    "best_rider": None,
                    "position": None,
                    "stage_points": None,
                    "riders_detail": riders_detail,
                    "note": "Nenhum corredor classificado",
                }
            )
        else:
            position, rider = best
            points = calculate_stage_points(position)
            note = f"Vitória! Bónus {STAGE_WIN_BONUS} pts aplicado" if position == 1 else ""
            stage_scores.append(
                {
                    "participant": p["name"],
                    "best_rider": rider,
                    "position": position,
                    "stage_points": points,
                    "riders_detail": riders_detail,
                    "note": note,
                }
            )

    return stage_scores


# ---------------------------------------------------------------------------
# Classificação geral
# ---------------------------------------------------------------------------

def get_cumulative_rankings() -> list[dict]:
    """
    Devolve o ranking acumulado após cada etapa disputada.
    Resultado: lista de {stage, ranking: [{participant, total_points}]}
    ordenada por número de etapa.
    """
    results = load_results()
    participants = load_participants()

    cumulative: dict[str, int] = {p["name"]: 0 for p in participants}
    history = []

    for stage_data in sorted(results, key=lambda x: x["stage"]):
        for score in stage_data["scores"]:
            name = score["participant"]
            if score["stage_points"] is not None:
                cumulative[name] = cumulative.get(name, 0) + score["stage_points"]

        snapshot = sorted(
            [{"participant": n, "total_points": v} for n, v in cumulative.items()],
            key=lambda x: x["total_points"],
        )
        history.append({"stage": stage_data["stage"], "ranking": snapshot})

    return history


def get_total_scores() -> list[dict]:
    """
    Soma os pontos de todas as etapas processadas e devolve o ranking ordenado
    (menor total = melhor classificação).
    """
    results = load_results()
    participants = load_participants()

    totals: dict[str, int] = {p["name"]: 0 for p in participants}
    stages_counted: dict[str, int] = {p["name"]: 0 for p in participants}

    for stage in results:
        for score in stage["scores"]:
            name = score["participant"]
            if score["stage_points"] is not None:
                totals[name] = totals.get(name, 0) + score["stage_points"]
                stages_counted[name] = stages_counted.get(name, 0) + 1

    ranking = [
        {
            "participant": name,
            "total_points": points,
            "stages_scored": stages_counted.get(name, 0),
        }
        for name, points in totals.items()
    ]
    ranking.sort(key=lambda x: x["total_points"])
    return ranking
