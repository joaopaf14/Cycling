"""
Gera um ficheiro HTML estático e auto-contido com o ranking da fantasy.
Basta abrir no browser ou partilhar via Google Drive / WhatsApp.
"""

from datetime import datetime

from config import RACE_NAME, RACE_YEAR, STAGE_WIN_BONUS, TOTAL_STAGES
from fantasy import get_cumulative_rankings, get_total_scores, load_participants, load_results

OUTPUT_FILE = "index.html"

MEDALS = ["🥇", "🥈", "🥉"]


def _medal(i: int) -> str:
    return MEDALS[i] if i < 3 else str(i + 1) + "º"


def _pts_class(pts: int) -> str:
    if pts < 0:
        return "text-success fw-bold"
    if pts <= 5:
        return "text-primary"
    return ""


def _wins_breakdown_text(wins_by_rider: dict) -> str:
    """Formata o detalhe de vitórias por corredor, ex.: '2x Pogačar · 1x Evenepoel'."""
    if not wins_by_rider:
        return ""
    parts = sorted(wins_by_rider.items(), key=lambda kv: -kv[1])
    return " · ".join(f"{count}x {rider}" for rider, count in parts)


def _evolution_section(history: list[dict]) -> str:
    """
    Tabela de evolução: linhas = participantes, colunas = etapas.
    Mostra os pontos acumulados após cada etapa.
    A célula fica a verde se o participante liderava nessa etapa.
    """
    if not history:
        return ""

    participants_order = [e["participant"] for e in history[-1]["ranking"]]
    stages = [h["stage"] for h in history]

    # índice: {stage: {participant: total_points}}
    pts_by_stage: dict[int, dict[str, int]] = {}
    leaders: dict[int, str] = {}
    for h in history:
        pts_by_stage[h["stage"]] = {e["participant"]: e["total_points"] for e in h["ranking"]}
        leaders[h["stage"]] = h["ranking"][0]["participant"]

    header_cols = "".join(f'<th class="text-center">E{s}</th>' for s in stages)
    rows = ""
    for p in participants_order:
        cells = ""
        for s in stages:
            pts = pts_by_stage[s].get(p, "")
            sign = "+" if isinstance(pts, int) and pts >= 0 else ""
            is_leader = leaders.get(s) == p
            cls = "text-center small" + (" table-success fw-bold" if is_leader else "")
            cells += f'<td class="{cls}">{sign}{pts}</td>'
        rows += f"<tr><td class='fw-semibold'>{p}</td>{cells}</tr>"

    return f"""
    <p class="section-title mt-4">Evolução do ranking</p>
    <div class="table-responsive">
    <table class="table table-sm table-bordered align-middle" style="width:auto;min-width:100%">
      <thead class="table-secondary">
        <tr><th>Participante</th>{header_cols}</tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    </div>
    <p class="text-muted small">Pontos acumulados após cada etapa. Fundo verde = lider nessa etapa.</p>"""


def _ranking_section(ranking: list[dict], stages_done: int) -> str:
    if not ranking:
        return "<p class='text-muted'>Ainda sem resultados. Aguarda a primeira etapa.</p>"

    rows = ""
    for i, entry in enumerate(ranking):
        medal = MEDALS[i] if i < 3 else f"{i + 1}º"
        pts = entry["total_points"]
        pts_cls = _pts_class(pts)
        sign = "+" if pts >= 0 else ""
        wins = entry.get("wins", 0)
        breakdown = _wins_breakdown_text(entry.get("wins_by_rider", {}))
        breakdown_html = (
            f'<div class="text-muted fw-normal" style="font-size:.72rem">{breakdown}</div>'
            if breakdown else ""
        )
        rows += f"""
        <tr {'class="table-warning fw-bold"' if i == 0 else ''}>
          <td class="text-center">{medal}</td>
          <td>{entry['participant']}</td>
          <td class="text-center {pts_cls}">{sign}{pts}</td>
          <td class="text-center">{wins}{breakdown_html}</td>
        </tr>"""

    return f"""
    <table class="table table-hover align-middle">
      <thead class="table-dark">
        <tr>
          <th class="text-center" style="width:60px">Pos</th>
          <th style="width:110px">Participante</th>
          <th class="text-center">Pontos</th>
          <th class="text-center">Vitórias</th>
        </tr>
      </thead>
      <tbody>{rows}
      </tbody>
    </table>
    <p class="text-muted small">
      Pontos = posição do melhor corredor em cada etapa.
      Vitória = posição 1 + bónus {STAGE_WIN_BONUS} pts. Menor total ganha.
    </p>"""


