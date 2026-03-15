<script>
  import GraphCanvas from '$lib/components/game/GraphCanvas.svelte';
  import StoryPane from '$lib/components/game/StoryPane.svelte';
  import ChoiceCards from '$lib/components/game/ChoiceCards.svelte';
  import PathTrail from '$lib/components/game/PathTrail.svelte';
  import SoulOverlay from '$lib/components/game/SoulOverlay.svelte';
  import {
    currentNode,
    sessionId,
    hopCount,
    wsConnected,
    isTerminal,
    lastError,
  } from '$lib/stores/session.js';

  function dismissError() {
    lastError.set(null);
  }
</script>

<svelte:head>
  <title>Axon Graph — Traversal</title>
</svelte:head>

<div class="game-layout">
  <!-- Left: Graph + Path Trail -->
  <aside class="panel-left">
    <div class="panel-header">
      <span class="panel-title">KNOWLEDGE GRAPH</span>
    </div>
    <div class="graph-area">
      <GraphCanvas />
    </div>
    <PathTrail />
  </aside>

  <!-- Center: Story Pane + Choice Cards -->
  <main class="panel-center">
    <div class="story-area">
      <StoryPane />
    </div>
    <ChoiceCards />
  </main>

  <!-- Right: Stats sidebar -->
  <aside class="panel-right">
    <!-- Session stats -->
    <div class="stats-block">
      <div class="block-heading">SESSION</div>
      <div class="stat-row">
        <span class="stat-l">NODE</span>
        <span class="stat-v gold">{$currentNode?.replace(/_/g, ' ') ?? '—'}</span>
      </div>
      <div class="stat-row">
        <span class="stat-l">HOPS</span>
        <span class="stat-v">{$hopCount}</span>
      </div>
      <div class="stat-row">
        <span class="stat-l">STATUS</span>
        <span class="stat-v {$isTerminal ? 'amber' : 'teal'}">
          {$isTerminal ? 'TERMINAL' : ($sessionId ? 'ACTIVE' : 'IDLE')}
        </span>
      </div>
    </div>

    <!-- Network status -->
    <div class="stats-block">
      <div class="block-heading">
        NETWORK
        <span class="ws-dot" class:connected={$wsConnected} title={$wsConnected ? 'Connected' : 'Disconnected'}></span>
      </div>
      <div class="stat-row">
        <span class="stat-l">GATEWAY</span>
        <span class="stat-v {$wsConnected ? 'teal' : 'dim'}">{$wsConnected ? 'LIVE' : 'OFFLINE'}</span>
      </div>
      <div class="stat-row">
        <span class="stat-l">SESSION</span>
        <span class="stat-v mono-sm">{$sessionId ? $sessionId.slice(0, 12) + '…' : '—'}</span>
      </div>
    </div>

    <!-- Navigation links -->
    <div class="nav-links">
      <div class="block-heading">REPORTS</div>
      <a href="/treasury" class="nav-link">
        <span class="nav-icon">◈</span>
        <span>Treasury</span>
      </a>
      <a href="/intelligence" class="nav-link">
        <span class="nav-icon">◉</span>
        <span>Intelligence</span>
      </a>
      <a href="/dossier" class="nav-link">
        <span class="nav-icon">◎</span>
        <span>Dossier</span>
      </a>
    </div>
  </aside>
</div>

<!-- Soul token overlay -->
<SoulOverlay />

<!-- Error toast -->
{#if $lastError}
  <div class="error-toast" role="alert">
    <span class="error-msg">{$lastError}</span>
    <button class="error-dismiss" on:click={dismissError} aria-label="Dismiss error">✕</button>
  </div>
{/if}

<style>
  .game-layout {
    display: grid;
    grid-template-columns: 320px 1fr 280px;
    height: 100vh;
    background: var(--void);
    color: var(--text);
    overflow: hidden;
  }

  /* Left Panel */
  .panel-left {
    display: flex;
    flex-direction: column;
    border-right: 1px solid var(--border);
    background: var(--surface);
    overflow: hidden;
  }

  .panel-header {
    padding: 12px 14px;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }

  .panel-title {
    font-family: var(--mono-dark);
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.14em;
    color: var(--text-dim);
    text-transform: uppercase;
  }

  .graph-area {
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }

  /* Center Panel */
  .panel-center {
    display: flex;
    flex-direction: column;
    background: var(--surface);
    border-right: 1px solid var(--border);
    overflow: hidden;
  }

  .story-area {
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }

  /* Right Panel */
  .panel-right {
    background: var(--surface);
    display: flex;
    flex-direction: column;
    gap: 0;
    overflow-y: auto;
  }

  .stats-block {
    padding: 16px 16px 12px;
    border-bottom: 1px solid var(--border);
  }

  .block-heading {
    font-family: var(--mono-dark);
    font-size: 9px;
    font-weight: 500;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--text-dim);
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .block-heading::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border);
  }

  .ws-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: rgba(220, 215, 205, 0.2);
    flex-shrink: 0;
    transition: background 0.3s ease;
    /* placed before the ::after rule so it doesn't sit on the line */
    order: -1;
    margin-left: auto;
  }

  .ws-dot.connected {
    background: var(--accent2);
    box-shadow: 0 0 5px rgba(0, 229, 176, 0.5);
  }

  .stat-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 4px 0;
  }

  .stat-l {
    font-family: var(--mono-dark);
    font-size: 9px;
    font-weight: 400;
    letter-spacing: 0.08em;
    color: var(--text-dim);
    text-transform: uppercase;
  }

  .stat-v {
    font-family: var(--mono-dark);
    font-size: 12px;
    font-weight: 500;
    color: var(--text);
    text-transform: capitalize;
    text-align: right;
    max-width: 160px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .stat-v.gold  { color: var(--gold); }
  .stat-v.teal  { color: var(--accent2); }
  .stat-v.amber { color: var(--gold-dim, #b8963a); }
  .stat-v.dim   { color: var(--text-dim); }
  .stat-v.mono-sm { font-size: 10px; letter-spacing: 0.04em; }

  /* Nav links */
  .nav-links {
    padding: 16px 16px 12px;
  }

  .nav-link {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 10px;
    font-family: var(--mono-dark);
    font-size: 11px;
    font-weight: 400;
    letter-spacing: 0.06em;
    color: var(--text-dim);
    border-radius: 2px;
    transition: color 0.2s ease, background 0.2s ease;
    text-decoration: none;
    margin-bottom: 2px;
  }

  .nav-link:hover {
    color: var(--text);
    background: var(--surface2);
  }

  .nav-icon {
    font-size: 12px;
    color: var(--accent);
    flex-shrink: 0;
  }

  /* Error toast */
  .error-toast {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 16px;
    background: var(--surface);
    border: 1px solid rgba(220, 80, 80, 0.5);
    border-radius: 2px;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.5);
    z-index: 2000;
    animation: toast-in 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    max-width: calc(100vw - 48px);
  }

  @keyframes toast-in {
    from { opacity: 0; transform: translateX(-50%) translateY(8px); }
    to   { opacity: 1; transform: translateX(-50%) translateY(0); }
  }

  .error-msg {
    font-family: var(--mono-dark);
    font-size: 12px;
    font-weight: 400;
    color: rgba(220, 120, 120, 1);
    letter-spacing: 0.03em;
  }

  .error-dismiss {
    font-size: 12px;
    color: var(--text-dim);
    background: none;
    border: none;
    cursor: pointer;
    padding: 2px 4px;
    line-height: 1;
    flex-shrink: 0;
    transition: color 0.15s ease;
  }

  .error-dismiss:hover {
    color: var(--text);
  }
</style>
