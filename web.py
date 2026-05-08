"""
Servidor web Flask — dashboard da Fantasy Cycling.
"""

from flask import Flask, render_template

from config import RACE_YEAR
from fantasy import get_total_scores, load_participants, load_results

app = Flask(__name__)


def _stages_done() -> list[int]:
    return sorted(r["stage"] for r in load_results())


@app.context_processor
def inject_globals():
    return {
        "race_year": RACE_YEAR,
        "stages_done": _stages_done(),
    }


@app.route("/")
def index():
    ranking = get_total_scores()
    stages = _stages_done()
    return render_template("index.html", ranking=ranking, stages=stages)


@app.route("/stage/<int:stage_number>")
def stage(stage_number: int):
    results = load_results()
    stage_data = next((r for r in results if r["stage"] == stage_number), None)
    if stage_data is None:
        return render_template("404.html", stage=stage_number), 404
    return render_template("stage.html", stage_data=stage_data)


@app.route("/participants")
def participants():
    part = load_participants()
    return render_template("participants.html", participants=part)


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
