"""
config/subnet_config.py

Single source of truth for all protocol constants across axon-graph.

Every other package imports from here. Changing a value here changes it
everywhere. All tunable parameters are grouped by subsystem with the
reasoning behind each default documented inline.

Environment overrides: any constant can be overridden at runtime by setting
an environment variable of the same name prefixed with AXON_, e.g.:
    AXON_NETUID=24 python -m miners.domain.miner ...
This allows per-deployment tuning without code changes.
"""

from __future__ import annotations
import os
from typing import Final


def _env(key: str, default):
    """Read AXON_{KEY} from environment, cast to the type of default."""
    raw = os.environ.get(f"AXON_{key}")
    if raw is None:
        return default
    try:
        return type(default)(raw)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Network identity
# ---------------------------------------------------------------------------

NETUID: Final[int] = _env("NETUID", 42)
# The subnet UID on the Bittensor network. Change to a local testnet value
# (e.g. 1) when developing against btcli localnet.

NETWORK: Final[str] = _env("NETWORK", "finney")
# "finney" = mainnet, "test" = testnet, "local" = local subtensor node.

SPEC_VERSION: Final[int] = 1
# Increment when the synapse wire format changes incompatibly.
# Validators reject miners whose spec_version differs from their own.


# ---------------------------------------------------------------------------
# Embedding model
# ---------------------------------------------------------------------------

EMBEDDING_MODEL: Final[str] = _env(
    "EMBEDDING_MODEL", "sentence-transformers/all-mpnet-base-v2"
)
# 768-dim output. All embeddings across the system — query, passage,
# corpus centroid, domain centroid — must use the same model.
# Switching models requires a full corpus re-index and manifest refresh.

EMBEDDING_DIM: Final[int] = 768
# Must match the output dimension of EMBEDDING_MODEL.

EMBEDDING_BATCH_SIZE: Final[int] = 64
# Chunks to embed in a single SentenceTransformer forward pass.
# Larger = faster ingestion, higher peak RAM. 64 fits comfortably in 4 GB.


# ---------------------------------------------------------------------------
# Domain miner
# ---------------------------------------------------------------------------

DOMAIN_MINER_TOP_K: Final[int] = _env("DOMAIN_MINER_TOP_K", 5)
# Chunks returned per KnowledgeQuery. Validators sample 3 for Merkle
# challenges; the narrative miner uses all 5 for context assembly.

CHUNK_MAX_TOKENS: Final[int] = 256
# Corpus chunks are split to this token ceiling during ingestion.
# Shorter chunks improve retrieval precision; longer chunks give the
# narrative miner more coherent context per result.

CHUNK_OVERLAP_TOKENS: Final[int] = 32
# Sliding window overlap between adjacent chunks.
# Prevents a sentence split exactly at a chunk boundary from losing context.

CHUNK_CHALLENGE_PORT: Final[int] = _env("CHUNK_CHALLENGE_PORT", 8092)
# Port for the domain miner's Merkle proof HTTP sidecar.
# Must not conflict with the axon port (default 8091).

CORPUS_REFRESH_GRACE_BLOCKS: Final[int] = 7200
# Blocks a miner has to submit an updated manifest after a corpus_refresh
# warning before validators begin penalising scores.


# ---------------------------------------------------------------------------
# Narrative miner
# ---------------------------------------------------------------------------

NARRATIVE_MODEL: Final[str] = _env(
    "NARRATIVE_MODEL", "mistralai/Mistral-7B-Instruct-v0.2"
)
# Base model served by vLLM. Can be swapped for a fine-tuned checkpoint
# by pointing to a local HuggingFace-format directory.

NARRATIVE_MAX_TOKENS: Final[int] = _env("NARRATIVE_MAX_TOKENS", 400)
# Maximum tokens the narrative miner generates per NarrativeHop response.
# 300-400 tokens ≈ 2-3 short paragraphs — enough for atmosphere without
# overwhelming the player UI.

NARRATIVE_TEMPERATURE: Final[float] = 0.75
# Sampling temperature for the narrative LLM.
# 0.75 balances creativity with coherence. Lower = more deterministic
# (good for scoring consistency), higher = more varied (good for replayability).

NARRATIVE_TOP_P: Final[float] = 0.9
# Nucleus sampling cutoff. Works with temperature to prevent degenerate outputs.

