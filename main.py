#!/usr/bin/env python3
"""
Fantasy Cycling — Tour de France 2026
CLI principal.

Utilização:
  python main.py setup                  # Registar participantes e corredores
  python main.py update <etapa>         # Buscar resultados e calcular pontos
  python main.py update <etapa> --force # Substituir etapa já processada
  python main.py ranking                # Ver classificação geral
  python main.py stage <etapa>          # Detalhes de uma etapa
  python main.py participants           # Listar participantes
  python main.py export                 # Gerar index.html para partilhar
"""

import argparse
import sys

from config import RACE_NAME, RACE_YEAR, RIDERS_PER_PARTICIPANT, TOTAL_STAGES
from export_html import generate_html
from fantasy import (
    get_total_scores,
    load_participants,
    load_results,
    process_stage,
    save_participants,
    save_results,
)
from scraper import get_gc_results, get_stage_results

# ---------------------------------------------------------------------------
# Helpers de apresentação
# ---------------------------------------------------------------------------

MEDALS = ["🥇", "🥈", "🥉"]


def _print_ranking() -> None:
    ranking = get_total_scores()
    results = load_results()
    stages_done = len(results)

    plural = "s" if stages_done != 1 else ""
    print(f"\n{'=' * 55}")
    print(f"  RANKING — {RACE_NAME} {RACE_YEAR}  (após {stages_done} etapa{plural})")
    print(f"{'=' * 55}")

    if not ranking:
        print("  Sem dados ainda. Corre: python main.py update 1")
        print()
        return

    for i, entry in enumerate(ranking):
        pos_label = MEDALS[i] if i < 3 else f"  {i + 1}."
        pts = entry["total_points"]
        stages = entry["stages_scored"]
        print(
            f"  {pos_label}  {entry['participant']:<16} {pts:>+5} pts"
            f"  ({stages} etapa{'s' if stages != 1 else ''})"
        )
    print()


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

def cmd_setup(args) -> None:  # noqa: ARG001
    print("\n=== Fantasy Cycling — Registo de Participantes ===")
    print(f"Cada participante escolhe {RIDERS_PER_PARTICIPANT} corredores.\n")

    participants = []

    while True:
        name = input("Nome do participante (ENTER para terminar): ").strip()
        if not name:
            break

        print(f"  Escolhe {RIDERS_PER_PARTICIPANT} corredores para {name}:")
        riders = []
        for i in range(RIDERS_PER_PARTICIPANT):
            while True:
                rider = input(f"    Corredor {i + 1}: ").strip()
                if rider:
                    riders.append(rider)
                    break

        participants.append({"name": name, "riders": riders})
        print(f"  ✓ {name} registado: {', '.join(riders)}\n")

    if participants:
        save_participants(participants)
        print(f"\n{len(participants)} participante(s) guardado(s) em data/participants.json")
    else:
        print("Nenhum participante registado.")


def cmd_update(args) -> None:
    stage = args.stage
    if not 1 <= stage <= TOTAL_STAGES:
        print(f"Etapa inválida. Deve ser um número entre 1 e {TOTAL_STAGES}.")
        sys.exit(1)

    participants = load_participants()
    if not participants:
        print("Nenhum participante encontrado. Corre primeiro: python main.py setup")
        sys.exit(1)

    results = load_results()
    existing = next((r for r in results if r["stage"] == stage), None)
    if existing and not args.force:
        print(f"Etapa {stage} já processada. Usa --force para substituir.")
        sys.exit(1)

    print(f"\nA obter {'classificação geral' if args.gc else 'resultados'} da etapa {stage} em procyclingstats.com...")
    try:
        stage_results = (get_gc_results if args.gc else get_stage_results)(stage)
    except Exception as exc:  # noqa: BLE001
        print(f"Erro ao obter resultados: {exc}")
        sys.exit(1)

    print(f"  {len(stage_results)} corredores classificados.\n")

    scores = process_stage(stage, stage_results)

    stage_data = {
        "stage": stage,
        "scores": scores,
        "top10": stage_results[:10],
    }

    if existing:
        results = [r for r in results if r["stage"] != stage]
    results.append(stage_data)
    results.sort(key=lambda x: x["stage"])
    save_results(results)

    # Gerar HTML atualizado
    html_file = generate_html()
    print(f"\n📄 HTML atualizado: {html_file}  (partilha este ficheiro ou carrega-o para o Google Drive)")

    # Mostrar resumo da etapa
    print(f"{'=' * 55}")
    print(f"  ETAPA {stage} — Pontuação Fantasy")
    print(f"{'=' * 55}")

    valid_scores = sorted(
        [s for s in scores if s["stage_points"] is not None],
        key=lambda x: x["stage_points"],
    )
    for s in valid_scores:
        note = f"  ← {s['note']}" if s.get("note") else ""
        print(
            f"  {s['participant']:<16} melhor: {s['best_rider']:<26}"
            f" {s['position']:>3}.º  {s['stage_points']:>+4} pts{note}"
        )
    for s in scores:
        if s["stage_points"] is None:
            print(f"  {s['participant']:<16} — {s['note']}")

    _print_ranking()


def cmd_ranking(args) -> None:  # noqa: ARG001
    _print_ranking()


