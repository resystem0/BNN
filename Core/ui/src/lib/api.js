const BASE = import.meta.env.VITE_GATEWAY_URL || 'http://localhost:8000';

/**
 * Create a new traversal session with a soul token.
 * @param {string} soulToken
 * @returns {Promise<{ session_id: string, start_node: string }>}
 */
export async function createSession(soulToken) {
  const r = await fetch(`${BASE}/session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ soul_token: soulToken }),
  });
  return r.json();
}

/**
 * Get current session state.
 * @param {string} sessionId
 * @returns {Promise<object>}
 */
export async function getSession(sessionId) {
  const r = await fetch(`${BASE}/session/${sessionId}`);
  return r.json();
}

/**
 * Perform a hop to a target node.
 * @param {string} sessionId
 * @param {string} targetNodeId
 * @returns {Promise<{ passage: string, score: number, miner_id: string, choices: Array }>}
 */
export async function hop(sessionId, targetNodeId) {
  const r = await fetch(`${BASE}/session/${sessionId}/hop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_node: targetNodeId }),
  });
  return r.json();
}

/**
 * Get intelligence data for a session (scoring, competing miners, etc.)
 * @param {string} sessionId
 * @returns {Promise<object>}
 */
export async function getIntelligence(sessionId) {
  const r = await fetch(`${BASE}/session/${sessionId}/intelligence`);
  return r.json();
}

/**
 * Get treasury/ledger data for a session.
 * @param {string} sessionId
 * @returns {Promise<object>}
 */
export async function getTreasury(sessionId) {
  const r = await fetch(`${BASE}/session/${sessionId}/treasury`);
  return r.json();
}
