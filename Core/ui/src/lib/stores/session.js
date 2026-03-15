import { writable, derived } from 'svelte/store';
import { enterVault as apiEnterVault, hop as apiHop, getSession as apiGetSession } from '$lib/api.js';

// ============================================================
// Config
// ============================================================

const BASE = import.meta.env.VITE_GATEWAY_URL || 'http://localhost:8000';
const WS_BASE = BASE.replace(/^http/, 'ws');

// ============================================================
// Session State Stores
// ============================================================

export const sessionId = writable(null);
export const currentNode = writable('quantum_mechanics');

/** Array of { nodeId, passage, timestamp } */
export const pathHistory = writable([]);

/** Array of { nodeId } mapped from available_next_nodes */
export const choices = writable([]);

export const isStreaming = writable(false);
export const streamBuffer = writable('');
export const wsConnected = writable(false);
export const isTerminal = writable(false);
export const lastError = writable(null);

// Soul overlay visibility
export const showSoulOverlay = writable(true);

// ============================================================
// Derived State
// ============================================================

/** Number of hops taken — always pathHistory.length - 1 (entry doesn't count as a hop) */
export const hopCount = derived(pathHistory, ($pathHistory) =>
  Math.max(0, $pathHistory.length - 1)
);

// ============================================================
// Internal WebSocket reference
// ============================================================

let ws = null;

// ============================================================
// Helper: map available_next_nodes string[] → choices array
// ============================================================

function mapChoices(nodes) {
  if (!Array.isArray(nodes)) return [];
  return nodes.map((nodeId) => ({ nodeId }));
}

// ============================================================
// Actions
// ============================================================

/**
 * Open a WebSocket connection for the given session.
 * @param {string} sid
 */
export function connectWS(sid) {
  if (ws) {
    ws.close();
    ws = null;
  }

  const url = `${WS_BASE}/session/${encodeURIComponent(sid)}/live`;

  try {
    ws = new WebSocket(url);

    ws.onopen = () => {
      wsConnected.set(true);
    };

    ws.onclose = () => {
      wsConnected.set(false);
      ws = null;
    };

    ws.onerror = () => {
      wsConnected.set(false);
      lastError.set('WebSocket connection error');
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);

        if (msg.error) {
          lastError.set(msg.error);
          isStreaming.set(false);
          return;
        }

        if (msg.event === 'hop') {
          pathHistory.update((h) => [
            ...h,
            {
              nodeId: msg.to_node_id,
              passage: msg.hop_text ?? '',
              timestamp: Date.now(),
            },
          ]);
          currentNode.set(msg.to_node_id);
          choices.set(mapChoices(msg.available_next_nodes));
          streamBuffer.set(msg.hop_text ?? '');
          isStreaming.set(false);
          return;
        }

        if (msg.event === 'terminal') {
          isTerminal.set(true);
          isStreaming.set(false);
          if (ws) {
            ws.close();
            ws = null;
          }
          return;
        }
      } catch {
        // ignore malformed messages
      }
    };
  } catch {
    wsConnected.set(false);
    lastError.set('Failed to open WebSocket');
  }
}

/**
 * Enter the vault — calls POST /enter, seeds session state, then connects WS.
 * The soul token is used as the query string.
 * @param {string} query
 * @param {string} [persona='neutral']
 */
export async function enterVault(query, persona = 'neutral') {
  if (!query?.trim()) return;

  lastError.set(null);
  isStreaming.set(true);
  streamBuffer.set('');

  try {
    const data = await apiEnterVault(query.trim(), persona);

    sessionId.set(data.session_id);
    currentNode.set(data.entry_node_id);
    isTerminal.set(false);

    // Seed path history with the entry node
    pathHistory.set([
      {
        nodeId: data.entry_node_id,
        passage: data.entry_narrative ?? '',
        timestamp: Date.now(),
      },
    ]);

    streamBuffer.set(data.entry_narrative ?? '');
    choices.set(mapChoices(data.available_next_nodes));
    isStreaming.set(false);

    showSoulOverlay.set(false);

    connectWS(data.session_id);
  } catch (err) {
    isStreaming.set(false);
    lastError.set(err?.message ?? 'Failed to enter vault');
  }
}

/**
 * Navigate to a node.
 * Sends over WS if connected; falls back to REST POST /hop.
 * @param {string} toNodeId
 */
export async function navigate(toNodeId) {
  if (!toNodeId) return;

  isStreaming.set(true);
  streamBuffer.set('');
  lastError.set(null);

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ to_node_id: toNodeId }));
    return;
  }

  // WS fallback — use REST
  let sid;
  sessionId.subscribe((v) => { sid = v; })();

  if (!sid) {
    isStreaming.set(false);
    lastError.set('No active session');
    return;
  }

  try {
    const data = await apiHop(sid, toNodeId);

    pathHistory.update((h) => [
      ...h,
      {
        nodeId: data.to_node_id,
        passage: data.hop_text ?? '',
        timestamp: Date.now(),
      },
    ]);
    currentNode.set(data.to_node_id);
    choices.set(mapChoices(data.available_next_nodes));
    streamBuffer.set(data.hop_text ?? '');
    isStreaming.set(false);

    if (data.is_terminal) {
      isTerminal.set(true);
    }
  } catch (err) {
    isStreaming.set(false);
    lastError.set(err?.message ?? 'Hop failed');
  }
}

/**
 * Re-fetch session state from GET /session/{sid} then reconnect WS.
 * @param {string} sid
 */
export async function reconnect(sid) {
  if (!sid) return;

  lastError.set(null);

  try {
    const data = await apiGetSession(sid);

    sessionId.set(data.session_id);
    currentNode.set(data.current_node_id);
    isTerminal.set(data.is_terminal ?? false);

    // Rebuild path history from path array (no passage text available on reconnect)
    const rebuilt = (data.path ?? []).map((nodeId) => ({
      nodeId,
      passage: '',
      timestamp: Date.now(),
    }));
    pathHistory.set(rebuilt);

    // Show last narrative as the stream buffer
    streamBuffer.set(data.narrative_so_far ?? '');
    isStreaming.set(false);

    if (!data.is_terminal) {
      connectWS(sid);
    }
  } catch (err) {
    lastError.set(err?.message ?? 'Reconnect failed');
  }
}

/**
 * Close the WebSocket and reset all session state.
 */
export function disconnect() {
  if (ws) {
    ws.close();
    ws = null;
  }

  sessionId.set(null);
  currentNode.set('quantum_mechanics');
  pathHistory.set([]);
  choices.set([]);
  isStreaming.set(false);
  streamBuffer.set('');
  wsConnected.set(false);
  isTerminal.set(false);
  lastError.set(null);
  showSoulOverlay.set(true);
}
