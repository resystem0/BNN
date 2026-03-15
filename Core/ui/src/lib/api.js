const BASE = import.meta.env.VITE_GATEWAY_URL || 'http://localhost:8000';

/**
 * Enter the axon-graph vault — creates a new traversal session.
 * @param {string} query - The soul token / query string
 * @param {string} [persona='neutral']
 * @param {number} [maxHops=5]
 * @param {string|null} [entryNodeId=null]
 * @returns {Promise<{ session_id: string, entry_node_id: string, entry_narrative: string, path: string[], available_next_nodes: string[] }>}
 */
export async function enterVault(query, persona = 'neutral', maxHops = 5, entryNodeId = null) {
  const body = { query, persona, max_hops: maxHops };
  if (entryNodeId) body.entry_node_id = entryNodeId;

  const r = await fetch(`${BASE}/enter`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!r.ok) {
    const text = await r.text().catch(() => r.statusText);
    throw new Error(`enterVault failed (${r.status}): ${text}`);
  }

  return r.json();
}

/**
 * Perform a hop to a target node via REST (fallback when WS is unavailable).
 * @param {string} sessionId
 * @param {string} toNodeId
 * @returns {Promise<{ session_id: string, from_node_id: string, to_node_id: string, hop_text: string, path: string[], available_next_nodes: string[], is_terminal: boolean }>}
 */
export async function hop(sessionId, toNodeId) {
  const r = await fetch(`${BASE}/hop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, to_node_id: toNodeId }),
  });

  if (!r.ok) {
    const text = await r.text().catch(() => r.statusText);
    throw new Error(`hop failed (${r.status}): ${text}`);
  }

  return r.json();
}

/**
 * Get current session state.
 * @param {string} sessionId
 * @returns {Promise<{ session_id: string, path: string[], narrative_so_far: string, current_node_id: string, is_terminal: boolean, hop_count: number }>}
 */
export async function getSession(sessionId) {
  const r = await fetch(`${BASE}/session/${encodeURIComponent(sessionId)}`);

  if (!r.ok) {
    const text = await r.text().catch(() => r.statusText);
    throw new Error(`getSession failed (${r.status}): ${text}`);
  }

  return r.json();
}

/**
 * Health check.
 * @returns {Promise<{ status: string, active_sessions: number, graph_stats: object }>}
 */
export async function healthz() {
  const r = await fetch(`${BASE}/healthz`);

  if (!r.ok) {
    const text = await r.text().catch(() => r.statusText);
    throw new Error(`healthz failed (${r.status}): ${text}`);
  }

  return r.json();
}
