#!/usr/bin/env bash
# scripts/run_local_testnet.sh
# ---------------------------------------------------------------------------
# Spin up the full axon-graph local dev environment in a tmux session.
#
# What this does:
#   1. Starts docker-compose dev stack (redis, chroma, ipfs, subtensor)
#   2. Waits for subtensor to be ready
#   3. Seeds the knowledge graph (seed_graph.py)
#   4. Creates and funds test wallets (validator + 2 miners)
#   5. Registers the subnet (netuid 1) on localnet
#   6. Opens a tmux session with panes for:
#        - validator process
#        - domain miner (quantum_mechanics)
#        - narrative miner
#        - orchestrator gateway
#        - log tail
#
# Requirements:
#   - tmux >= 3.0
#   - docker compose v2
#   - python >= 3.10 with axon-graph installed (pip install -e .)
#   - btcli installed (comes with bittensor)
#
# Usage:
#   chmod +x scripts/run_local_testnet.sh
#   ./scripts/run_local_testnet.sh
#   ./scripts/run_local_testnet.sh --no-tmux   # just start docker + seed, no processes
#   ./scripts/run_local_testnet.sh --reset      # wipe volumes and re-seed
# ---------------------------------------------------------------------------

set -euo pipefail

# ── Config ─────────────────────────────────────────────────────────────────
SESSION="axon-dev"
NETUID=1
SUBTENSOR_WS="ws://localhost:9944"
COMPOSE_FILE="docker-compose.dev.yml"
NODES_FILE="config/nodes.yaml"
DB_PATH="./data/kuzu"
LOG_DIR="./logs"

VALIDATOR_WALLET="validator_local"
MINER_A_WALLET="miner_domain_a"
MINER_B_WALLET="miner_narrative_b"

NO_TMUX=false
RESET=false

# ── Parse args ──────────────────────────────────────────────────────────────
for arg in "$@"; do
  case $arg in
    --no-tmux) NO_TMUX=true ;;
    --reset)   RESET=true ;;
    *) echo "Unknown argument: $arg"; exit 1 ;;
  esac
done

# ── Helpers ─────────────────────────────────────────────────────────────────
log()  { echo -e "\033[1;34m[axon]\033[0m $*"; }
ok()   { echo -e "\033[1;32m[  ok]\033[0m $*"; }
warn() { echo -e "\033[1;33m[warn]\033[0m $*"; }
die()  { echo -e "\033[1;31m[ err]\033[0m $*"; exit 1; }

require() {
  command -v "$1" &>/dev/null || die "$1 is required but not installed."
}

wait_for_port() {
  local host=$1 port=$2 label=$3 retries=${4:-30}
  log "Waiting for $label ($host:$port) ..."
  for i in $(seq 1 $retries); do
    nc -z "$host" "$port" 2>/dev/null && ok "$label is up" && return 0
    sleep 2
  done
  die "$label did not become ready in time."
}

# ── Pre-flight ──────────────────────────────────────────────────────────────
require tmux
require docker
require python3
require btcli

mkdir -p "$LOG_DIR" data/kuzu

# ── Docker stack ────────────────────────────────────────────────────────────
log "Starting docker compose stack ..."

if [ "$RESET" = true ]; then
  warn "Reset requested — wiping volumes ..."
  docker compose -f "$COMPOSE_FILE" down -v --remove-orphans 2>/dev/null || true
  rm -rf "$DB_PATH"
fi

docker compose -f "$COMPOSE_FILE" up -d

wait_for_port localhost 6379  "Redis"      20
wait_for_port localhost 8001  "ChromaDB"   20
wait_for_port localhost 5001  "IPFS API"   30
wait_for_port localhost 9944  "Subtensor"  40

ok "All docker services healthy."

# ── Seed graph ───────────────────────────────────────────────────────────────
if [ "$RESET" = true ] || [ ! -d "$DB_PATH" ]; then
  log "Seeding graph from $NODES_FILE ..."
  python3 scripts/seed_graph.py \
    --db-path "$DB_PATH" \
    --nodes-file "$NODES_FILE" \
    --reset \
    2>&1 | tee "$LOG_DIR/seed_graph.log"
  ok "Graph seeded."
else
  log "Graph DB already exists at $DB_PATH — skipping seed (use --reset to re-seed)."
fi

# ── Create wallets ────────────────────────────────────────────────────────────
create_wallet_if_missing() {
  local name=$1
  if [ ! -d "$HOME/.bittensor/wallets/$name" ]; then
    log "Creating wallet: $name"
    btcli wallet create --wallet.name "$name" --wallet.hotkey default --no_prompt \
      2>&1 | tail -5
  else
    log "Wallet $name already exists."
  fi
}

create_wallet_if_missing "$VALIDATOR_WALLET"
create_wallet_if_missing "$MINER_A_WALLET"
create_wallet_if_missing "$MINER_B_WALLET"

