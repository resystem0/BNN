<script>
  import { sessionId, wsConnected, streamBuffer, isStreaming, showSoulOverlay, hopCount } from '$lib/stores/session.js';
</script>

<div class="story-pane">
  <!-- Header bar -->
  <div class="header-bar">
    <span class="session-id">{$sessionId ?? 'NO SESSION'}</span>
    <span class="epoch-chip">HOP {$hopCount}</span>
    <span class="status-dot" class:connected={$wsConnected} title={$wsConnected ? 'Connected' : 'Disconnected'}></span>
  </div>

  <!-- Passage section -->
  <div class="passage-section">
    <div class="section-heading-dark">PASSAGE</div>

    <div class="passage-text">
      {#if $streamBuffer}
        <p class="passage-body">
          {$streamBuffer}{#if $isStreaming}<span class="cursor">|</span>{/if}
        </p>
      {:else}
        <p class="passage-empty">
          {#if $isStreaming}
            <span class="cursor">|</span>
          {:else}
            Awaiting traversal — enter a query or select a node to begin.
          {/if}
        </p>
      {/if}
    </div>
  </div>

  <!-- Soul Entry prompt -->
  <div class="entry-section">
    <div class="section-heading-dark">SOUL ENTRY</div>
    <button
      class="enter-btn"
      on:click={() => showSoulOverlay.set(true)}
    >
      ENTER VAULT
    </button>
  </div>
</div>

<style>
  .story-pane {
    display: flex;
    flex-direction: column;
    height: 100%;
    padding: 0;
    overflow: hidden;
  }

  /* Header */
  .header-bar {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
  }

  .session-id {
    font-family: var(--mono-dark);
    font-size: 10px;
    font-weight: 400;
    letter-spacing: 0.08em;
    color: var(--text-dim);
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .epoch-chip {
    font-family: var(--mono-dark);
    font-size: 9px;
    font-weight: 500;
    letter-spacing: 0.1em;
    padding: 2px 8px;
    background: rgba(79, 123, 255, 0.1);
    border: 1px solid var(--border-strong);
    border-radius: 2px;
    color: var(--accent);
    white-space: nowrap;
  }

  .status-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: rgba(220, 215, 205, 0.2);
    transition: background 0.3s ease;
    flex-shrink: 0;
  }

  .status-dot.connected {
    background: var(--accent2);
    box-shadow: 0 0 6px rgba(0, 229, 176, 0.5);
  }

  /* Passage */
  .passage-section {
    flex: 1;
    overflow-y: auto;
    padding: 20px 20px 16px;
  }

  .passage-text {
    min-height: 80px;
  }

  .passage-body {
    font-family: var(--body-dark);
    font-size: 17px;
    font-style: italic;
    font-weight: 400;
    line-height: 1.75;
    color: var(--text);
    letter-spacing: 0.01em;
  }

  .passage-empty {
    font-family: var(--body-dark);
    font-size: 15px;
    font-style: italic;
    color: var(--text-dim);
    line-height: 1.6;
  }

  /* Blinking cursor */
  .cursor {
    display: inline-block;
    color: var(--accent);
    animation: blink 1s step-end infinite;
    font-style: normal;
    margin-left: 1px;
  }

  @keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0; }
  }

  /* Entry section */
  .entry-section {
    padding: 16px 20px;
    border-top: 1px solid var(--border);
  }

  .enter-btn {
    font-family: var(--mono-dark);
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.14em;
    padding: 9px 20px;
    background: transparent;
    border: 1px solid var(--gold-dim);
    border-radius: 2px;
    color: var(--gold);
    cursor: pointer;
    transition: background 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
    width: 100%;
    text-align: center;
  }

  .enter-btn:hover {
    background: rgba(232, 200, 122, 0.07);
    border-color: var(--gold);
    box-shadow: 0 0 12px rgba(232, 200, 122, 0.12);
  }

  .enter-btn:active {
    background: rgba(232, 200, 122, 0.12);
  }

  .section-heading-dark {
    display: flex;
    align-items: center;
    gap: 8px;
    font-family: var(--mono-dark);
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-dim);
    margin-bottom: 12px;
  }

  .section-heading-dark::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border);
  }
</style>
