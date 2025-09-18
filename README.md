<p align="center">
  <img src="assets/indicium_logo.png" alt="Indicium" Width="600"
</p>

<h1 align="center">SRAG — Dashboard & Agente</h1>

<p align="center">
  Painel analítico e agente conversacional para SRAG (Síndrome Respiratória Aguda Grave) com
  <b>DuckDB</b>, <b>Streamlit</b> e <b>LLM routing</b> (OpenAI/Groq).
  Inclui <b>ELT</b> bronze→silver→gold, consultas <b>NL→SQL</b> seguras e coleta de <b>notícias</b> do Brasil.
</p>

<p align="center">
  <a href="https://python.org"><img src="https://img.shields.io/badge/Python-3.12%2B-blue.svg" alt="Python 3.12+"></a>
  <a href="https://duckdb.org"><img src="https://img.shields.io/badge/DuckDB-embedded-lightgrey.svg" alt="DuckDB"></a>
  <a href="https://streamlit.io"><img src="https://img.shields.io/badge/Streamlit-App-orange.svg" alt="Streamlit"></a>
  <img src="https://img.shields.io/badge/Status-Active-success.svg" alt="Project status">
</p>

<hr/>

## Visão geral

O projeto entrega dois componentes principais:

1) **Dashboard (Streamlit)**  
   KPIs (janela 30d), séries **diária (30d)** e **mensal (12m)**, ranking de UFs por casos e um **chat** integrado ao agente.

2) **Agente SRAG (LLM-routed)**  
   Entende intenção (PT-first), acessa o **dicionário de dados**, busca **notícias recentes** (Tavily), executa **consultas em linguagem natural → SQL** com *guardrails* e gera relatório padrão (BR/UF).


---

## Principais funcionalidades

- **Relatório padrão** (BR/UF) com sumário executivo, KPIs e comentários.  
- **Notícias recentes** sobre SRAG no Brasil, com **links** das fontes.  
- **Explicação de termos/métricas** (glossário).  
- **NL→SQL (seguro)**: interpreta pedidos em linguagem natural e gera **SELECT** DuckDB válido, com *whitelist* de tabelas e **LIMIT** automático.  
- **Data QA**: perguntas sobre o dicionário/esquema respondidas via LLM com *grounding*.  
- **Tendências**: comentário rápido (7d vs 7d anteriores) com base nas séries do painel.

---

## Stack técnica

- **Linguagem:** Python 3.12+  
- **Frontend:** Streamlit  
- **Banco analítico:** DuckDB (arquivo local `data/srag.duckdb`)  
- **LLM routing:** OpenAI e/ou Groq (fallback automático), controlado por env  
- **Busca de notícias:** Tavily  
- **Templates:** Jinja2 (relatório)  
- **Gráficos:** Plotly

---

## Arquitetura

```mermaid
graph LR

%% ===== FRONTEND =====
subgraph FE["Frontend"]
  FE1["Streamlit UI\n:8501\nsrc/case_indicium/webapp/app.py"]
end

%% ===== AGENT / CORE =====
subgraph CORE["Agent Orchestrator"]
  CORE1["Intent Router\nintent_router.py"]
  CORE2["LLM Router\nllm_router.py\nProviders: OpenAI, GROQ"]
  CORE3["Tools Manager"]
  CORE4["Memory / Context Store"]
end

%% ===== TOOLS =====
subgraph TOOLS["Agent Tools"]
  T1["NL to SQL Orchestrator\ntools.query_nl()"]
  T2["Data QA and Glossary\ntools.answer_data_question()\ntools.glossary_lookup()"]
  T3["Reports and Time Series\ngenerator.build_report()\ntools.get_series()"]
  T4["SQL Client\nagent/sql_client.py"]
end

%% ===== DATA LAYER =====
subgraph DATA["Data Layer (DuckDB + Files)"]
  DB0[("data/srag.duckdb")]
  BR["bronze.*"]
  SI["silver.*"]
  GD1["gold.fct_daily_uf"]
  GD2["gold.fct_monthly_uf"]
  RAW[("data/raw/*")]
end

%% ===== ELT =====
subgraph ELT["ELT Pipeline"]
  E1["Bronze\nscripts/run_bronze.py"]
  E2["Silver\nscripts/run_silver.py"]
  E3["Gold\nscripts/run_gold.py"]
end

%% ===== INFRA =====
subgraph INFRA["Infra / Runtime (Docker Compose)"]
  S1["Service: app\ndocker/Dockerfile\nENV: OPENAI_API_KEY, GROQ_API_KEY,\nDATA_DIR=/data, RUN_PIPELINE"]
  S2["Service: elt (one-off)\ndocker/Dockerfile\nRUN_PIPELINE=1"]
  VOL["Bind volume\n./data -> /data"]
end

%% ===== FLOWS =====
FE1 -->|prompt / inputs| CORE1
CORE1 --> CORE2
CORE1 --> CORE3
CORE2 -->|calls| CORE3
CORE3 -->|uses| CORE4

CORE3 --> T1
CORE3 --> T2
CORE3 --> T3
CORE3 --> T4

T1 --> T4
T2 --> T4
T3 --> T4
T4 -->|queries| DB0

DB0 --- BR
DB0 --- SI
DB0 --- GD1
DB0 --- GD2

RAW --> E1
E1 --> BR
E2 --> SI
E3 --> GD1
E3 --> GD2

S1 --> VOL
S2 --> VOL
VOL --> DB0
VOL --> RAW

%% ===== STYLES =====
classDef fe    fill:#e6f7ff,stroke:#9cc3ff,color:#043959
classDef core  fill:#eef7ff,stroke:#9cc3ff,color:#043959
classDef tools fill:#f7f7e8,stroke:#d9d9a8,color:#4d4a2a
classDef data  fill:#f0fff4,stroke:#a2d9a2,color:#185a1b
classDef elt   fill:#fff8e6,stroke:#ffd27f,color:#5d3e00
classDef infra fill:#fff0f6,stroke:#f5a3c7,color:#6b1035
classDef hub   fill:#ffffff,stroke:#7aa7ff,stroke-width:2px

class FE1 fe
class CORE1,CORE2,CORE3,CORE4 core
class T1,T2,T3,T4 tools
class DB0,BR,SI,GD1,GD2,RAW data
class E1,E2,E3 elt
class S1,S2,VOL infra

class DB0 hub
class CORE3 hub

linkStyle default stroke:#7aa7ff,stroke-width:1.5px


```

