from __future__ import annotations
from .sql_client import SQLClient
from .schemas import KPIs30d, Series, SeriesPoint
from . import queries as Q

def get_as_of_day(sql: SQLClient) -> str | None:
    """Return last available day in gold.fct_daily_uf as ISO string."""
    df = sql.df("SELECT COALESCE(MAX(day), CURRENT_DATE) AS d FROM gold.fct_daily_uf")
    if df.empty or df.iloc[0]["d"] is None:
        return None
    d = df.iloc[0]["d"]
    try:
        return d.isoformat()
    except Exception:
        return str(d)


def get_growth_7d_br(sql: SQLClient) -> tuple[int, int, float | None]:
    df = sql.df(Q.SQL_GROWTH_7D_BR)
    if df.empty:
        return 0, 0, None
    r = df.iloc[0]
    cases_7d = int(r.get("cases_7d") or 0)
    cases_prev_7d = int(r.get("cases_prev_7d") or 0)
    growth = None if r.get("growth_7d_pct") is None else float(r["growth_7d_pct"])
    return cases_7d, cases_prev_7d, growth

def get_kpis_30d_br(sql: SQLClient) -> KPIs30d:
    g7, g7prev, g7pct = get_growth_7d_br(sql)
    df = sql.df(Q.SQL_KPIS_30D_BR)
    if df.empty:
        return KPIs30d(
            cases_7d=g7, cases_prev_7d=g7prev, growth_7d_pct=g7pct,
            cfr_closed_30d_pct=None, icu_rate_30d_pct=None, vaccinated_rate_30d_pct=None
        )
    r = df.iloc[0]
    return KPIs30d(
        cases_7d=g7,
        cases_prev_7d=g7prev,
        growth_7d_pct=g7pct,
        cfr_closed_30d_pct=None if r.get("cfr_closed_30d_pct") is None else float(r["cfr_closed_30d_pct"]),
        icu_rate_30d_pct=None if r.get("icu_rate_30d_pct") is None else float(r["icu_rate_30d_pct"]),
        vaccinated_rate_30d_pct=None if r.get("vaccinated_rate_30d_pct") is None else float(r["vaccinated_rate_30d_pct"]),
    )

def _series_from_df(df, x_col: str, y_col: str, label: str) -> Series:
    pts = [SeriesPoint(x=row[x_col], y=float(row[y_col])) for _, row in df.iterrows()]
    return Series(label=label, points=pts)

def get_daily_30d_br(sql: SQLClient) -> Series:
    df = sql.df(Q.SQL_DAILY_30D_BR)
    return _series_from_df(df, "day", "cases", "daily_cases_30d")

def get_monthly_12m_br(sql: SQLClient) -> Series:
    df = sql.df(Q.SQL_MONTHLY_12M_BR)
    return _series_from_df(df, "month", "cases", "monthly_cases_12m")