SESSION_CACHE_TTL_SECONDS: Final[int] = 60 * 60 * 24 * 7
# How long a session's prior narrative is kept in Redis (7 days).
# Sessions idle longer than this lose narrative continuity on return.

MAX_CHOICE_CARDS: Final[int] = 3
# Maximum choice cards a narrative miner may return per hop.
# Enforced by the validator; returning more penalises edge_utility score.

MIN_CHOICE_CARDS: Final[int] = 2
# Returning fewer than this also penalises edge_utility.

EDGE_DELTA_MAX: Final[float] = 0.05
# Maximum absolute edge weight delta a single hop may propose.
# Prevents a miner from manipulating graph topology by returning
# extreme deltas on its own outgoing edges.


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

VALIDATOR_EPOCH_LENGTH_BLOCKS: Final[int] = 360
# How many blocks between validator weight commits (~72 minutes at 12s/block).
# Must match or be a multiple of the subnet's tempo setting on-chain.

VALIDATOR_SAMPLE_SIZE: Final[int] = _env("VALIDATOR_SAMPLE_SIZE", 16)
# Sessions sampled per epoch for scoring. Higher = more accurate weights
# but more validator compute. 16 is sufficient for subnets with <100 miners.

VALIDATOR_TIMEOUT_KNOWLEDGE: Final[float] = 3.0
# Seconds to wait for a KnowledgeQuery response before marking timeout.

VALIDATOR_TIMEOUT_HOP: Final[float] = 5.0
# Seconds to wait for a NarrativeHop response. Longer because LLM
# inference is involved. Timeouts count against the miner's score.

SCORE_WEIGHT_GROUNDEDNESS: Final[float] = 0.40
SCORE_WEIGHT_COHERENCE:    Final[float] = 0.35
SCORE_WEIGHT_EDGE_UTILITY: Final[float] = 0.25
# Must sum to 1.0. Groundedness is weighted highest because fabricating
# domain knowledge is the most harmful failure mode.

assert abs(
    SCORE_WEIGHT_GROUNDEDNESS + SCORE_WEIGHT_COHERENCE + SCORE_WEIGHT_EDGE_UTILITY - 1.0
) < 1e-9, "Score weights must sum to 1.0"

COHERENCE_PRIOR_BLEND: Final[float] = 0.6
# When computing coherence target: blend(prior_passage_emb, domain_centroid_emb).
# 0.6 weights recent narrative continuity over domain identity.
# Lower values keep passages closer to the domain's registered persona.

TOP_QUARTILE_FRACTION: Final[float] = 0.25
# Fraction of scored responses that qualify for the quality pool bonus.

MINER_HISTORY_WINDOW_EPOCHS: Final[int] = 10
# Number of recent epochs used to compute a miner's rolling average score.
# Used for pruning evaluation and weight normalisation.


# ---------------------------------------------------------------------------
# Graph store
# ---------------------------------------------------------------------------

GRAPH_REDIS_HOST: Final[str] = _env("GRAPH_REDIS_HOST", "localhost")
GRAPH_REDIS_PORT: Final[int] = _env("GRAPH_REDIS_PORT", 6379)
GRAPH_REDIS_DB:   Final[int] = _env("GRAPH_REDIS_DB", 0)

EDGE_WEIGHT_FLOOR:  Final[float] = 0.05
# Minimum edge weight. Edges never fully disappear through decay alone —
# they must be explicitly pruned when the source/destination node is pruned.

EDGE_WEIGHT_CEILING: Final[float] = 1.0

EDGE_REINFORCE_DELTA: Final[float] = 0.03
# How much a traversed edge is reinforced per hop, scaled by quality score:
#   delta = EDGE_REINFORCE_DELTA * quality_score

EDGE_DECAY_DELTA: Final[float] = 0.005
# How much non-traversed outgoing edges decay per hop on their source node.

EDGE_WARNING_DECAY_DELTA: Final[float] = 0.02
# Accelerated decay rate applied to all edges of a node under pruning warning.

EDGE_VISIBILITY_THRESHOLD: Final[float] = 0.05
# During edge bridge integration, choice cards for the new node only surface
# once the ramp reaches this weight.

CENTRALITY_RECOMPUTE_INTERVAL_EPOCHS: Final[int] = 6
# Betweenness centrality is expensive on large graphs (O(VE)).
# Recompute every 6 epochs (~7 hours) rather than every epoch.


# ---------------------------------------------------------------------------
# Emission pools
# ---------------------------------------------------------------------------