def _stages_section(results: list[dict]) -> str:
    results_by_stage = {r["stage"]: r for r in results}
    last_played = max(results_by_stage.keys(), default=0)

    accordion_items = ""
    for sn in range(1, TOTAL_STAGES + 1):
        played = sn in results_by_stage

        if not played:
            is_open = False
            accordion_items += f"""
        <div class="accordion-item">
          <h2 class="accordion-header">
            <button class="accordion-button collapsed text-muted" type="button"
                    data-bs-toggle="collapse" data-bs-target="#stage{sn}">
              Etapa {sn} <span class="ms-2 badge bg-secondary">Por disputar</span>
            </button>
          </h2>
          <div id="stage{sn}" class="accordion-collapse collapse">
            <div class="accordion-body text-muted">Ainda não disputada.</div>
          </div>
        </div>"""
            continue

        stage_data = results_by_stage[sn]
        is_open = sn == last_played

        if stage_data.get("cancelled"):
            accordion_items += f"""
        <div class="accordion-item">
          <h2 class="accordion-header">
            <button class="accordion-button {'collapsed' if not is_open else ''} text-muted"
                    type="button" data-bs-toggle="collapse" data-bs-target="#stage{sn}">
              Etapa {sn} <span class="ms-2 badge bg-warning text-dark">Anulada</span>
            </button>
          </h2>
          <div id="stage{sn}"
               class="accordion-collapse collapse {'show' if is_open else ''}">
            <div class="accordion-body text-muted">
              Etapa anulada — sem resultados nem pontos atribuídos.
            </div>
          </div>
        </div>"""
            continue

        scores = stage_data.get("scores", [])

        # Coluna esquerda: pontuação fantasy (melhor corredor de cada participante)
        score_rows = ""
        valid = sorted(
            [s for s in scores if s["stage_points"] is not None],
            key=lambda x: x["stage_points"],
        )
        for i, s in enumerate(valid):
            sign = "+" if s["stage_points"] >= 0 else ""
            note_badge = (
                f' <span class="badge bg-success">Vitória!</span>'
                if s.get("note")
                else ""
            )
            score_rows += f"""
            <tr {'class="table-warning"' if i == 0 else ''}>
              <td>{s['participant']}</td>
              <td>{s['best_rider']}{note_badge}</td>
              <td class="text-center">{s['position']}º</td>
              <td class="text-center {_pts_class(s['stage_points'])}">{sign}{s['stage_points']}</td>
            </tr>"""
        for s in scores:
            if s["stage_points"] is None:
                score_rows += f"""
            <tr class="text-muted">
              <td>{s['participant']}</td>
              <td colspan="3">{s['note']}</td>
            </tr>"""

        # Coluna direita: todos os corredores dos jogadores ordenados por posição
        flat_riders = []
        for s in scores:
            for rd in s.get("riders_detail", []):
                is_best = (
                    s.get("best_rider") and s["best_rider"] == rd["rider_name"]
                    and rd["position"] is not None
                )
                flat_riders.append({
                    "participant": s["participant"],
                    "rider_name": rd["rider_name"],
                    "position": rd["position"],
                    "is_best": is_best,
                })
        flat_riders.sort(key=lambda x: x["position"] if x["position"] is not None else 9999)

        all_riders_rows = ""
        for rd in flat_riders:
            pos = rd["position"]
            pos_str = f"{pos}º" if pos is not None else "<span class='text-muted'>—</span>"
            bold = " fw-bold" if rd["is_best"] else ""
            star = " ⭐" if rd["is_best"] else ""
            all_riders_rows += f"""
            <tr>
              <td class="text-muted small">{rd['participant']}</td>
              <td class="{bold}">{rd['rider_name']}{star}</td>
              <td class="text-center{bold}">{pos_str}</td>
            </tr>"""

        accordion_items += f"""
        <div class="accordion-item">
          <h2 class="accordion-header">
            <button class="accordion-button {'collapsed' if not is_open else ''}"
                    type="button" data-bs-toggle="collapse"
                    data-bs-target="#stage{sn}">
              Etapa {sn}
            </button>
          </h2>
          <div id="stage{sn}"
               class="accordion-collapse collapse {'show' if is_open else ''}">
            <div class="accordion-body">
              <div class="row g-3">
                <div class="col-md-6">
                  <h6 class="text-uppercase text-muted small mb-2">Pontuação Fantasy</h6>
                  <table class="table table-sm table-hover">
                    <thead><tr><th>Participante</th><th>Corredor</th><th class="text-center">Pos</th><th class="text-center">Pts</th></tr></thead>
                    <tbody>{score_rows}</tbody>
                  </table>
                </div>
                <div class="col-md-6">
                  <table class="table table-sm">
                    <thead><tr><th>Jogador</th><th>Corredor</th><th class="text-center">Pos</th></tr></thead>
                    <tbody>{all_riders_rows}</tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>"""

    return f'<div class="accordion">{accordion_items}</div>'


