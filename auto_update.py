#!/usr/bin/env python3
"""
Auto-update da Fantasy Cycling.

Uso:
  python3 auto_update.py                   # processa próxima etapa pendente
  python3 auto_update.py --stage 5         # força etapa específica
  python3 auto_update.py --stage 5 --force # re-processa etapa já existente
  python3 auto_update.py --stage 1 --gc    # usa a GC em vez do resultado da etapa
                                            # (ex.: CRE por equipas)
"""

import argparse
import logging
import sys
from pathlib import Path

from config import TOTAL_STAGES
from export_html import generate_html
from fantasy import load_results, process_stage, save_results
from scraper import get_gc_results, get_stage_results

LOG_FILE = Path(__file__).parent / "auto_update.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def _next_pending_stage() -> int | None:
    results = load_results()
    done = {r["stage"] for r in results}
    for s in range(1, TOTAL_STAGES + 1):
        if s not in done:
            return s
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-update da Fantasy Cycling")
    parser.add_argument("--stage", type=int, default=None, help="Etapa específica")
    parser.add_argument("--force", action="store_true", help="Re-processar etapa já existente")
    parser.add_argument(
        "--gc", action="store_true",
        help="Usar a Classificação Geral (GC) após a etapa em vez do resultado da etapa "
             "(ex.: CRE por equipas)",
    )
    args = parser.parse_args()

    # Determinar etapa
    if args.stage:
        stage = args.stage
        log.info("Etapa especificada: %d%s", stage, " (--force)" if args.force else "")
    else:
        stage = _next_pending_stage()
        if stage is None:
            log.info("Todas as %d etapas já processadas.", TOTAL_STAGES)
            sys.exit(0)
        log.info("Próxima etapa pendente: %d", stage)

    # Verificar se já existe (sem --force, sair)
    results = load_results()
    already_done = any(r["stage"] == stage for r in results)
    if already_done and not args.force:
        log.info("Etapa %d já processada. Usa --force para re-processar.", stage)
        sys.exit(0)

    # Buscar resultados do PCS
    try:
        stage_results = get_stage_results(stage)
    except ValueError as exc:
        # Etapa sem resultados = ainda não terminou. Não é um erro real.
        log.info("Etapa %d: %s", stage, exc)
        sys.exit(0)
    except Exception as exc:
        log.error("Etapa %d: erro inesperado — %s", stage, exc)
        sys.exit(1)

    if not stage_results:
        log.info("Etapa %d: sem resultados ainda.", stage)
        sys.exit(0)

    log.info("Etapa %d: %d ciclistas obtidos.", stage, len(stage_results))

    # Re-processar: remover dados antigos da etapa se existirem
    results = [r for r in results if r["stage"] != stage]

    # Calcular pontos com as equipas ACTUAIS dos participantes
    # (as equipas passadas ficam preservadas nas etapas já em results)
    stage_data = {
        "stage": stage,
        "scores": process_stage(stage, stage_results),
        "top10": stage_results[:10],
    }
    results.append(stage_data)
    results.sort(key=lambda r: r["stage"])
    save_results(results)

    log.info("Etapa %d guardada.", stage)

    html_out = generate_html()
    log.info("HTML gerado: %s", html_out)
    log.info("Auto-update concluído para etapa %d.", stage)


if __name__ == "__main__":
    main()