EMISSION_TRAVERSAL_SHARE:  Final[float] = 0.45
EMISSION_QUALITY_SHARE:    Final[float] = 0.30
EMISSION_TOPOLOGY_SHARE:   Final[float] = 0.15
EMISSION_RESERVE_SHARE:    Final[float] = 0.10

assert abs(
    EMISSION_TRAVERSAL_SHARE + EMISSION_QUALITY_SHARE +
    EMISSION_TOPOLOGY_SHARE  + EMISSION_RESERVE_SHARE - 1.0
) < 1e-9, "Emission pool shares must sum to 1.0"

TRAVERSAL_DOMAIN_SPLIT:    Final[float] = 0.35
# Fraction of traversal pool going to domain miners; rest to narrative miners.

QUALITY_VALIDATOR_CUT:     Final[float] = 0.667
# Fraction of quality pool going to validators; rest as miner top-quartile bonus.

BOND_RETURN_MULTIPLIER:    Final[float] = 1.05
# Successful proposals return their bond × this multiplier.

BOND_LAPSE_RETURN_FRACTION: Final[float] = 0.95
# Proposals that lapse (insufficient quorum, not slashed) return this fraction.


# ---------------------------------------------------------------------------
# Graph evolution — proposals & voting
# ---------------------------------------------------------------------------

PROPOSAL_MIN_BOND_TAO:       Final[float] = 50.0
PROPOSAL_MAX_EDGES:          Final[int]   = 4
PROPOSAL_MAX_INITIAL_WEIGHT: Final[float] = 0.6
PROPOSAL_VOTE_PERIOD_BLOCKS: Final[int]   = 7200   # ~24 hours
PROPOSAL_EXTENSION_BLOCKS:   Final[int]   = 3600   # ~12 hours if quorum not met
PROPOSAL_QUORUM_FRACTION:    Final[float] = 0.25
PROPOSAL_PASS_THRESHOLD:     Final[float] = 0.60

INCUBATION_DURATION_BLOCKS:    Final[int]   = 14400  # ~48 hours
INCUBATION_MIN_QUERY_RESPONSES: Final[int]  = 50
INCUBATION_MIN_HOP_RESPONSES:   Final[int]  = 20
INCUBATION_MIN_AVG_SCORE:       Final[float] = 0.55
INCUBATION_MAX_TIMEOUT_FRACTION: Final[float] = 0.15

INTEGRATION_BRIDGE_WINDOW_BLOCKS: Final[int] = 7200   # ~24 hours

PRUNING_SCORE_WINDOW_BLOCKS:    Final[int]   = 21600  # ~72 hours
PRUNING_THRESHOLD:              Final[float] = 0.35
PRUNING_GRACE_WINDOW_BLOCKS:    Final[int]   = 7200   # ~24 hours
PRUNING_MIN_TRAVERSALS_PER_DAY: Final[int]   = 3

DRIFT_CHECK_INTERVAL_DAYS:  Final[int]   = 90
DRIFT_SAMPLE_SIZE:          Final[int]   = 50
DRIFT_THRESHOLD:            Final[float] = 0.28
DRIFT_REFRESH_GRACE_BLOCKS: Final[int]   = 7200


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

ORCHESTRATOR_HOST: Final[str] = _env("ORCHESTRATOR_HOST", "0.0.0.0")
ORCHESTRATOR_PORT: Final[int] = _env("ORCHESTRATOR_PORT", 8080)

SESSION_REDIS_DB: Final[int] = _env("SESSION_REDIS_DB", 1)
# Separate Redis DB from graph store so flushes don't cross-contaminate.

ENTRY_COSINE_FLOOR: Final[float] = 0.20
# Minimum domain_similarity for a miner to be considered as an entry node.
# Prevents placing a player in a node with no topical relevance to their
# soul token, even if it's the best available option.

MAX_CONCURRENT_SESSIONS: Final[int] = _env("MAX_CONCURRENT_SESSIONS", 500)


# ---------------------------------------------------------------------------
# SubnetConfig — class wrapper so code can do cfg = SubnetConfig()
# ---------------------------------------------------------------------------

