<script>
  import { pathHistory, currentNode } from '$lib/stores/session.js';
</script>

<div class="trail">
  <div class="trail-label">PATH</div>
  <div class="trail-chips">
    {#if $pathHistory.length === 0}
      <span class="chip origin">{$currentNode.replace(/_/g, ' ')}</span>
    {:else}
      {#each $pathHistory as hop, i}
        <span class="chip {i === $pathHistory.length - 1 ? 'current' : 'visited'}">
          {hop.nodeId.replace(/_/g, ' ')}
        </span>
        {#if i < $pathHistory.length - 1}
          <span class="arrow">→</span>
        {/if}
      {/each}
    {/if}
  </div>
</div>

<style>
  .trail {
    padding: 8px 12px;
    border-top: 1px solid var(--border);
  }

  .trail-label {
    font-family: var(--mono-dark);
    font-size: 9px;
    font-weight: 500;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-dim);
    margin-bottom: 6px;
  }

  .trail-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    align-items: center;
  }

  .chip {
    font-family: var(--mono-dark);
    font-size: 9px;
    font-weight: 400;
    letter-spacing: 0.06em;
    padding: 2px 6px;
    border-radius: 2px;
    text-transform: uppercase;
    white-space: nowrap;
  }

  .chip.origin,
  .chip.current {
    background: rgba(232, 200, 122, 0.12);
    color: var(--gold);
    border: 1px solid rgba(232, 200, 122, 0.3);
  }

  .chip.visited {
    background: rgba(79, 123, 255, 0.08);
    color: var(--text-dim);
    border: 1px solid var(--border);
  }

  .arrow {
    font-size: 10px;
    color: var(--text-dim);
    opacity: 0.5;
    line-height: 1;
  }
</style>