def _participants_section(participants: list[dict], results: list[dict]) -> str:
    if not participants:
        return "<p class='text-muted'>Nenhum participante registado.</p>"

    names = [p["name"] for p in participants]
    # equipa atual (para etapas ainda não disputadas)
    current_team = {p["name"]: p["riders"] for p in participants}

    # equipa usada em cada etapa já disputada (extraída do riders_detail)
    team_by_stage: dict[int, dict[str, list[str]]] = {}
    for stage_data in results:
        sn = stage_data["stage"]
        team_by_stage[sn] = {}
        for score in stage_data.get("scores", []):
            team_by_stage[sn][score["participant"]] = [
                rd["rider_name"] for rd in score.get("riders_detail", [])
            ]

    header = "".join(f"<th class='text-center'>{n}</th>" for n in names)
    rows = ""
    for sn in range(1, TOTAL_STAGES + 1):
        played = sn in team_by_stage
        row_cls = "" if played else " class='text-muted'"
        cells = ""
        for n in names:
            if played:
                riders = team_by_stage[sn].get(n, current_team.get(n, []))
                cell = "<br>".join(riders)
            else:
                riders = current_team.get(n, [])
                cell = "<span class='text-muted small'>" + "<br>".join(riders) + "</span>"
            cells += f"<td class='text-center small'>{cell}</td>"
        rows += f"<tr{row_cls}><td class='fw-semibold text-nowrap'>Etapa {sn}{'&nbsp;<span class=\"badge bg-secondary\">Pendente</span>' if not played else ''}</td>{cells}</tr>"

    return f"""
    <div class="table-responsive">
    <table class="table table-sm table-bordered align-middle">
      <thead class="table-dark"><tr><th>Etapa</th>{header}</tr></thead>
      <tbody>{rows}</tbody>
    </table>
    </div>
    <p class="text-muted small">Equipas pendentes mostram a equipa atual (pode mudar até à etapa).</p>"""


