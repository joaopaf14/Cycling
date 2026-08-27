#!/usr/bin/env python3
"""
Auto-update da Fantasy Cycling.

Uso:
  python3 auto_update.py                   # processa TODAS as etapas pendentes em sequência,
                                            # parando na primeira ainda não disputada
  python3 auto_update.py --stage 5         # força só essa etapa específica
  python3 auto_update.py --stage 5 --force # re-processa etapa já existente
  python3 auto_update.py --stage 1 --gc    # usa a GC em vez do resultado da etapa
                                            # (ex.: CRE por equipas) — só faz sentido
                                            # combinado com --stage

Etapas anuladas (ex.: mau tempo) são detetadas automaticamente e marcadas como
tal em data/results.json (scores vazios), para o processo não ficar preso à
espera de resultados que nunca vão chegar.
"""

import argparse
import logging
import sys
from pathlib import Path

from config import TOTAL_STAGES
from export_html import generate_html
from fantasy import load_results, process_stage, save_results
from scraper import StageCancelled, get_gc_results, get_stage_results

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


def _save_cancelled(stage: int) -> None:
    results = [r for r in load_results() if r["stage"] != stage]
    results.append({"stage": stage, "cancelled": True, "scores": [], "top10": []})
    results.sort(key=lambda r: r["stage"])
    save_results(results)


def _process_stage(stage: int, *, gc: bool, force: bool) -> str:
    """
    Processa uma única etapa. Devolve o estado:
      "done"      — processada e guardada com sucesso
      "cancelled" — etapa anulada; marcada como tal para não bloquear as seguintes
      "not_yet"   — a corrida ainda não tem resultados para esta etapa
      "skipped"   — já estava processada e não se pediu --force
    Erros inesperados (não ValueError/StageCancelled) propagam-se para quem chamou.
    """
    results = load_results()
    already_done = any(r["stage"] == stage for r in results)
    if already_done and not force:
        log.info("Etapa %d já processada. Usa --force para re-processar.", stage)
        return "skipped"

    try:
        stage_results = (get_gc_results if gc else get_stage_results)(stage)
    except StageCancelled as exc:
        log.info("Etapa %d: %s", stage, exc)
        _save_cancelled(stage)
        return "cancelled"
    except ValueError as exc:
        # Etapa sem resultados = ainda não terminou. Não é um erro real.
        log.info("Etapa %d: %s", stage, exc)
        return "not_yet"

    if not stage_results:
        log.info("Etapa %d: sem resultados ainda.", stage)
        return "not_yet"

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
    return "done"


def main() -> None:
    parser = argparse.ArgumentParser(description="Auto-update da Fantasy Cycling")
    parser.add_argument(
        "--stage", type=int, default=None,
        help="Etapa específica. Se omitido, processa todas as etapas pendentes em sequência.",
    )
    parser.add_argument("--force", action="store_true", help="Re-processar etapa(s) já existente(s)")
    parser.add_argument(
        "--gc", action="store_true",
        help="Usar a Classificação Geral (GC) após a etapa em vez do resultado da etapa "
             "(ex.: CRE por equipas). Só é usado com --stage — no modo automático "
             "as etapas seguintes usam sempre o resultado normal.",
    )
    args = parser.parse_args()

    processed = 0

    if args.stage:
        log.info("Etapa especificada: %d%s%s", args.stage,
                  " (--force)" if args.force else "", " (--gc)" if args.gc else "")
        try:
            status = _process_stage(args.stage, gc=args.gc, force=args.force)
        except Exception as exc:
            log.error("Etapa %d: erro inesperado — %s", args.stage, exc)
            sys.exit(1)
        if status in ("done", "cancelled"):
            processed += 1
    else:
        # Modo automático: percorre todas as etapas pendentes seguidas,
        # parando na primeira que ainda não tenha resultados disponíveis.
        while True:
            stage = _next_pending_stage()
            if stage is None:
                log.info("Todas as %d etapas já processadas.", TOTAL_STAGES)
                break

            log.info("Próxima etapa pendente: %d", stage)
            try:
                status = _process_stage(stage, gc=False, force=args.force)
            except Exception as exc:
                log.error("Etapa %d: erro inesperado — %s", stage, exc)
                sys.exit(1)

            if status in ("done", "cancelled"):
                processed += 1
                continue  # tenta logo a etapa seguinte, sem esperar pelo cron do dia seguinte
            break  # not_yet ou skipped: não faz sentido continuar hoje

    if processed == 0:
        log.info("Nenhuma etapa nova processada.")
        sys.exit(0)

    html_out = generate_html()
    log.info("HTML gerado: %s", html_out)
    log.info("Auto-update concluído — %d etapa(s) processada(s).", processed)


if __name__ == "__main__":
    main()