class SubnetConfig:
    """
    Class wrapper around the module-level constants.  Instantiated once per
    component so configuration can be injected / mocked in tests.
    All attributes mirror the module-level constants above; additional
    operational constants that don't require an on-chain override live here.
    """

    # ── Network identity ────────────────────────────────────────────────
    NETUID:   int   = NETUID
    NETWORK:  str   = NETWORK
    SPEC_VERSION: int = SPEC_VERSION

    # ── Embedding ───────────────────────────────────────────────────────
    EMBEDDING_MODEL:      str = EMBEDDING_MODEL
    EMBEDDING_DIM:        int = EMBEDDING_DIM
    EMBEDDING_BATCH_SIZE: int = EMBEDDING_BATCH_SIZE

    # ── Domain miner ────────────────────────────────────────────────────
    DOMAIN_MINER_TOP_K:   int   = DOMAIN_MINER_TOP_K
    CHUNK_MAX_TOKENS:     int   = CHUNK_MAX_TOKENS
    CHUNK_OVERLAP_TOKENS: int   = CHUNK_OVERLAP_TOKENS
    MINER_AXON_PORT:      int   = _env("MINER_AXON_PORT", 8091)
    NARRATIVE_AXON_PORT:  int   = _env("NARRATIVE_AXON_PORT", 8093)
    MINER_SYNC_INTERVAL_S: float = _env("MINER_SYNC_INTERVAL_S", 60.0)
    WHITELIST_HOTKEYS:    list  = []       # populated from env / YAML at startup
    SCORING_TOP_K:        int   = _env("SCORING_TOP_K", 5)
    CHALLENGE_TOP_K:      int   = _env("CHALLENGE_TOP_K", 3)
    CHALLENGE_TIMEOUT:    float = _env("CHALLENGE_TIMEOUT", 3.0)
    LATENCY_SOFT_LIMIT_S: float = _env("LATENCY_SOFT_LIMIT_S", 2.0)
    LATENCY_MAX_PENALTY:  float = 0.30
    LATENCY_PENALTY_PER_S: float = 0.10

    # ── Narrative miner ─────────────────────────────────────────────────
    NARRATIVE_MODEL:       str   = NARRATIVE_MODEL
    NARRATIVE_MAX_TOKENS:  int   = NARRATIVE_MAX_TOKENS
    NARRATIVE_TEMPERATURE: float = NARRATIVE_TEMPERATURE
    NARRATIVE_TOP_P:       float = NARRATIVE_TOP_P
    MIN_HOP_WORDS:         int   = 80
    MAX_HOP_WORDS:         int   = 220
    SESSION_CACHE_TTL_SECONDS: int = SESSION_CACHE_TTL_SECONDS

    # ── Validator ───────────────────────────────────────────────────────
    EPOCH_LENGTH_BLOCKS:   int   = VALIDATOR_EPOCH_LENGTH_BLOCKS
    EPOCH_SLEEP_S:         float = 12.0 * VALIDATOR_EPOCH_LENGTH_BLOCKS
    VALIDATOR_SAMPLE_SIZE: int   = VALIDATOR_SAMPLE_SIZE
    QUERY_TIMEOUT:         float = VALIDATOR_TIMEOUT_KNOWLEDGE
    NARRATIVE_TIMEOUT:     float = VALIDATOR_TIMEOUT_HOP
    TRAVERSAL_WEIGHT:      float = SCORE_WEIGHT_GROUNDEDNESS
    QUALITY_WEIGHT:        float = SCORE_WEIGHT_COHERENCE
    TOPOLOGY_WEIGHT:       float = SCORE_WEIGHT_EDGE_UTILITY
    CORPUS_WEIGHT:         float = 0.0
    VALIDATOR_TRUST_MIN:   float = 0.5
    COMMIT_TIMEOUT:        float = 5.0
    COMMIT_QUORUM:         float = 0.51

    # ── Graph store ─────────────────────────────────────────────────────
    GRAPH_REDIS_HOST: str   = GRAPH_REDIS_HOST
    GRAPH_REDIS_PORT: int   = GRAPH_REDIS_PORT
    GRAPH_REDIS_DB:   int   = GRAPH_REDIS_DB
    EDGE_DECAY_RATE:  float = EDGE_DECAY_DELTA * 10   # per-epoch decay rate

    # ── Orchestrator / session ───────────────────────────────────────────
    ORCHESTRATOR_HOST:      str  = ORCHESTRATOR_HOST
    ORCHESTRATOR_PORT:      int  = ORCHESTRATOR_PORT
    SESSION_REDIS_DB:       int  = SESSION_REDIS_DB
    MAX_CONCURRENT_SESSIONS: int = MAX_CONCURRENT_SESSIONS
    DEFAULT_MAX_HOPS:       int  = 5
    SESSION_RETRIEVAL_TOP_K: int = 5
    MAX_NEXT_NODES:         int  = 4
    SESSION_MAX_TOKENS:     int  = 512
    GATEWAY_CORS_ORIGINS:   list = ["*"]

    # ── Evolution / proposals ────────────────────────────────────────────
    MIN_PROPOSAL_BOND:    float = PROPOSAL_MIN_BOND_TAO
    DEFAULT_PROPOSAL_BOND: float = PROPOSAL_MIN_BOND_TAO
    MAX_PROPOSAL_ADJACENCY: int  = PROPOSAL_MAX_EDGES
    VOTING_WINDOW_BLOCKS: int   = PROPOSAL_VOTE_PERIOD_BLOCKS
    BOND_ESCROW_ADDRESS:  str   = _env("BOND_ESCROW_ADDRESS", "")

    # ── Drift detection ─────────────────────────────────────────────────
    DRIFT_THRESHOLD:          float = DRIFT_THRESHOLD
    DRIFT_WINDOW_EPOCHS:      int   = 10    # rolling window for drift detection
    DRIFT_BASELINE_EPOCHS:    int   = 3     # epochs to establish baseline cosine
    DRIFT_CONSECUTIVE_EPOCHS: int   = 3     # consecutive below-threshold epochs to flag
    DRIFT_DROP_THRESHOLD:     float = 0.28  # hard cosine drop from baseline to flag

    # ── Validator challenges ─────────────────────────────────────────────
    CHALLENGE_MAX_TOKENS: int = _env("CHALLENGE_MAX_TOKENS", 200)

    # ── Emission pools ───────────────────────────────────────────────────
    # Traversal pool: balance between retrieval quality and actual usage
    TRAVERSAL_USAGE_WEIGHT: float = 0.5
    # Quality pool sub-weights (must sum to 1.0)
    QUALITY_COHERENCE_WEIGHT:  float = 0.5
    QUALITY_WORDCOUNT_WEIGHT:  float = 0.3
    QUALITY_FINISH_WEIGHT:     float = 0.2
    # Topology pool
    TOPOLOGY_BETWEENNESS_WEIGHT: float = 0.6
    TOPOLOGY_SOFTMAX_TEMP:       float = 1.0

    # ── Metagraph watcher ────────────────────────────────────────────────
    METAGRAPH_SYNC_INTERVAL_S: float = _env("METAGRAPH_SYNC_INTERVAL_S", 60.0)

    # ── Voting ───────────────────────────────────────────────────────────
    MIN_VALIDATOR_STAKE_TO_VOTE: float = _env("MIN_VALIDATOR_STAKE_TO_VOTE", 1000.0)
    VOTE_QUORUM_PARTICIPATION:   float = PROPOSAL_QUORUM_FRACTION
    VOTE_APPROVAL_THRESHOLD:     float = PROPOSAL_PASS_THRESHOLD

    # ── Node integration ─────────────────────────────────────────────────
    FORESHADOW_OFFSET_BLOCKS:    int   = 360    # ~1 hour before bridge open
    BRIDGE_OPEN_OFFSET_BLOCKS:   int   = 720    # ~2 hours after acceptance
    EDGE_RAMP_BLOCKS:            int   = 3600   # ~12 hours to ramp to 1.0
    INTEGRATION_MIN_EDGE_WEIGHT: float = EDGE_VISIBILITY_THRESHOLD

    # ── Pruning ──────────────────────────────────────────────────────────
    PRUNE_SCORE_WINDOW:          int   = 20     # rolling window size in epochs
    PRUNE_MEAN_THRESHOLD:        float = PRUNING_THRESHOLD
    PRUNE_CONSECUTIVE_THRESHOLD: float = 0.25   # per-epoch threshold for streak
    PRUNE_CONSECUTIVE_EPOCHS:    int   = 5      # streak length to trigger warning
    PRUNE_RECOVERY_THRESHOLD:    float = 0.50
    PRUNE_WARNING_EPOCHS:        int   = 5      # epochs in warning before decay
    PRUNE_DECAY_EPOCHS:          int   = 10     # epochs to decay before collapse
    PRUNE_AGGRESSIVE_DECAY_RATE: float = EDGE_WARNING_DECAY_DELTA