---

## Modelo de dados (camada gold)

Tabelas principais usadas pelo painel e pelo NL→SQL:

- `gold.fct_daily_uf(day, uf, cases, deaths, icu_cases, vaccinated_cases, pending_60d_cases, closed_cases_30d, deaths_30d, median_symptom_to_notification_days, median_icu_los_days, cfr_closed_30d_pct, icu_rate_pct, vaccinated_rate_pct, pending_60d_pct, cases_ma7, deaths_ma7)`

- `gold.fct_monthly_uf(month, uf, cases, deaths, icu_cases, vaccinated_cases, pending_60d_cases, closed_cases_30d, deaths_30d, median_symptom_to_notification_days, median_icu_los_days, cfr_closed_30d_pct, icu_rate_pct, vaccinated_rate_pct, pending_60d_pct)`

> O agente NL→SQL está **restrito** por padrão às tabelas `gold.*` para reduzir risco e simplificar o contexto.

---

## Agente — intenções & ferramentas

### Intenções suportadas
- `greet` — saudação/apresentação  
- `news` — últimas notícias (com links)  
- `report` — relatório padrão (BR/UF)  
- `explain` — explicação de termo/métrica  
- `dataqa` — perguntas sobre dicionário/esquema/colunas  
- `nlquery` — consulta em linguagem natural → SQL seguro  
- `trend` — comentário de tendência (7d vs 7d anteriores)  
- `compare` — comparação/ranking (placeholder)  
- `chitchat` — conversa leve sem números operacionais  
- `unknown` — fallback para pedir mais detalhes

### Ferramentas principais (`agent/tools.py`)
- **`answer_data_question()`**: QA do dicionário de dados com *grounding* em tabelas/colunas/métricas.  
- **`nl_to_sql()`**: traduz PT → SQL DuckDB (somente `SELECT`), sempre com `LIMIT`.  
- **`run_sql_text_safe()`**: executa SQL *read-only*, bloqueando DDL/DML e checando *whitelist* de tabelas.  
- **`query_nl()`**: *pipeline* de alto nível (NL→SQL→exec) que retorna `(DataFrame, SQL)`.  
- **`build_schema_snapshot()`**: snapshot do esquema + métricas para orientar o LLM (contexto compacto).

---

## Organização do repositório

```
case-indicium/
├─ src/case_indicium/
│  ├─ agent/           # agente, intent router, news client, tools NL→SQL, etc.
│  ├─ etl/             # bronze/silver e orquestração local
│  ├─ sql/             # views/checagens para camada gold
│  ├─ templates/       # Jinja2 (ex.: report.md.j2)
│  ├─ utils/           # utilitários (config, duckdb, io)
│  └─ webapp/          # app Streamlit (app.py)
├─ assets/             # logos/imagens do app
├─ data/               # srag.duckdb e raw/
├─ notebooks/          # EDA (dev)
├─ scripts/            # scripts utilitários
├─ .streamlit/         # config do Streamlit
├─ .env.example        # exemplo de variáveis de ambiente
├─ pyproject.toml      # deps (Poetry)
└─ README.md
```

---

## Variáveis de ambiente

Arquivo `.env` (exemplo em `.env.example`):

```env
# LLMs (pelo menos uma)
OPENAI_API_KEY=sk-xxxx
GROQ_API_KEY=gsk_xxxx

# Busca de notícias
TAVILY_API_KEY=tvly-dev-xxxx
```

---

## Como rodar
### 1. Configurar o .env
```
cp .env.example .env
# Configurar as API Keys
```
### 2. Build da Imagem Docker
```
docker compose build
```
### 3. Rodar o ELT
```
docker compose run --rm etl

```
#### Esse processo irá demorar um pouco, devido ao download de todos os arquivos CSVs

### 4. Subir o app
```
docker compose up -d app
docker compose logs -f app
```
### Com isso basta Acessar: http://localhost:8501
### 5. Parar serviços
```
docker compose down
```


## Fluxos de trabalho

- **ELT local**: Ingestão de bases SRAG (bronze) → padronização/limpeza (silver) → fatos & views (gold).  
- **Relatório padrão**: `agent/generator.py` + `templates/report.md.j2` produzem markdown com KPIs/séries.  
- **Agente no app**: o Streamlit usa `intent_router.handle()` para rotear a mensagem e acionar as *tools*.

---

## Possiveis Melhorias Futuras

- Melhorar tratamento e Limpeza de Dados.  
- Mais testes para NL→SQL e *guardrails*.  
- Cache para notícias.  
- Mais tabelas tratadas e relacionadas.
---