def generate_html() -> str:
    """Gera o HTML completo e devolve o caminho do ficheiro criado."""
    ranking = get_total_scores()
    history = get_cumulative_rankings()
    results = load_results()
    participants = load_participants()
    stages_done = len(results)
    updated_at = datetime.now().strftime("%d/%m/%Y %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="pt">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Fantasy Cycling — {RACE_NAME} {RACE_YEAR}</title>
  <link rel="stylesheet"
        href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css"
        integrity="sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH"
        crossorigin="anonymous"/>
  <style>
    body {{ background: #f8f9fa; }}
    .hero {{
      background: linear-gradient(135deg, #e63946 0%, #c1121f 100%);
      color: white;
      padding: 2.5rem 1rem 2rem;
      margin-bottom: 2rem;
    }}
    .hero h1 {{ font-size: 1.8rem; font-weight: 800; letter-spacing: -0.5px; }}
    .hero .subtitle {{ opacity: .85; font-size: .95rem; }}
    .section-title {{
      font-size: .7rem; font-weight: 700; letter-spacing: 1.5px;
      text-transform: uppercase; color: #6c757d; margin-bottom: .75rem;
    }}
    .nav-pills .nav-link.active {{ background-color: #c1121f; }}
    .nav-pills .nav-link {{ color: #c1121f; }}
  </style>
</head>
<body>

<div class="hero text-center">
  <h1>🚴 Fantasy Cycling</h1>
  <div class="subtitle">{RACE_NAME} {RACE_YEAR} &nbsp;·&nbsp; {stages_done} etapa{'s' if stages_done != 1 else ''} disputada{'s' if stages_done != 1 else ''}</div>
</div>

<div class="container pb-5" style="max-width:860px">

  <!-- Tabs -->
  <ul class="nav nav-pills mb-4 justify-content-center" id="tabs" role="tablist">
    <li class="nav-item"><button class="nav-link active px-4" data-bs-toggle="pill" data-bs-target="#tab-ranking">Ranking</button></li>
    <li class="nav-item"><button class="nav-link px-4" data-bs-toggle="pill" data-bs-target="#tab-stages">Etapas</button></li>
    <li class="nav-item"><button class="nav-link px-4" data-bs-toggle="pill" data-bs-target="#tab-participants">Equipas</button></li>
  </ul>

  <div class="tab-content">

    <!-- RANKING -->
    <div class="tab-pane fade show active" id="tab-ranking">
      <p class="section-title">Classificação geral</p>
      {_ranking_section(ranking, stages_done)}
      {_evolution_section(history)}
    </div>

    <!-- ETAPAS -->
    <div class="tab-pane fade" id="tab-stages">
      <p class="section-title">Resultados por etapa</p>
      {_stages_section(results)}
    </div>

    <!-- PARTICIPANTES -->
    <div class="tab-pane fade" id="tab-participants">
      <p class="section-title">Equipas por etapa</p>
      {_participants_section(participants, results)}
    </div>

  </div>

  <p class="text-center text-muted small mt-4">Atualizado a {updated_at}</p>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"
        integrity="sha384-YvpcrYf0tY3lHB60NNkmXc4s9bIOgUxi8T/jzmxFrXVMtf66EBc/UGl0+3M5DqNR"
        crossorigin="anonymous"></script>
<script>
  // Fallback tabs
  (function () {{
    var btns = document.querySelectorAll('[data-bs-toggle="pill"]');
    var panes = document.querySelectorAll('.tab-pane');
    btns.forEach(function (btn) {{
      btn.addEventListener('click', function () {{
        btns.forEach(function (b) {{ b.classList.remove('active'); }});
        panes.forEach(function (p) {{ p.classList.remove('show', 'active'); }});
        btn.classList.add('active');
        var target = document.querySelector(btn.getAttribute('data-bs-target'));
        if (target) {{ target.classList.add('show', 'active'); }}
      }});
    }});
  }})();
  // Fallback accordion
  (function () {{
    var accBtns = document.querySelectorAll('[data-bs-toggle="collapse"]');
    accBtns.forEach(function (btn) {{
      btn.addEventListener('click', function () {{
        var targetId = btn.getAttribute('data-bs-target');
        var panel = document.querySelector(targetId);
        if (!panel) return;
        var isOpen = panel.classList.contains('show');
        // fecha todos os painéis do mesmo acordeão
        var accordion = btn.closest('.accordion');
        if (accordion) {{
          accordion.querySelectorAll('.accordion-collapse').forEach(function (p) {{
            p.classList.remove('show');
          }});
          accordion.querySelectorAll('.accordion-button').forEach(function (b) {{
            b.classList.add('collapsed');
          }});
        }}
        if (!isOpen) {{
          panel.classList.add('show');
          btn.classList.remove('collapsed');
        }}
      }});
    }});
  }})();
</script>
</body>
</html>"""

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    return OUTPUT_FILE
