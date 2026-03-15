<script>
  import { choices } from '$lib/stores/session.js';
  import { navigate } from '$lib/stores/session.js';
</script>

{#if $choices.length > 0}
  <div class="choices">
    <div class="section-heading-dark">NAVIGATE</div>
    <div class="cards">
      {#each $choices as choice}
        <button
          class="card"
          on:click={() => navigate(choice.nodeId)}
        >
          <span class="card-title">{choice.label}</span>
          <span class="card-desc">{choice.description}</span>
          <span class="card-arrow">→</span>
        </button>
      {/each}
    </div>
  </div>
{/if}

<style>
  .choices {
    padding: 16px 20px;
    border-top: 1px solid var(--border);
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
    margin-bottom: 10px;
  }

  .section-heading-dark::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border);
  }

  .cards {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .card {
    display: grid;
    grid-template-columns: 1fr auto;
    grid-template-rows: auto auto;
    align-items: center;
    gap: 2px 8px;
    padding: 10px 12px;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 2px;
    cursor: pointer;
    text-align: left;
    transition: border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease;
  }

  .card:hover {
    border-color: var(--accent2);
    background: rgba(0, 229, 176, 0.04);
    box-shadow: inset 0 0 0 1px rgba(0, 229, 176, 0.08);
  }

  .card:active {
    background: rgba(0, 229, 176, 0.08);
  }

  .card-title {
    font-family: var(--serif-dark);
    font-size: 12px;
    font-weight: 400;
    letter-spacing: 0.06em;
    color: var(--text);
    grid-column: 1;
    grid-row: 1;
  }

  .card-desc {
    font-family: var(--body-dark);
    font-size: 11px;
    font-style: italic;
    color: var(--text-dim);
    grid-column: 1;
    grid-row: 2;
    line-height: 1.4;
  }

  .card-arrow {
    font-size: 14px;
    color: var(--text-dim);
    grid-column: 2;
    grid-row: 1 / 3;
    transition: color 0.2s ease, transform 0.2s ease;
  }

  .card:hover .card-arrow {
    color: var(--accent2);
    transform: translateX(2px);
  }
</style>
