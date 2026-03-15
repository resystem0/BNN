<script>
  import StatPair from '$lib/components/shared/StatPair.svelte';

  // Mock ledger data
  const ledger = [
    { hop: 1, route: 'quantum_mechanics → information_theory', miner: 'uid-047', score: 0.91, pool: 0.428, earn: 0.0089 },
    { hop: 2, route: 'information_theory → computability', miner: 'uid-112', score: 0.78, pool: 0.391, earn: 0.0067 },
    { hop: 3, route: 'computability → recursion', miner: 'uid-023', score: 0.65, pool: 0.402, earn: 0.0051 },
    { hop: 4, route: 'recursion → consciousness', miner: 'uid-187', score: 0.83, pool: 0.415, earn: 0.0074 },
    { hop: 5, route: 'consciousness → epistemology', miner: 'uid-067', score: 0.59, pool: 0.388, earn: 0.0044 },
    { hop: 6, route: 'epistemology → information_theory', miner: 'uid-099', score: 0.87, pool: 0.421, earn: 0.0081 },
  ];

  const pools = [
    { label: 'Traversal Pool', amount: 1.847, fill: 0.62, color: '#4f7bff' },
    { label: 'Quality Pool', amount: 0.923, fill: 0.38, color: '#1a7a6e' },
    { label: 'Topology Pool', amount: 0.461, fill: 0.22, color: '#4a3580' },
  ];

  function scoreClass(s) {
    if (s >= 0.8) return 'teal';
    if (s >= 0.65) return 'amber';
    return 'red';
  }

  function handleExport() {
    const data = { ledger, pools, exportedAt: new Date().toISOString() };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `axon-session-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
</script>

<svelte:head>
  <title>Axon Graph — Treasury</title>
</svelte:head>

<div class="page theme-light">
  <!-- Page header -->
  <header class="page-header">
    <div class="header-left">
      <a href="/" class="back-link">← GRAPH</a>
      <h1 class="page-title">TREASURY</h1>
      <span class="page-sub">Session ledger & pool breakdown</span>
    </div>
  </header>

  <div class="page-body">
    <!-- Main column -->
    <div class="main-col">
      <!-- Traversal ledger -->
      <section class="section">
        <div class="section-heading">TRAVERSAL LEDGER</div>
        <div class="table-wrap">
          <table class="ledger-table">
            <thead>
              <tr>
                <th>HOP / ROUTE</th>
                <th>MINER</th>
                <th>SCORE</th>
                <th>POOL τ</th>
                <th>EARN τ</th>
              </tr>
            </thead>
            <tbody>
              {#each ledger as row, i}
                <tr class:alt={i % 2 === 1}>
                  <td>
                    <span class="hop-num">{row.hop}</span>
                    <span class="route">{row.route.replace(/_/g, ' ')}</span>
                  </td>
                  <td class="mono-cell">{row.miner}</td>
                  <td>
                    <span class="score-val {scoreClass(row.score)}">{row.score.toFixed(2)}</span>
                  </td>
                  <td class="mono-cell">{row.pool.toFixed(3)}</td>
                  <td class="mono-cell earn">{row.earn.toFixed(4)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </section>

      <!-- Pool breakdown -->
      <section class="section">
        <div class="section-heading">POOL BREAKDOWN</div>
        <div class="pools">
          {#each pools as pool}
            <div class="pool-row">
              <div class="pool-meta">
                <span class="pool-label">{pool.label}</span>
                <span class="pool-amount">{pool.amount.toFixed(3)} τ</span>
              </div>
              <div class="pool-track">
                <div class="pool-fill" style="width: {pool.fill * 100}%; background: {pool.color}"></div>
              </div>
            </div>
          {/each}
        </div>
      </section>
    </div>

    <!-- Right sidebar -->
    <aside class="side-col">
      <div class="side-block">
        <div class="section-heading">SESSION TOTALS</div>
        <StatPair label="Total Earned" value="0.0406 τ" valueClass="teal" />
        <StatPair label="Avg Score" value="0.772" />
        <StatPair label="Hops" value="6" />
        <StatPair label="Duration" value="4m 12s" />
      </div>

      <div class="side-block">
        <div class="section-heading">NETWORK STATE</div>
        <StatPair label="Block" value="1,847,310" />
        <StatPair label="Epoch" value="1,847" />
        <StatPair label="Active Miners" value="47" />
        <StatPair label="Validators" value="12" />
      </div>

      <div class="side-block">
        <button class="export-btn" on:click={handleExport}>
          EXPORT SESSION JSON
        </button>
      </div>
    </aside>
  </div>
</div>

<style>
  .page {
    min-height: 100vh;
    background: var(--vellum);
    color: var(--ink);
    font-family: var(--serif);
  }

  /* Header */
  .page-header {
    padding: 20px 32px 16px;
    border-bottom: 1px solid var(--rule-strong);
    background: var(--vellum2);
  }

  .header-left {
    display: flex;
    align-items: baseline;
    gap: 16px;
  }

  .back-link {
    font-family: var(--mono);
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.1em;
    color: var(--muted);
    text-decoration: none;
    transition: color 0.2s ease;
  }

  .back-link:hover { color: var(--teal); }

  .page-title {
    font-family: var(--mono);
    font-size: 16px;
    font-weight: 500;
    letter-spacing: 0.18em;
    color: var(--ink);
  }

  .page-sub {
    font-family: var(--serif);
    font-size: 13px;
    font-style: italic;
    color: var(--muted);
  }

  /* Layout */
  .page-body {
    display: grid;
    grid-template-columns: 1fr 220px;
    gap: 0;
    max-height: calc(100vh - 73px);
    overflow: hidden;
  }

  .main-col {
    padding: 24px 28px;
    overflow-y: auto;
    border-right: 1px solid var(--rule);
  }

  .side-col {
    padding: 20px 16px;
    background: var(--vellum2);
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 0;
  }

  /* Sections */
  .section {
    margin-bottom: 32px;
  }

  .section-heading {
    display: flex;
    align-items: center;
    gap: 8px;
    font-family: var(--mono);
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 12px;
  }

  .section-heading::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--rule);
  }

  /* Ledger table */
  .table-wrap {
    overflow-x: auto;
    border: 1px solid var(--rule-strong);
    border-radius: 2px;
  }

  .ledger-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }

  .ledger-table thead tr {
    background: var(--vellum3);
  }

  .ledger-table th {
    padding: 8px 12px;
    text-align: left;
    font-family: var(--mono);
    font-size: 9px;
    font-weight: 500;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
    border-bottom: 1px solid var(--rule-strong);
    white-space: nowrap;
  }

  .ledger-table td {
    padding: 8px 12px;
    border-bottom: 1px solid var(--rule);
    vertical-align: middle;
  }

  .ledger-table tr:last-child td {
    border-bottom: none;
  }

  .ledger-table tr.alt td {
    background: var(--vellum2);
  }

  .hop-num {
    font-family: var(--mono);
    font-size: 10px;
    font-weight: 600;
    color: var(--muted);
    margin-right: 8px;
  }

  .route {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--ink);
  }

  .mono-cell {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--ink);
  }

  .score-val {
    font-family: var(--mono);
    font-size: 12px;
    font-weight: 600;
  }

  .score-val.teal { color: var(--teal); }
  .score-val.amber { color: var(--amber); }
  .score-val.red { color: var(--red); }

  .earn {
    color: var(--teal);
    font-weight: 500;
  }

  /* Pools */
  .pools {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .pool-row {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .pool-meta {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
  }

  .pool-label {
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.05em;
    color: var(--ink);
  }

  .pool-amount {
    font-family: var(--mono);
    font-size: 12px;
    font-weight: 600;
    color: var(--ink);
  }

  .pool-track {
    height: 6px;
    background: var(--rule-strong);
    border-radius: 2px;
    overflow: hidden;
  }

  .pool-fill {
    height: 100%;
    border-radius: 2px;
    transition: width 0.5s cubic-bezier(0.16, 1, 0.3, 1);
  }

  /* Sidebar */
  .side-block {
    padding: 16px 0;
    border-bottom: 1px solid var(--rule);
  }

  .side-block:last-child {
    border-bottom: none;
    padding-top: 20px;
  }

  .export-btn {
    width: 100%;
    padding: 9px 14px;
    background: transparent;
    border: 1px solid var(--rule-strong);
    border-radius: 2px;
    font-family: var(--mono);
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.1em;
    color: var(--ink);
    cursor: pointer;
    text-align: center;
    transition: background 0.2s ease, border-color 0.2s ease;
  }

  .export-btn:hover {
    background: var(--teal-light);
    border-color: var(--teal);
    color: var(--teal);
  }
</style>
