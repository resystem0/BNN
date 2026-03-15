import { writable, derived } from 'svelte/store';

// ============================================================
// Session State Stores
// ============================================================

export const sessionId = writable(null);
export const currentNode = writable('quantum_mechanics');
export const pathHistory = writable([]); // { nodeId, passage, score, minerId, timestamp }
export const isStreaming = writable(false);
export const streamBuffer = writable('');
export const choices = writable([]); // { nodeId, label, description }
export const wsConnected = writable(false);
export const blockHeight = writable(1847304);
export const hopsCount = writable(0);
export const tokensSpent = writable(0);
export const sessionEarned = writable(0);
export const validatorCount = writable(12);
export const activeMiners = writable(47);

// Soul overlay visibility
export const showSoulOverlay = writable(false);

// ============================================================
// Derived State
// ============================================================

export const sessionStats = derived(
  [currentNode, hopsCount, tokensSpent, sessionEarned],
  ([$currentNode, $hopsCount, $tokensSpent, $sessionEarned]) => ({
    currentNode: $currentNode,
    hops: $hopsCount,
    tokensSpent: $tokensSpent,
    earned: $sessionEarned,
  })
);

// ============================================================
// Actions
// ============================================================

export function navigate(nodeId) {
  currentNode.update(() => nodeId);
  hopsCount.update((n) => n + 1);
  isStreaming.set(true);
  streamBuffer.set('');

  // Stub: simulate streaming passage text
  const passages = [
    'The lattice of causality folds upon itself at the threshold of observation. Each measurement collapses the wave-form into a singular thread of realized history.',
    'In the space between knowing and not-knowing, the observer becomes entangled with the observed. The boundary dissolves like mist at dawn.',
    'Recursion is not mere repetition — it is the universe examining itself through layers of abstraction, each reflection carrying the seed of the next.',
    'Information propagates through substrate agnostic to matter, binding disparate systems into coherent narrative structures that outlast their physical vessels.',
  ];

  const text = passages[Math.floor(Math.random() * passages.length)];
  const words = text.split(' ');
  let i = 0;

  const interval = setInterval(() => {
    if (i < words.length) {
      streamBuffer.update((buf) => (buf ? buf + ' ' + words[i] : words[i]));
      i++;
    } else {
      clearInterval(interval);
      isStreaming.set(false);

      // Add to path history
      pathHistory.update((history) => [
        ...history,
        {
          nodeId,
          passage: text,
          score: 0.72 + Math.random() * 0.25,
          minerId: `uid-${Math.floor(Math.random() * 200)}`,
          timestamp: Date.now(),
        },
      ]);

      // Set mock choices
      choices.set([
        { nodeId: 'recursion', label: 'Recursion', description: 'Self-referential computational structures' },
        { nodeId: 'consciousness', label: 'Consciousness', description: 'Emergent subjective experience' },
        { nodeId: 'information_theory', label: 'Information Theory', description: 'Entropy, encoding, and signal' },
      ]);
    }
  }, 80);
}

export function submitEntry(token) {
  if (!token?.trim()) return;
  showSoulOverlay.set(false);
  sessionId.set(`axon-${Date.now().toString(36)}`);

  // Stub: initialize session with token
  streamBuffer.set('');
  choices.set([
    { nodeId: 'relativity', label: 'Relativity', description: 'Spacetime curvature and inertial frames' },
    { nodeId: 'thermodynamics', label: 'Thermodynamics', description: 'Entropy and energy transformation' },
    { nodeId: 'information_theory', label: 'Information Theory', description: 'Entropy, encoding, and signal' },
  ]);
}

// ============================================================
// WebSocket Connection
// ============================================================

let ws = null;

export function connectWS(sid) {
  if (ws) {
    ws.close();
    ws = null;
  }

  const url = `ws://localhost:8000/ws/${sid}`;

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
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);

        switch (msg.type) {
          case 'streaming_token':
            isStreaming.set(true);
            streamBuffer.update((buf) => buf + (msg.token || ''));
            break;

          case 'hop_complete':
            isStreaming.set(false);
            if (msg.node_id) currentNode.set(msg.node_id);
            if (msg.score != null) {
              pathHistory.update((h) => {
                const last = h[h.length - 1];
                if (last) return [...h.slice(0, -1), { ...last, score: msg.score }];
                return h;
              });
            }
            break;

          case 'choices':
            choices.set(msg.choices || []);
            break;

          case 'block_update':
            if (msg.block_height != null) blockHeight.set(msg.block_height);
            if (msg.validator_count != null) validatorCount.set(msg.validator_count);
            if (msg.active_miners != null) activeMiners.set(msg.active_miners);
            break;

          default:
            break;
        }
      } catch {
        // ignore malformed messages
      }
    };
  } catch {
    wsConnected.set(false);
  }
}

export function disconnectWS() {
  if (ws) {
    ws.close();
    ws = null;
  }
}
