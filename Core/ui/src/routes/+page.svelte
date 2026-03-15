<script>
  import { onMount } from 'svelte';
  import GraphCanvas from '$lib/components/game/GraphCanvas.svelte';
  import StoryPane from '$lib/components/game/StoryPane.svelte';
  import ChoiceCards from '$lib/components/game/ChoiceCards.svelte';
  import PathTrail from '$lib/components/game/PathTrail.svelte';
  import SoulOverlay from '$lib/components/game/SoulOverlay.svelte';
  import {
    currentNode,
    blockHeight,
    hopsCount,
    tokensSpent,
    sessionEarned,
    validatorCount,
    activeMiners,
    sessionId,
  } from '$lib/stores/session.js';

  onMount(() => {
    // Simulate block height incrementing
    const interval = setInterval(() => {
      blockHeight.update((h) => h + 1);
    }, 12000);
    return () => clearInterval(interval);
  });
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
        <span class="stat-v">{$hopsCount}</span>
      </div>
      <div class="stat-row">
        <span class="stat-l">TOKENS</span>
        <span class="stat-v">{$tokensSpent}</span>
      </div>
      <div class="stat-row">
        <span class="stat-l">EARNED τ</span>
        <span class="stat-v teal">{$sessionEarned.toFixed(4)}</span>
      </div>
    </div>

    <!-- Network status -->
    <div class="stats-block">
      <div class="block-heading">NETWORK</div>
      <div class="stat-row">
        <span class="stat-l">BLOCK</span>
        <span class="stat-v">{$blockHeight?.toLocaleString()}</span>
      </div>
      <div class="stat-row">
        <span class="stat-l">VALIDATORS</span>
        <span class="stat-v">{$validatorCount}</span>
      </div>
      <div class="stat-row">
        <span class="stat-l">MINERS</span>
        <span class="stat-v">{$activeMiners}</span>
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

<!-- Soul token overlay (portal rendered) -->
<SoulOverlay />

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

  .stat-v.gold { color: var(--gold); }
  .stat-v.teal { color: var(--accent2); }

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
</style>
