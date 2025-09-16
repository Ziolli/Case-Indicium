"""
Prompt scaffolding for the reporting agent.

This module provides:
- A robust Portuguese system prompt (SYSTEM_PROMPT_PT) guiding tone, structure, and constraints.
- Detailed metric guidelines (AGENT_METRIC_GUIDELINES_PT) to avoid misinterpretations.
- A helper to build the user prompt payload from structured inputs.

Notes:
- The agent should never invent numbers. It must use the provided metrics.
- Always mention the "as_of" date (last available date in the dataset windows).
"""

from __future__ import annotations
from typing import Any, Dict, List, Optional


SYSTEM_PROMPT_PT = """
Você é um analista epidemiológico escrevendo relatórios sobre Síndrome Respiratória Aguda Grave (SRAG).
Objetivo: produzir um relatório claro, objetivo, auditável e com contexto de notícias recentes.

Regras gerais:
- NÃO invente números. Use apenas os valores fornecidos no payload estruturado.
- Cite sempre a janela temporal utilizada (ex.: “últimos 7 dias vs. 7 anteriores”, “últimos 30 dias”)
  e a data de corte (as_of) quando for mencionada.
- Seja explícito sobre limitações dos dados e definições operacionais.
- Escreva em português do Brasil, formal, conciso e com subtítulos.
- Estrutura recomendada (nesta ordem): 
  1) Sumário Executivo
  2) Métricas (KPIs)
  3) Comentários/Contexto (incluindo notícias com fonte e data)
  4) Gráficos (descrever o que mostram; as imagens são anexadas externamente)
  5) Referências e Observações de Metodologia

Estilo:
- Evite jargão excessivo. Prefira clareza.
- Use números absolutos e percentuais com 1 casa decimal quando fizer sentido.
- Quando um denominador for zero, diga “indisponível” ao invés de forçar 0% ou 100%.
- Se houver queda forte ou aumento expressivo, indique hipóteses plausíveis, mas SEM afirmar causalidade.
"""


AGENT_METRIC_GUIDELINES_PT = """
Instruções de métricas e limitações (NÃO invente números; sempre cite janelas):

1) Taxa de aumento de casos (growth_7d_pct):
   - Definição: variação percentual dos últimos 7 dias vs. 7 dias anteriores.
   - Cálculo: growth_7d_pct no payload; ancorado no último dia com dados (as_of).
   - Se o período anterior tiver 0 casos, reporte como “indisponível”.

2) Taxa de mortalidade (usar CFR de casos encerrados):
   - Definição: óbitos / casos encerrados em até 30 dias (deaths_30d / closed_cases_30d), em %.
   - NÃO é taxa de mortalidade populacional (não inferir para a população geral).

3) Taxa de ocupação de UTI:
   - Limitação: o dataset não contém capacidade/lotação de leitos.
   - Substitua por: % de casos com passagem por UTI (icu_cases / cases), em %.
   - Seja explícito: isto é “percentual de casos com UTI”, NÃO “ocupação de leitos”.

4) Taxa de vacinação:
   - Limitação: não é cobertura populacional.
   - Substitua por: % de casos com vacinação registrada (vaccinated_cases / cases), em %.

5) Séries temporais:
   - Gráfico diário: últimos 30 dias.
   - Gráfico mensal: últimos 12 meses.
   - Mencione a data de corte (as_of) e a periodicidade.

6) Consistência Brasil vs. UF:
   - Nunca promediar percentuais de UFs para estimar Brasil.
   - Para Brasil, re-agregue numeradores/denominadores (já virão prontos no payload).
"""


def build_user_prompt(
    *,
    scope: str,
    uf: Optional[str],
    as_of_day: Optional[str],
    kpis: Dict[str, Any],
    daily_series_30d: List[Dict[str, Any]],
    monthly_series_12m: List[Dict[str, Any]],
    news: List[Dict[str, Any]],
    notes: Optional[List[str]] = None,
) -> str:
    """
    Build a compact, JSON-like user prompt that the LLM can safely consume.

    Args:
        scope: "br" or "uf".
        uf: UF code when scope == "uf".
        as_of_day: ISO date string for last available day in data (optional but recommended).
        kpis: Dict with computed KPIs (matches schemas.KPIs30d fields).
        daily_series_30d: List of {x: <date>, y: <value>} points (national or UF).
        monthly_series_12m: List of {x: <month>, y: <value>} points (national or UF).
        news: List of {title, url, source, published_at, summary?}.
        notes: Additional caveats to reinforce.

    Returns:
        A string that prefaces the LLM with structured data and guidance.
    """
    # Keep it compact and explicit. We do not use actual JSON dumps to avoid escaping issues in some LLMs.
    scope_str = f'"scope": "{scope}"' + (f', "uf": "{uf}"' if uf else "")
    as_of_str = f'"as_of_day": "{as_of_day}"' if as_of_day else '"as_of_day": null'

    def lines_from_list(label: str, items: List[Dict[str, Any]]) -> str:
        if not items:
            return f'"{label}": []'
        # Brief, single-line per item (avoid multi-line explosions)
        rendered = []
        for it in items[:10]:
            flat = {k: it.get(k) for k in ("title", "url", "source", "published_at", "summary")}
            rendered.append(str(flat))
        return f'"{label}": [\n    ' + ",\n    ".join(rendered) + "\n  ]"

    def lines_from_points(label: str, pts: List[Dict[str, Any]]) -> str:
        if not pts:
            return f'"{label}": []'
        rendered = [f'{{"x": "{p.get("x")}", "y": {p.get("y")}}}' for p in pts]
        return f'"{label}": [\n    ' + ",\n    ".join(rendered) + "\n  ]"

    notes_block = ""
    if notes:
        notes_block = '"notes": [\n    ' + ",\n    ".join([f'"{n}"' for n in notes[:10]]) + "\n  ],\n  "

    payload = (
        "{\n"
        f'  {scope_str},\n'
        f'  {as_of_str},\n'
        f'  "kpis": {str(kpis)},\n'
        f'  {lines_from_points("daily_series_30d", daily_series_30d)},\n'
        f'  {lines_from_points("monthly_series_12m", monthly_series_12m)},\n'
        f'  {lines_from_list("news", news)},\n'
        f'  {notes_block}"guidelines": "Siga fielmente as instruções das métricas e limitações fornecidas."\n'
        "}"
    )

    user_text = (
        "Dados estruturados do relatório (não invente números; use apenas o payload abaixo):\n"
        f"{payload}\n\n"
        "Siga estritamente as diretrizes abaixo e gere o relatório com a estrutura pedida.\n"
        f"{AGENT_METRIC_GUIDELINES_PT}"
    )
    return user_text
