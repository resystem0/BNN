# axon-graph

Knowledge-graph narrative traversal subnet on Bittensor.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Components

| Command | Description |
|---------|-------------|
| `axon-validator` | Run the subnet validator |
| `axon-domain-miner` | Run a domain (RAG) miner |
| `axon-narrative-miner` | Run a narrative (LLM) miner |
| `axon-gateway` | Run the orchestrator FastAPI gateway |

## Configuration

Copy `.env.example` to `.env` and fill in your values.
All environment variables are prefixed with `AXON_`.

## Architecture

```
Gateway (FastAPI)
  └── OrchestratorSession
        ├── Router          — entry-node ranking
        ├── Embedder        — sentence-transformer wrapper
        ├── SafetyGuard     — content safety
        └── Dendrite → Domain Miner (KnowledgeQuery)
                    → Narrative Miner (NarrativeHop)
Validator
  └── ScoringLoop — traversal / quality / topology scores
GraphStore (KùzuDB + in-memory)
```
