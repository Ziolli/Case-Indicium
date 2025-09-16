from __future__ import annotations
from pathlib import Path
import matplotlib.pyplot as plt
from .schemas import Series

ASSETS_DIR = Path("reports/assets")

def plot_series(series: Series, filename: str) -> str:
    """
    Render a simple line/bar depending on periodicity (infer by label substring).
    Returns the saved PNG path.
    """
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    path = ASSETS_DIR / filename

    xs = [p.x for p in series.points]
    ys = [p.y for p in series.points]

    plt.figure()
    if "monthly" in series.label:
        plt.bar(xs, ys)
        plt.title("Monthly cases (last 12 months)")
        plt.xlabel("month"); plt.ylabel("cases")
        plt.xticks(rotation=45)
    else:
        plt.plot(xs, ys)
        plt.title("Daily cases (last 30 days)")
        plt.xlabel("date"); plt.ylabel("cases")
        plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(path, dpi=120)
    plt.close()
    return str(path)