# ── Fund wallets on localnet ──────────────────────────────────────────────────
log "Faucet-funding wallets on localnet ..."
for WALLET in "$VALIDATOR_WALLET" "$MINER_A_WALLET" "$MINER_B_WALLET"; do
  btcli wallet faucet \
    --wallet.name "$WALLET" \
    --subtensor.network "$SUBTENSOR_WS" \
    --no_prompt \
    2>&1 | tail -3 || warn "Faucet for $WALLET may have already run."
done

# ── Create subnet ─────────────────────────────────────────────────────────────
log "Creating subnet netuid=$NETUID ..."
btcli subnet create \
  --wallet.name "$VALIDATOR_WALLET" \
  --subtensor.network "$SUBTENSOR_WS" \
  --no_prompt \
  2>&1 | tail -5 || warn "Subnet may already exist."

ok "Localnet setup complete."

if [ "$NO_TMUX" = true ]; then
  log "--no-tmux passed. Docker stack and graph are ready. Exiting."
  exit 0
fi

# ── tmux session ──────────────────────────────────────────────────────────────
log "Launching tmux session: $SESSION"

# Kill existing session if present
tmux kill-session -t "$SESSION" 2>/dev/null || true

# Create new session (detached)
tmux new-session -d -s "$SESSION" -x 220 -y 50

# ── Window 0: validator ──────────────────────────────────────────────────────
tmux rename-window -t "$SESSION:0" "validator"
tmux send-keys -t "$SESSION:0" "
echo '=== VALIDATOR ===' &&
python3 -m subnet.validator \
  --wallet.name $VALIDATOR_WALLET \
  --wallet.hotkey default \
  --subtensor.network $SUBTENSOR_WS \
  --netuid $NETUID \
  --logging.debug \
  2>&1 | tee $LOG_DIR/validator.log
" Enter

# ── Window 1: domain miner ────────────────────────────────────────────────────
tmux new-window -t "$SESSION" -n "domain-miner"
tmux send-keys -t "$SESSION:domain-miner" "
echo '=== DOMAIN MINER (quantum_mechanics) ===' &&
python3 -m miners.domain.miner \
  --wallet.name $MINER_A_WALLET \
  --wallet.hotkey default \
  --subtensor.network $SUBTENSOR_WS \
  --netuid $NETUID \
  --node-id quantum_mechanics \
  --corpus-dir ./data/corpora/quantum_mechanics \
  --axon.port 8091 \
  --logging.debug \
  2>&1 | tee $LOG_DIR/domain_miner.log
" Enter

# ── Window 2: narrative miner ─────────────────────────────────────────────────
tmux new-window -t "$SESSION" -n "narrative-miner"
tmux send-keys -t "$SESSION:narrative-miner" "
echo '=== NARRATIVE MINER ===' &&
python3 -m miners.narrative.miner \
  --wallet.name $MINER_B_WALLET \
  --wallet.hotkey default \
  --subtensor.network $SUBTENSOR_WS \
  --netuid $NETUID \
  --axon.port 8110 \
  --venice-api-key \${VENICE_API_KEY:-''} \
  --logging.debug \
  2>&1 | tee $LOG_DIR/narrative_miner.log
" Enter

# ── Window 3: orchestrator gateway ────────────────────────────────────────────
tmux new-window -t "$SESSION" -n "gateway"
tmux send-keys -t "$SESSION:gateway" "
echo '=== ORCHESTRATOR GATEWAY ===' &&
python3 -m orchestrator.gateway \
  --wallet.name $VALIDATOR_WALLET \
  --wallet.hotkey default \
  --subtensor.network $SUBTENSOR_WS \
  --netuid $NETUID \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  2>&1 | tee $LOG_DIR/gateway.log
" Enter

# ── Window 4: logs ────────────────────────────────────────────────────────────
tmux new-window -t "$SESSION" -n "logs"
tmux send-keys -t "$SESSION:logs" "
tail -f $LOG_DIR/validator.log $LOG_DIR/domain_miner.log $LOG_DIR/narrative_miner.log $LOG_DIR/gateway.log
" Enter

# ── Window 5: shell ───────────────────────────────────────────────────────────
tmux new-window -t "$SESSION" -n "shell"
tmux send-keys -t "$SESSION:shell" "
echo 'axon-graph dev shell'
echo ''
echo 'Useful commands:'
echo '  python scripts/seed_graph.py --dry-run'
echo '  python scripts/register_miner.py --node-id quantum_mechanics --dry-run'
echo '  curl http://localhost:8000/healthz'
echo '  curl -X POST http://localhost:8000/enter -H \"Content-Type: application/json\" \\'
echo '       -d \"{\\\"query\\\": \\\"How does quantum entanglement work?\\\"}\"\\'
echo ''
" Enter

# ── Attach ────────────────────────────────────────────────────────────────────
tmux select-window -t "$SESSION:0"
tmux attach-session -t "$SESSION"
