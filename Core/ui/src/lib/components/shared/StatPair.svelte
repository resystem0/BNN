<script>
  export let label = '';
  export let value = '';
  export let valueClass = '';
  export let mono = true;
</script>

<div class="stat-pair">
  <span class="stat-label">{label}</span>
  <span class="stat-value {valueClass}" class:mono-val={mono}>{value}</span>
</div>

<style>
  .stat-pair {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 5px 0;
    border-bottom: 1px solid var(--rule);
  }

  .stat-label {
    font-family: var(--mono);
    font-size: 10px;
    font-weight: 400;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--muted);
  }

  .stat-value {
    font-size: 13px;
    color: var(--ink);
  }

  .mono-val {
    font-family: var(--mono);
    font-size: 12px;
    font-weight: 500;
  }
</style>
