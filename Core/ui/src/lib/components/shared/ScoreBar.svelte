<script>
  export let score = 0;        // 0–1
  export let label = '';
  export let weight = null;    // optional weight percentage string e.g. "40%"
  export let note = '';        // optional italic note text
  export let showValue = true;

  // Color threshold logic
  $: colorClass = score >= 0.8 ? 'teal' : score >= 0.65 ? 'amber' : 'red';
  $: fillPct = Math.round(score * 100);
</script>

<div class="score-bar-wrap">
  <div class="score-bar-header">
    <span class="score-bar-label">
      {label}
      {#if weight}<span class="weight">{weight}</span>{/if}
    </span>
    {#if showValue}
      <span class="score-bar-value {colorClass}">{score.toFixed(2)}</span>
    {/if}
  </div>

  <div class="track">
    <div class="fill {colorClass}" style="width: {fillPct}%"></div>
  </div>

  {#if note}
    <p class="note">{note}</p>
  {/if}
</div>

<style>
  .score-bar-wrap {
    margin-bottom: 10px;
  }

  .score-bar-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 4px;
  }

  .score-bar-label {
    font-family: var(--mono);
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--ink);
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .weight {
    font-size: 9px;
    color: var(--muted);
    font-weight: 400;
  }

  .score-bar-value {
    font-family: var(--mono);
    font-size: 12px;
    font-weight: 600;
  }

  .track {
    height: 4px;
    background: var(--rule-strong);
    border-radius: 2px;
    overflow: hidden;
  }

  .fill {
    height: 100%;
    border-radius: 2px;
    transition: width 0.4s cubic-bezier(0.16, 1, 0.3, 1);
  }

  .fill.teal { background: var(--teal); }
  .fill.amber { background: var(--amber); }
  .fill.red { background: var(--red); }

  .score-bar-value.teal { color: var(--teal); }
  .score-bar-value.amber { color: var(--amber); }
  .score-bar-value.red { color: var(--red); }

  .note {
    font-family: var(--serif);
    font-size: 11px;
    font-style: italic;
    color: var(--muted);
    margin-top: 3px;
    line-height: 1.4;
  }
</style>
