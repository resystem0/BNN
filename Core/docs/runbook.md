# Axon-Graph Operator Runbook

**System:** Bittensor Subnet 42 — Knowledge-Graph Narrative Traversal
**Kubernetes Namespace:** `axon-graph`
**Last Updated:** 2026-03-15
**Maintained By:** See [Emergency Contacts](#emergency-contacts)

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Monitoring Dashboards](#monitoring-dashboards)
3. [Procedure 1: Miner Restart](#procedure-1-miner-restart)
4. [Procedure 2: Corpus Refresh](#procedure-2-corpus-refresh)
5. [Procedure 3: Emergency Node Pruning](#procedure-3-emergency-node-pruning)
6. [Procedure 4: Validator Key Rotation](#procedure-4-validator-key-rotation)
7. [Alert Response Guides](#alert-response-guides)
8. [kubectl Cheat Sheet](#kubectl-cheat-sheet)
9. [Emergency Contacts](#emergency-contacts)

---

## System Overview

Axon-Graph is a knowledge-graph narrative traversal system running on Bittensor Subnet 42. Players traverse a live knowledge graph via narrative prompts; miners respond with contextually grounded paths; validators score miner outputs and commit weights on-chain.

### Component Reference

| Component | Type | Port(s) | Replicas | Notes |
|---|---|---|---|---|
| `gateway` | FastAPI | 8000 | 1+ | Public API entrypoint |
| `domain-miner` | Python/bittensor | 8091 | 8 | Domain knowledge graph miners |
| `narrative-miner` | Python/bittensor | 8092 | 4 | Narrative path synthesis miners |
| `validator` | Python/bittensor | 8093 | 3 | Subtensor weight commit validators |
| `redis` | Session cache | 6379 | 1 | Player session state |
| `kuzudb` | Graph store (PVC) | 7474 | 1 | Stateful — handle with care |
| `ipfs` | Corpus pinning (PVC) | 5001/8080 | 1 | Stateful — handle with care |
| `prometheus` | Metrics scrape | 9090 | 1 | — |
| `grafana` | Dashboards | 3000 | 1 | — |

### Namespace Quick Check

```bash
kubectl get all -n axon-graph
```

---

## Monitoring Dashboards

All dashboards are hosted on Grafana at port `3000`.

| Dashboard | URL | Purpose |
|---|---|---|
| Axon-Graph Overview | `http://<grafana-host>:3000/d/axon-graph/overview` | System health at a glance |
| Miner Performance | `http://<grafana-host>:3000/d/axon-graph/miners` | Per-miner timeout rates, response latency |
| Validator Status | `http://<grafana-host>:3000/d/axon-graph/validators` | Weight commits, online status, key age |
| Graph Store Health | `http://<grafana-host>:3000/d/axon-graph/graphstore` | KùzuDB write latency, PVC usage |
| Session & Gateway | `http://<grafana-host>:3000/d/axon-graph/gateway` | Active sessions, gateway RPS, Redis hit rate |

To resolve `<grafana-host>` in-cluster:

```bash
kubectl get svc grafana -n axon-graph -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
```

---

## Procedure 1: Miner Restart

**Use when:** Deploying a new miner image, recovering a stuck/OOMKilled pod, or responding to `MinerHighTimeoutRate` alert.

**Estimated downtime:** Near-zero. Active sessions route around restarting pods via Redis session affinity.

### 1.1 Pre-Restart Checks

1. Confirm the target deployment and current image:

```bash
# For domain-miner
kubectl get deployment domain-miner -n axon-graph -o jsonpath='{.spec.template.spec.containers[0].image}'

# For narrative-miner
kubectl get deployment narrative-miner -n axon-graph -o jsonpath='{.spec.template.spec.containers[0].image}'
```

2. Check how many replicas are currently healthy (you need at least half healthy before restarting):

```bash
kubectl get deployment domain-miner -n axon-graph
kubectl get deployment narrative-miner -n axon-graph
```

3. Verify the gateway's session routing is Redis-backed (required for zero-downtime restart):

```bash
kubectl get configmap gateway-config -n axon-graph -o jsonpath='{.data.SESSION_BACKEND}'
# Expected output: redis
```

### 1.2 Graceful Rolling Restart (Standard)

Kubernetes performs a rolling restart by default. This replaces pods one at a time while keeping the minimum available count healthy.

```bash
# Restart domain-miner (8 replicas — safe to roll)
kubectl rollout restart deployment/domain-miner -n axon-graph

# Restart narrative-miner (4 replicas — safe to roll)
kubectl rollout restart deployment/narrative-miner -n axon-graph
```

Monitor the rollout in real time:

```bash
kubectl rollout status deployment/domain-miner -n axon-graph --timeout=5m
kubectl rollout status deployment/narrative-miner -n axon-graph --timeout=5m
```

### 1.3 Verify Sessions Rerouted Without Errors

1. Watch gateway error rate during rollout (check Grafana: `axon-graph/gateway` dashboard, or use a quick log tail):

```bash
kubectl logs -f deployment/gateway -n axon-graph --since=2m | grep -E 'ERROR|502|503|session'
```

2. Confirm Redis session keys are still present after restart (sessions must not have been flushed):

```bash
kubectl exec -n axon-graph deployment/redis -- redis-cli DBSIZE
# Compare with pre-restart count; should be equal or only slightly lower (natural expiry)
```

3. Check that miner endpoints are re-registered in the gateway's upstream list:

```bash
kubectl logs -f deployment/gateway -n axon-graph --since=1m | grep -E 'registered|upstream|miner'
```

4. Confirm new pods are passing liveness and readiness probes:

```bash
kubectl get pods -n axon-graph -l app=domain-miner
kubectl get pods -n axon-graph -l app=narrative-miner
# All pods should show STATUS=Running and READY=1/1 (or N/N)
```

### 1.4 Rollback If New Image Fails

> **WARNING:** Rollback will revert all pods in the deployment to the previous image. Only run this if the new image is causing errors or failing readiness probes.

1. Check rollout history:

```bash
kubectl rollout history deployment/domain-miner -n axon-graph
kubectl rollout history deployment/narrative-miner -n axon-graph
```

2. Roll back to the immediately previous revision:

```bash
kubectl rollout undo deployment/domain-miner -n axon-graph
kubectl rollout undo deployment/narrative-miner -n axon-graph
```

3. Roll back to a specific revision (if the last known-good is not revision N-1):

```bash
kubectl rollout undo deployment/domain-miner -n axon-graph --to-revision=<revision-number>
```

4. Verify rollback completed and pods are healthy:

```bash
kubectl rollout status deployment/domain-miner -n axon-graph
kubectl get pods -n axon-graph -l app=domain-miner
```

5. Document the failed image tag in the incident log and open a ticket before re-attempting the upgrade.

---

## Procedure 2: Corpus Refresh

**Use when:** A miner's knowledge corpus is stale, a new data snapshot is available on IPFS, or on-chain manifest hash needs updating after corpus publication.

**Estimated impact:** The target miner(s) will temporarily serve from a stale corpus during pin verification. Player sessions are not interrupted.

### 2.1 Pin the New Corpus to IPFS

1. Identify the new corpus CID (provided by the corpus publisher):

```bash
export NEW_CID="<bafyXXXXXX...>"
```

2. Pin the CID via the in-cluster IPFS node:

```bash
kubectl exec -n axon-graph deployment/ipfs -- ipfs pin add --progress "$NEW_CID"
# Wait for: pinned <CID> recursively
```

3. Verify the pin is persisted:

```bash
kubectl exec -n axon-graph deployment/ipfs -- ipfs pin ls --type=recursive | grep "$NEW_CID"
```

### 2.2 Update the Miner ConfigMap with the New CID

1. Patch the corpus CID in the miner's ConfigMap:

```bash
# For domain-miner
kubectl patch configmap domain-miner-config -n axon-graph \
  --type merge \
  -p "{\"data\":{\"CORPUS_CID\":\"$NEW_CID\"}}"

# For narrative-miner (if applicable)
kubectl patch configmap narrative-miner-config -n axon-graph \
  --type merge \
  -p "{\"data\":{\"CORPUS_CID\":\"$NEW_CID\"}}"
```

2. Trigger a rolling restart so pods pick up the new CID (follow [Procedure 1.2](#12-graceful-rolling-restart-standard)):

```bash
kubectl rollout restart deployment/domain-miner -n axon-graph
```

### 2.3 Trigger On-Chain Re-Registration with Updated Manifest Hash

Once the miner pods are running with the new corpus, trigger re-registration so the updated manifest hash is committed to the subtensor chain:

1. Exec into a running miner pod:

```bash
kubectl exec -it -n axon-graph deployment/domain-miner -- bash
```

2. Inside the pod, run the re-registration script (adjust module path as needed):

```bash
python -m axon.subnet.register \
  --corpus-cid "$NEW_CID" \
  --subtensor.network finney \
  --wallet.name <hotkey-name> \
  --wallet.hotkey <hotkey-file>
```

3. Alternatively, if a registration helper script exists:

```bash
kubectl exec -n axon-graph deployment/domain-miner -- \
  python /app/scripts/reregister.py --cid "$NEW_CID"
```

4. Confirm the transaction was accepted (the script should print the extrinsic hash). Record this hash in the incident log.

### 2.4 Validation Steps

#### Merkle Proof Check

Verify that the new corpus root hash matches the on-chain commitment:

```bash
kubectl exec -n axon-graph deployment/domain-miner -- \
  python /app/scripts/verify_merkle.py --cid "$NEW_CID"
# Expected: "Merkle root verified: <hash> matches on-chain manifest"
```

If this fails, the corpus may be incomplete or the wrong CID was used. Do not proceed until resolved.

#### Centroid Distance Check

Verify that the new corpus embeddings are within acceptable semantic distance from the previous corpus (prevents radical knowledge drift):

```bash
kubectl exec -n axon-graph deployment/domain-miner -- \
  python /app/scripts/check_centroid_distance.py \
    --old-cid "$OLD_CID" \
    --new-cid "$NEW_CID" \
    --max-distance 0.35
# Expected: "Centroid distance: <value> — within threshold"
```

> **WARNING:** If centroid distance exceeds the configured threshold (default `0.35`), the corpus update represents a significant knowledge shift. Escalate to the subnet team before proceeding, as this may affect validator scoring calibration.

#### End-to-End Smoke Test

Send a test narrative query through the gateway and verify a valid path is returned:

```bash
curl -s -X POST http://<gateway-host>:8000/api/traverse \
  -H "Content-Type: application/json" \
  -d '{"prompt": "test traversal", "session_id": "smoke-test-001"}' \
  | jq '.path | length'
# Expected: integer > 0
```

---

## Procedure 3: Emergency Node Pruning

**Use when:** A knowledge node must be removed from KùzuDB due to data quality issues, legal/content requirements, or graph integrity violations (e.g., poison nodes causing invalid traversal paths).

> **WARNING:** Node pruning is a destructive, irreversible operation on the live graph store. Always take a KùzuDB snapshot before proceeding. Coordinate with active session owners — players mid-traversal through the affected node will be affected.

### 3.1 Pre-Prune Snapshot

1. Snapshot the KùzuDB PVC before any changes:

```bash
# Identify the PVC
kubectl get pvc -n axon-graph | grep kuzu

# Create a VolumeSnapshot (requires VolumeSnapshot CRD and CSI driver support)
kubectl apply -f - <<EOF
apiVersion: snapshot.storage.k8s.io/v1
kind: VolumeSnapshot
metadata:
  name: kuzudb-pre-prune-$(date +%Y%m%d%H%M%S)
  namespace: axon-graph
spec:
  volumeSnapshotClassName: csi-hostpath-snapclass
  source:
    persistentVolumeClaimName: kuzudb-data
EOF
```

2. Verify the snapshot is ready:

```bash
kubectl get volumesnapshot -n axon-graph
# Wait for READYTOUSE=true
```

### 3.2 Identify the Target Node

1. Identify the node by its graph ID. If you only have a label or concept name, resolve the ID first:

```bash
kubectl exec -n axon-graph deployment/kuzudb -- \
  kuzu-cli --db /data/axon.db \
  --query "MATCH (n:KnowledgeNode) WHERE n.concept = '<concept-name>' RETURN n.id, n.concept, n.created_at;"
```

2. Inspect the node's edges before pruning:

```bash
kubectl exec -n axon-graph deployment/kuzudb -- \
  kuzu-cli --db /data/axon.db \
  --query "MATCH (n:KnowledgeNode {id: '<node-id>'})-[e]-(m) RETURN type(e), m.id, m.concept, e.weight;"
```

Record all connected node IDs. You will need to verify these after pruning.

### 3.3 Communicate Pruning to Active Player Sessions

Before removing the node, identify and notify any active sessions currently traversing it:

1. Check Redis for sessions with the target node in their traversal path:

```bash
kubectl exec -n axon-graph deployment/redis -- \
  redis-cli --scan --pattern "session:*" | xargs -I{} \
  redis-cli GET {} | grep -l "<node-id>"
```

2. For each affected session, push a soft redirect event so the gateway can gracefully reroute the player:

```bash
kubectl exec -n axon-graph deployment/redis -- \
  redis-cli PUBLISH axon:events \
  '{"type":"node_prune_warning","node_id":"<node-id>","message":"This path is being updated. You will be redirected."}'
```

3. Allow a 60-second grace period for active sessions to naturally advance past the node before pruning.

### 3.4 Run the Pruning Engine

The `PruningEngine` lives at `Core/evolution/pruning.py`. Run it via the KùzuDB pod or a dedicated ops pod with access to the graph store.

```bash
kubectl exec -it -n axon-graph deployment/kuzudb -- bash
```

Inside the pod:

```bash
cd /app

# Dry run first — prints what would be pruned without making changes
python -m evolution.pruning \
  --node-id "<node-id>" \
  --dry-run \
  --db-path /data/axon.db

# Confirm output is expected, then execute for real
python -m evolution.pruning \
  --node-id "<node-id>" \
  --db-path /data/axon.db \
  --confirm
```

If the `PruningEngine` module path differs, use the absolute path:

```bash
python /app/Core/evolution/pruning.py \
  --node-id "<node-id>" \
  --db-path /data/axon.db \
  --confirm
```

The pruning engine will:
- Remove the target node and all its edges
- Recalculate edge weights on adjacent nodes
- Log the operation to `/data/prune.log`

### 3.5 Post-Prune Validation

#### Check Edge Weights on Adjacent Nodes

Verify that adjacent nodes retained valid edge weights after the prune (weights should be positive and normalized):

```bash
kubectl exec -n axon-graph deployment/kuzudb -- \
  kuzu-cli --db /data/axon.db \
  --query "
    MATCH (n:KnowledgeNode)-[e:CONNECTS]->(m:KnowledgeNode)
    WHERE n.id IN ['<adjacent-node-id-1>', '<adjacent-node-id-2>']
    RETURN n.id, m.id, e.weight
    ORDER BY n.id;
  "
# All weights should be > 0.0 and <= 1.0
```

If any weights are `0` or `null`, the weight recalculation failed. Check the prune log:

```bash
kubectl exec -n axon-graph deployment/kuzudb -- cat /data/prune.log | tail -50
```

#### Verify No Dead-End Paths Remain

A dead-end path is a node with outgoing edges but no reachable exit path. Run the dead-end detector:

```bash
kubectl exec -n axon-graph deployment/kuzudb -- \
  python /app/scripts/check_dead_ends.py --db-path /data/axon.db
# Expected: "No dead-end paths detected"
```

If dead ends are found, they will be listed by node ID. Each must be resolved by either:
- Connecting the isolated node to a valid exit path (preferred), or
- Pruning the dead-end node as well (repeat this procedure)

#### Confirm Node Is No Longer Queryable

```bash
kubectl exec -n axon-graph deployment/kuzudb -- \
  kuzu-cli --db /data/axon.db \
  --query "MATCH (n:KnowledgeNode {id: '<node-id>'}) RETURN n.id;"
# Expected: empty result set (0 rows)
```

### 3.6 Post-Prune Session Handling

Send a final event to clear any residual session state referencing the pruned node:

```bash
kubectl exec -n axon-graph deployment/redis -- \
  redis-cli PUBLISH axon:events \
  '{"type":"node_pruned","node_id":"<node-id>","timestamp":"<ISO-8601-timestamp>"}'
```

The gateway subscribes to this channel and will automatically reset any sessions still referencing the pruned node to their last valid checkpoint.

---

## Procedure 4: Validator Key Rotation

**Use when:**
- A validator hotkey is suspected to be compromised
- Scheduled key rotation policy (recommended every 90 days)
- A validator is being migrated to new hardware
- On-chain key blacklist notice received

> **WARNING:** Incorrect key rotation can knock a validator offline and interrupt weight commits. Always maintain at least 2 of 3 validators active throughout this process (never rotate more than 1 key at a time).

### 4.1 Pre-Rotation Safety Check

Confirm all 3 validators are currently active before starting:

```bash
kubectl get pods -n axon-graph -l app=validator
# All 3 should show Running / READY 1/1
```

Check current weight commit frequency on Grafana (`axon-graph/validators` dashboard) — commits should be regular before you begin. Do not rotate during a period of existing validator instability.

Identify which validator you are rotating (replace `<validator-index>` with `0`, `1`, or `2`):

```bash
kubectl get pods -n axon-graph -l app=validator -o wide
```

### 4.2 Generate a New Hotkey

Generate the new Stellar hotkey. This should be done on a secure, air-gapped machine where possible. Store the new mnemonic in your secrets manager immediately.

```bash
# Using the bittensor CLI
btcli wallet new_hotkey \
  --wallet.name axon-validator-<index> \
  --wallet.hotkey hotkey-new \
  --no-prompt
```

Record:
- New hotkey SS58 address
- New hotkey file path
- Mnemonic (store in secrets manager — do NOT commit to git or paste into chat)

### 4.3 Update the Kubernetes Secret

> **WARNING:** This step replaces the secret used by the validator pod. The pod will be restarted immediately after. Ensure the other 2 validators are healthy before proceeding.

1. Base64-encode the new hotkey file:

```bash
NEW_HOTKEY_B64=$(base64 -i /path/to/new/hotkey.json)
```

2. Patch the validator secret (replace `<validator-n>` with the target validator's secret name):

```bash
kubectl patch secret validator-<n>-hotkey -n axon-graph \
  --type merge \
  -p "{\"data\":{\"hotkey\":\"$NEW_HOTKEY_B64\"}}"
```

3. Restart the target validator pod to load the new secret:

```bash
kubectl rollout restart deployment/validator-<n> -n axon-graph
kubectl rollout status deployment/validator-<n> -n axon-graph --timeout=3m
```

4. Confirm the pod started cleanly with no key errors:

```bash
kubectl logs -n axon-graph -l app=validator-<n> --since=2m | grep -E 'ERROR|hotkey|key'
```

### 4.4 Deregister the Old Key from Subtensor

> **WARNING:** Once deregistered, the old key cannot commit weights. Do this only after the new key is verified working.

First verify the new key has been picked up by the validator pod:

```bash
kubectl exec -n axon-graph deployment/validator-<n> -- \
  python -c "import bittensor; w = bittensor.wallet(name='axon-validator-<n>', hotkey='hotkey-new'); print(w.hotkey.ss58_address)"
# Should print the new SS58 address
```

Then deregister the old key:

```bash
btcli subnet deregister \
  --wallet.name axon-validator-<n> \
  --wallet.hotkey hotkey-old \
  --netuid 42 \
  --subtensor.network finney \
  --no-prompt
```

Record the deregistration extrinsic hash in the incident log.

### 4.5 Register the New Key on Subnet 42

```bash
btcli subnet register \
  --wallet.name axon-validator-<n> \
  --wallet.hotkey hotkey-new \
  --netuid 42 \
  --subtensor.network finney \
  --no-prompt
```

This will burn registration TAO. Confirm the registration cost is acceptable before running. Record the registration extrinsic hash.

### 4.6 Verify Weight Commits Resume

1. Monitor the validator logs for successful weight commits (commits should appear within 1–2 tempo blocks, typically ~12 minutes on mainnet):

```bash
kubectl logs -f -n axon-graph deployment/validator-<n> | grep -E 'weight|commit|set_weights'
```

2. Verify on Grafana (`axon-graph/validators` dashboard): the rotated validator's "Last Weight Commit" timestamp should update within one tempo.

3. Check on-chain that the new UID is active:

```bash
btcli subnet inspect --netuid 42 --subtensor.network finney | grep "<new-ss58-address>"
```

### 4.7 Safety Checklist

Before marking the rotation complete, confirm all of the following:

- [ ] New hotkey SS58 address stored in secrets manager
- [ ] Old hotkey mnemonic securely deleted from all operator machines
- [ ] All 3 validators showing `Running` in `kubectl get pods`
- [ ] New validator is committing weights on-chain (confirmed in logs and Grafana)
- [ ] Deregistration extrinsic hash recorded in incident log
- [ ] Registration extrinsic hash recorded in incident log
- [ ] Old Kubernetes Secret version marked for deletion (after 1 full tempo of stable operation)

---

## Alert Response Guides

### Alert: `ValidatorOffline`

**Condition:** One or more validator pods is not reachable or has been `NotReady` for more than 2 minutes.

**Severity:** Critical — weight commits will fail, miner scores will not update on-chain.

**Response:**

1. Identify the offline validator:

```bash
kubectl get pods -n axon-graph -l app=validator
```

2. Check pod events for crash reason:

```bash
kubectl describe pod <validator-pod-name> -n axon-graph | tail -30
```

3. Check pod logs for the last error:

```bash
kubectl logs <validator-pod-name> -n axon-graph --previous
```

4. Common causes and fixes:

| Cause | Fix |
|---|---|
| OOMKilled | Increase memory limit in Deployment spec; restart pod |
| Key file missing/corrupt | Re-run [Procedure 4.3](#43-update-the-kubernetes-secret) to restore the secret |
| Subtensor RPC timeout | Check `SUBTENSOR_ENDPOINT` in ConfigMap; try alternate endpoint |
| CrashLoopBackOff | Check logs; likely a Python import error from bad image — roll back |

5. If the validator cannot be recovered within 10 minutes, escalate to on-call (see [Emergency Contacts](#emergency-contacts)). With only 2/3 validators active, the subnet is degraded but functional; with 1/3, weight commits may stall entirely.

6. After recovery, verify weight commits resumed (see [Procedure 4.6](#46-verify-weight-commits-resume)).

---

### Alert: `MinerHighTimeoutRate`

**Condition:** A miner deployment is responding to gateway requests with timeout errors at a rate above the configured threshold (default: >10% of requests over a 5-minute window).

**Severity:** Warning — player traversal latency increases; severe cases cause session drops.

**Response:**

1. Identify which miner type is affected:

```bash
kubectl top pods -n axon-graph -l 'app in (domain-miner, narrative-miner)'
# Look for high CPU/memory relative to peers
```

2. Check miner logs for the timeout pattern:

```bash
kubectl logs -n axon-graph deployment/domain-miner --since=10m | grep -E 'timeout|TIMEOUT|TimeoutError'
```

3. Common causes:

| Cause | Fix |
|---|---|
| Corpus not loaded (slow startup) | Wait for readiness probe; if stuck, restart pod |
| IPFS node unreachable | Check `kubectl get pods -n axon-graph -l app=ipfs`; restart if needed |
| Overloaded replicas | Scale up temporarily (see below) |
| KùzuDB write contention | Check `GraphStoreWriteLatencyHigh` alert |

4. Scale up the affected miner temporarily:

```bash
# Increase domain-miner replicas from 8 to 12 during incident
kubectl scale deployment/domain-miner -n axon-graph --replicas=12

# Restore after incident resolution
kubectl scale deployment/domain-miner -n axon-graph --replicas=8
```

5. If timeouts persist after scaling, perform a rolling restart ([Procedure 1.2](#12-graceful-rolling-restart-standard)).

6. If still unresolved after restart, check for a bad corpus CID (stale or missing IPFS pin) and consider a corpus refresh ([Procedure 2](#procedure-2-corpus-refresh)).

---

### Alert: `GraphStoreWriteLatencyHigh`

**Condition:** KùzuDB write latency has exceeded the threshold (default: P99 > 500ms) over a 5-minute window.

**Severity:** Warning — high latency slows graph updates and may cascade to miner timeouts.

**Response:**

1. Check KùzuDB pod resource consumption:

```bash
kubectl top pod -n axon-graph -l app=kuzudb
kubectl describe pod -n axon-graph -l app=kuzudb | grep -A5 'Limits\|Requests'
```

2. Check PVC disk usage (a full disk causes severe write latency):

```bash
kubectl exec -n axon-graph deployment/kuzudb -- df -h /data
# Alert if >80% used
```

If disk is >80% full:
- Check for large orphaned files: `kubectl exec -n axon-graph deployment/kuzudb -- du -sh /data/*`
- Consider a pruning run ([Procedure 3](#procedure-3-emergency-node-pruning)) to remove stale nodes
- Expand the PVC if the graph has grown legitimately

3. Check for concurrent write contention (many miners writing simultaneously):

```bash
kubectl logs -n axon-graph deployment/kuzudb --since=10m | grep -E 'lock|contention|wait|slow'
```

4. Check for an active pruning operation (pruning holds a write lock):

```bash
kubectl exec -n axon-graph deployment/kuzudb -- cat /data/prune.log | tail -5
```

If a pruning run is active, the latency is expected. Monitor until the prune completes.

5. If no pruning is active and disk is healthy, check the KùzuDB process for CPU starvation:

```bash
kubectl exec -n axon-graph deployment/kuzudb -- top -bn1 | head -20
```

If CPU is saturated, consider temporarily reducing miner replica counts to decrease write load:

```bash
kubectl scale deployment/domain-miner -n axon-graph --replicas=4
# Monitor until latency recovers, then restore
kubectl scale deployment/domain-miner -n axon-graph --replicas=8
```

6. If latency remains elevated for >15 minutes and disk/CPU are healthy, escalate to on-call. Do not restart KùzuDB without taking a snapshot first ([Procedure 3.1](#31-pre-prune-snapshot)).

---

## kubectl Cheat Sheet

### Get Overview

```bash
# All resources in namespace
kubectl get all -n axon-graph

# All pods with node placement
kubectl get pods -n axon-graph -o wide

# Pod resource usage
kubectl top pods -n axon-graph

# PVC status
kubectl get pvc -n axon-graph

# Secrets (names only — do not print data)
kubectl get secrets -n axon-graph
```

### Inspect Pods and Events

```bash
# Describe a pod (events, resource limits, probe status)
kubectl describe pod <pod-name> -n axon-graph

# Describe a deployment
kubectl describe deployment <deployment-name> -n axon-graph

# Check pod events only
kubectl get events -n axon-graph --sort-by='.lastTimestamp' | tail -20
```

### Logs

```bash
# Live tail logs for a deployment (all pods)
kubectl logs -f deployment/<name> -n axon-graph

# Last N lines
kubectl logs deployment/<name> -n axon-graph --tail=100

# Logs from previous (crashed) container
kubectl logs <pod-name> -n axon-graph --previous

# Logs since a time window
kubectl logs deployment/<name> -n axon-graph --since=30m

# Logs from a specific container in a multi-container pod
kubectl logs <pod-name> -n axon-graph -c <container-name>
```

### Execute Into Pods

```bash
# Interactive shell in a running pod
kubectl exec -it <pod-name> -n axon-graph -- bash

# Execute a single command
kubectl exec -n axon-graph deployment/<name> -- <command>

# Execute as a specific user
kubectl exec -it <pod-name> -n axon-graph -- su -c "bash" <username>
```

### Scale and Restart

```bash
# Scale a deployment
kubectl scale deployment/<name> -n axon-graph --replicas=<n>

# Rolling restart (zero-downtime)
kubectl rollout restart deployment/<name> -n axon-graph

# Watch rollout progress
kubectl rollout status deployment/<name> -n axon-graph

# View rollout history
kubectl rollout history deployment/<name> -n axon-graph

# Undo last rollout
kubectl rollout undo deployment/<name> -n axon-graph

# Undo to a specific revision
kubectl rollout undo deployment/<name> -n axon-graph --to-revision=<n>
```

### Edit and Patch

```bash
# Open deployment in editor
kubectl edit deployment/<name> -n axon-graph

# Patch a configmap value
kubectl patch configmap <name> -n axon-graph \
  --type merge \
  -p '{"data":{"KEY":"value"}}'

# Patch a secret value (base64-encoded)
kubectl patch secret <name> -n axon-graph \
  --type merge \
  -p "{\"data\":{\"key\":\"$(echo -n 'value' | base64)\"}}"
```

### Specific Component Shortcuts

```bash
# Quick health check of all miners
kubectl get pods -n axon-graph -l 'app in (domain-miner, narrative-miner)' -o wide

# Quick health check of all validators
kubectl get pods -n axon-graph -l app=validator -o wide

# Tail gateway logs
kubectl logs -f deployment/gateway -n axon-graph

# Redis CLI
kubectl exec -it -n axon-graph deployment/redis -- redis-cli

# KùzuDB shell
kubectl exec -it -n axon-graph deployment/kuzudb -- kuzu-cli --db /data/axon.db

# IPFS CLI
kubectl exec -it -n axon-graph deployment/ipfs -- ipfs
```

---

## Emergency Contacts

> Replace the placeholders below with actual contact information before deploying this runbook.

| Role | Name | Contact | Escalation Condition |
|---|---|---|---|
| On-Call Operator | TBD | TBD | Any Critical alert not resolved within 10 minutes |
| Subnet Lead | TBD | TBD | Validator count drops to 1/3; corpus data integrity issue |
| Infrastructure Lead | TBD | TBD | KùzuDB or IPFS PVC at risk; cluster-level incident |
| Bittensor Subnet 42 Discord | `#axon-graph-ops` | TBD | On-chain registration failures; subtensor RPC issues |
| PagerDuty / Incident Manager | TBD | TBD | Full outage; all validators offline |

---

*Runbook version 1.0 — Axon-Graph Phase 5*