def cmd_stage(args) -> None:
    results = load_results()
    stage_data = next((r for r in results if r["stage"] == args.stage), None)
    if not stage_data:
        print(f"Etapa {args.stage} ainda não foi processada.")
        sys.exit(1)

    print(f"\n{'=' * 45}")
    print(f"  ETAPA {args.stage} — Top 10")
    print(f"{'=' * 45}")
    for r in stage_data.get("top10", []):
        print(f"  {r['position']:>3}.  {r['rider']}")

    print(f"\n{'=' * 45}")
    print(f"  ETAPA {args.stage} — Pontuação Fantasy")
    print(f"{'=' * 45}")
    for s in stage_data["scores"]:
        if s["stage_points"] is not None:
            note = f"  ← {s['note']}" if s.get("note") else ""
            print(
                f"  {s['participant']:<16} {s['best_rider']:<26}"
                f" {s['position']:>3}.º  {s['stage_points']:>+4} pts{note}"
            )
        else:
            print(f"  {s['participant']:<16} — {s['note']}")
    print()


def cmd_participants(args) -> None:  # noqa: ARG001
    participants = load_participants()
    if not participants:
        print("Nenhum participante registado.")
        return

    print(f"\n{'=' * 55}")
    print("  PARTICIPANTES")
    print(f"{'=' * 55}")
    for p in participants:
        print(f"  {p['name']:<16} {' / '.join(p['riders'])}")
    print()


def cmd_export(args) -> None:  # noqa: ARG001
    html_file = generate_html()
    print(f"\n✓ Ficheiro gerado: {html_file}")
    print("  → Abre no browser para pré-visualizar")
    print("  → Carrega no Google Drive e partilha o link com o grupo\n")


def cmd_change_team(args) -> None:
    participants = load_participants()
    if not participants:
        print("Nenhum participante registado. Corre primeiro: python main.py setup")
        sys.exit(1)

    # Mostra lista e deixa escolher
    print("\nParticipantes:")
    for i, p in enumerate(participants):
        print(f"  {i + 1}. {p['name']:<16} {' / '.join(p['riders'])}")

    # Se o nome foi passado como argumento usa-o, senão pede
    if args.participant:
        name_arg = args.participant.strip().lower()
        match = next((p for p in participants if p["name"].lower() == name_arg), None)
        if not match:
            print(f"Participante '{args.participant}' não encontrado.")
            sys.exit(1)
        participant = match
    else:
        raw = input("\nNúmero ou nome do participante: ").strip()
        if raw.isdigit():
            idx = int(raw) - 1
            if not 0 <= idx < len(participants):
                print("Número inválido.")
                sys.exit(1)
            participant = participants[idx]
        else:
            match = next((p for p in participants if p["name"].lower() == raw.lower()), None)
            if not match:
                print(f"Participante '{raw}' não encontrado.")
                sys.exit(1)
            participant = match

    print(f"\nA alterar equipa de {participant['name']}.")
    print(f"Corredores atuais: {', '.join(participant['riders'])}")
    print(f"Introduz {RIDERS_PER_PARTICIPANT} novos corredores (ENTER para manter o atual):")

    new_riders = []
    for i, current in enumerate(participant["riders"]):
        new = input(f"  Corredor {i + 1} [{current}]: ").strip()
        new_riders.append(new if new else current)

    participant["riders"] = new_riders
    save_participants(participants)

    print(f"\n✓ Equipa de {participant['name']} atualizada: {', '.join(new_riders)}")
    print("  As pontuações de etapas anteriores não foram alteradas.\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=f"Fantasy Cycling — {RACE_NAME} {RACE_YEAR}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemplos:\n"
            "  python main.py setup\n"
            "  python main.py update 1\n"
            "  python main.py ranking\n"
            "  python main.py stage 1\n"
            "  python main.py participants\n"
            "  python main.py change-team\n"
            "  python main.py change-team Tiago\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", metavar="comando")

    sub.add_parser("setup", help="Registar participantes e corredores")

    p_update = sub.add_parser("update", help="Obter resultados e calcular pontos da etapa")
    p_update.add_argument("stage", type=int, metavar="ETAPA", help="Número da etapa (1–21)")
    p_update.add_argument(
        "--force", action="store_true", help="Substituir resultados já existentes"
    )
    p_update.add_argument(
        "--gc", action="store_true",
        help="Usar a Classificação Geral (GC) após a etapa em vez do resultado da etapa "
             "(ex.: etapa 1 do Tour 2026, que é um CRE por equipas)",
    )

    sub.add_parser("ranking", help="Ver classificação geral")

    p_stage = sub.add_parser("stage", help="Ver detalhes de uma etapa já processada")
    p_stage.add_argument("stage", type=int, metavar="ETAPA", help="Número da etapa")

    sub.add_parser("participants", help="Listar participantes e corredores escolhidos")
    sub.add_parser("export", help="Gerar index.html para partilhar (Google Drive, etc.)")

    p_change = sub.add_parser("change-team", help="Substituir corredor(es) de um participante")
    p_change.add_argument(
        "participant", nargs="?", default=None,
        metavar="NOME", help="Nome do participante (opcional, pede interativamente se omitido)"
    )

    args = parser.parse_args()

    commands = {
        "setup": cmd_setup,
        "update": cmd_update,
        "ranking": cmd_ranking,
        "stage": cmd_stage,
        "participants": cmd_participants,
        "export": cmd_export,
        "change-team": cmd_change_team,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
