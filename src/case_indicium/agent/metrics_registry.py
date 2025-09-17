# src/case_indicium/agent/metrics_registry.py
"""Canonical registry of metrics the agent can explain and reference."""

from __future__ import annotations
from typing import Literal, Optional, Dict
from pydantic import BaseModel, Field

Scope = Literal["br", "uf"]

class Metric(BaseModel):
    """Describe a metric: what it is, how to compute it, and constraints."""
    id: str
    label: str
    description_pt: str
    query_id: str
    scope: list[Scope] = Field(default_factory=lambda: ["br", "uf"])
    window: str  # e.g., "7d", "30d"
    unit: Literal["pct", "count"]
    notes_pt: Optional[str] = None
    min_val: Optional[float] = None
    max_val: Optional[float] = None

METRICS: Dict[str, Metric] = {
    "growth_7d": Metric(
        id="growth_7d",
        label="Taxa de aumento (7 dias)",
        description_pt=(
            "Variação percentual dos últimos 7 dias em relação aos 7 dias anteriores, "
            "ancorada no último dia disponível (as_of)."
        ),
        query_id="SQL_GROWTH_7D",  # mapeamos na tool por BR/UF
        scope=["br", "uf"],
        window="7d",
        unit="pct",
        notes_pt="Se o período anterior tiver 0 casos, o crescimento é 'indisponível'.",
        min_val=-100.0,
        max_val=1000.0,
    ),
    "cfr_30d_closed": Metric(
        id="cfr_30d_closed",
        label="CFR (30 dias, casos encerrados)",
        description_pt=(
            "Óbitos divididos por casos encerrados nos últimos 30 dias, em %. "
            "Não é taxa de mortalidade populacional."
        ),
        query_id="SQL_KPIS_30D",
        scope=["br", "uf"],
        window="30d",
        unit="pct",
        notes_pt="Usa apenas casos encerrados em até 30 dias (fechamento/resultado).",
        min_val=0.0,
        max_val=100.0,
    ),
    "icu_rate_30d": Metric(
        id="icu_rate_30d",
        label="% casos com UTI (30 dias)",
        description_pt=(
            "Percentual de casos com passagem por UTI nos últimos 30 dias. "
            "Não representa ocupação de leitos hospitalares."
        ),
        query_id="SQL_KPIS_30D",
        scope=["br", "uf"],
        window="30d",
        unit="pct",
        notes_pt="Substituto operacional por ausência de denominador de leitos.",
        min_val=0.0,
        max_val=100.0,
    ),
    "vaccinated_rate_30d": Metric(
        id="vaccinated_rate_30d",
        label="% casos vacinados (30 dias)",
        description_pt=(
            "Percentual de casos com vacinação registrada nos últimos 30 dias. "
            "Não é cobertura vacinal da população."
        ),
        query_id="SQL_KPIS_30D",
        scope=["br", "uf"],
        window="30d",
        unit="pct",
        notes_pt="Não confundir com cobertura populacional.",
        min_val=0.0,
        max_val=100.0,
    ),
}
