<script>
  import ScoreBar from '$lib/components/shared/ScoreBar.svelte';
  import StatPair from '$lib/components/shared/StatPair.svelte';

  // Mock intelligence data
  const hops = [
    {
      num: 1,
      from: 'quantum_mechanics',
      to: 'information_theory',
      agentId: 'axon-agent-047',
      passage: `The lattice of causality folds upon itself at the threshold of <em>observation</em>. Each measurement collapses the wave-form into a singular thread of <em>realized history</em>, entangling the observer with the fabric of what becomes known.`,
      composite: 0.91,
      components: [
        { name: 'Groundedness', weight: '40%', score: 0.94, note: 'Strong corpus alignment with quantum measurement literature.' },
        { name: 'Coherence', weight: '35%', score: 0.88, note: 'Narrative arc maintains thematic consistency throughout.' },
        { name: 'Edge Utility', weight: '25%', score: 0.89, note: 'Transition to information theory well-motivated.' },
      ],
      miners: [
        { uid: 'uid-047', score: 0.91, stake: 847.3, ms: 312, earn: 0.0089, selected: true },
        { uid: 'uid-112', score: 0.84, stake: 623.1, ms: 441, earn: 0.0072, selected: false },
        { uid: 'uid-023', score: 0.79, stake: 1204.5, ms: 287, earn: 0.0065, selected: false },
        { uid: 'uid-187', score: 0.71, stake: 392.8, ms: 502, earn: 0.0055, selected: false },
      ],
      settlement: {
        pool: '0.428 τ', earned: '0.0089 τ', qualityRank: '1st / 47',
        validators: '12', responseTime: '312ms', epochBlock: '1,847,301'
      },
      checks: [
        { pass: true, label: 'Semantic drift < threshold', detail: '0.12 / 0.28' },
        { pass: true, label: 'Corpus citation verified', detail: '3 / 3 sources valid' },
        { pass: true, label: 'Edge traversal permitted', detail: 'Weight 0.70 confirmed' },
        { pass: false, label: 'Response latency', detail: '312ms / 250ms target' },
      ],
      deltas: [
        { edge: 'quantum_mechanics → information_theory', delta: +0.03 },
        { edge: 'information_theory → computability', delta: +0.01 },
        { edge: 'quantum_mechanics → relativity', delta: -0.01 },
      ],
    },
    {
      num: 2,
      from: 'information_theory',
      to: 'computability',
      agentId: 'axon-agent-112',
      passage: `In the space between <em>knowing</em> and not-knowing, the observer becomes entangled with the observed. The boundary dissolves like mist at dawn, revealing the <em>computational substrate</em> beneath all representation.`,
      composite: 0.78,
      components: [
        { name: 'Groundedness', weight: '40%', score: 0.82, note: 'Adequate grounding in information-theoretic concepts.' },
        { name: 'Coherence', weight: '35%', score: 0.76, note: 'Minor thematic drift in second passage half.' },
        { name: 'Edge Utility', weight: '25%', score: 0.72, note: 'Transition supported but not strongly motivated.' },
      ],
      miners: [
        { uid: 'uid-112', score: 0.78, stake: 623.1, ms: 441, earn: 0.0067, selected: true },
        { uid: 'uid-055', score: 0.74, stake: 881.2, ms: 398, earn: 0.0059, selected: false },
        { uid: 'uid-203', score: 0.69, stake: 445.7, ms: 521, earn: 0.0051, selected: false },
      ],
      settlement: {
        pool: '0.391 τ', earned: '0.0067 τ', qualityRank: '1st / 44',
        validators: '12', responseTime: '441ms', epochBlock: '1,847,306'
      },
      checks: [
        { pass: true, label: 'Semantic drift < threshold', detail: '0.19 / 0.28' },
        { pass: true, label: 'Corpus citation verified', detail: '2 / 2 sources valid' },
        { pass: true, label: 'Edge traversal permitted', detail: 'Weight 0.80 confirmed' },
        { pass: true, label: 'Response latency', detail: '441ms / 500ms target' },
      ],
      deltas: [
        { edge: 'information_theory → computability', delta: +0.02 },
        { edge: 'computability → recursion', delta: +0.01 },
      ],
    },
  ];

  let activeTab = 0;
  $: hop = hops[activeTab];
</script>

<svelte:head>
  <title>Axon Graph — Intelligence</title>
</svelte:head>

<div class="page theme-light">
  <!-- Tab bar -->
  <div class="tab-bar">
    <a href="/" class="back-link">← GRAPH</a>
    {#each hops as h, i}
      <button
        class="tab"
        class:active={activeTab === i}
        on:click={() => activeTab = i}
      >
        <span class="tab-hop">HOP {h.num}</span>
        <span class="tab-route">{h.from.replace(/_/g, ' ')} → {h.to.replace(/_/g, ' ')}</span>
      </button>
    {/each}
  </div>

  <!-- Panel body -->
  <div class="panel-body">
    <!-- Main column -->
    <div class="main-col">
      <!-- Passage block -->
      <section class="section">
        <div class="section-heading">PASSAGE</div>
        <div class="passage-block">
          <div class="passage-route">
            <span class="route-from">{hop.from.replace(/_/g, ' ')}</span>
            <span class="route-arrow"> → </span>
            <span class="route-to">{hop.to.replace(/_/g, ' ')}</span>
            <span class="agent-id">{hop.agentId}</span>
          </div>
          <p class="passage-text">{@html hop.passage}</p>
        </div>
      </section>

      <!-- Validator scoring -->
      <section class="section">
        <div class="section-heading">VALIDATOR SCORING</div>
        <div class="composite-score">
          <span class="composite-label">COMPOSITE</span>
          <span class="composite-val {hop.composite >= 0.8 ? 'teal' : hop.composite >= 0.65 ? 'amber' : 'red'}">
            {hop.composite.toFixed(2)}
          </span>
        </div>
        <div class="score-components">
          {#each hop.components as c}
            <ScoreBar score={c.score} label={c.name} weight={c.weight} note={c.note} />
          {/each}
        </div>
      </section>

      <!-- Competing miners -->
      <section class="section">
        <div class="section-heading">COMPETING MINERS</div>
        <div class="table-wrap">
          <table class="miners-table">
            <thead>
              <tr>
                <th>#</th>
                <th>UID</th>
                <th>SCORE</th>
                <th>STAKE τ</th>
                <th>MS</th>
                <th>EARN τ</th>
              </tr>
            </thead>
            <tbody>
              {#each hop.miners as miner, idx}
                <tr class:selected-row={miner.selected}>
                  <td class="mono-cell muted">{idx + 1}</td>
                  <td class="mono-cell">
                    {miner.uid}
                    {#if miner.selected}<span class="selected-badge">SELECTED</span>{/if}
                  </td>
                  <td>
                    <span class="score-val {miner.score >= 0.8 ? 'teal' : miner.score >= 0.65 ? 'amber' : 'red'}">
                      {miner.score.toFixed(2)}
                    </span>
                  </td>
                  <td class="mono-cell">{miner.stake.toFixed(1)}</td>
                  <td class="mono-cell">{miner.ms}</td>
                  <td class="mono-cell">{miner.earn.toFixed(4)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <!-- Side column -->
    <aside class="side-col">
      <!-- Hop settlement -->
      <div class="side-block">
        <div class="section-heading">HOP SETTLEMENT</div>
        <StatPair label="Pool" value={hop.settlement.pool} />
        <StatPair label="Earned" value={hop.settlement.earned} valueClass="teal" />
        <StatPair label="Quality Rank" value={hop.settlement.qualityRank} />
        <StatPair label="Validators" value={hop.settlement.validators} />
        <StatPair label="Response" value={hop.settlement.responseTime} />
        <StatPair label="Epoch Block" value={hop.settlement.epochBlock} />
      </div>

      <!-- Corpus verification -->
      <div class="side-block">
        <div class="section-heading">CORPUS VERIFICATION</div>
        <div class="checks">
          {#each hop.checks as check}
            <div class="check-row">
              <span class="check-icon {check.pass ? 'pass' : 'fail'}">{check.pass ? '✓' : '✗'}</span>
              <div class="check-text">
                <span class="check-label">{check.label}</span>
                <span class="check-detail">{check.detail}</span>
              </div>
            </div>
          {/each}
        </div>
      </div>

      <!-- Graph deltas -->
      <div class="side-block">
        <div class="section-heading">GRAPH DELTAS</div>
        <div class="deltas">
          {#each hop.deltas as delta}
            <div class="delta-row">
              <span class="delta-edge">{delta.edge.replace(/_/g, ' ')}</span>
              <span class="delta-val {delta.delta > 0 ? 'pos' : 'neg'}">
                {delta.delta > 0 ? '+' : ''}{delta.delta.toFixed(2)}
              </span>
            </div>
          {/each}
        </div>
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
    display: flex;
    flex-direction: column;
  }

  /* Tab bar */
  .tab-bar {
    display: flex;
    align-items: stretch;
    background: var(--ink);
    border-bottom: 1px solid rgba(255,255,255,0.08);
    overflow-x: auto;
    flex-shrink: 0;
  }

  .back-link {
    display: flex;
    align-items: center;
    padding: 0 16px;
    font-family: var(--mono);
    font-size: 9px;
    font-weight: 500;
    letter-spacing: 0.1em;
    color: rgba(245,240,232,0.4);
    text-decoration: none;
    transition: color 0.2s ease;
    border-right: 1px solid rgba(255,255,255,0.08);
    white-space: nowrap;
    flex-shrink: 0;
  }

  .back-link:hover { color: rgba(245,240,232,0.8); }

  .tab {
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 10px 16px;
    border: none;
    background: none;
    cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: border-color 0.2s ease;
    text-align: left;
    white-space: nowrap;
    flex-shrink: 0;
    gap: 2px;
  }

  .tab.active {
    border-bottom-color: var(--teal);
  }

  .tab-hop {
    font-family: var(--mono);
    font-size: 9px;
    font-weight: 500;
    letter-spacing: 0.1em;
    color: rgba(245,240,232,0.45);
    text-transform: uppercase;
  }

  .tab.active .tab-hop { color: rgba(245,240,232,0.7); }

  .tab-route {
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 400;
    color: rgba(245,240,232,0.6);
  }

  .tab.active .tab-route { color: rgba(245,240,232,0.95); }

  /* Body layout */
  .panel-body {
    display: grid;
    grid-template-columns: 1fr 220px;
    flex: 1;
    overflow: hidden;
    max-height: calc(100vh - 60px);
  }

  .main-col {
    padding: 24px 28px;
    overflow-y: auto;
    border-right: 1px solid var(--rule);
  }

  .side-col {
    padding: 16px;
    background: var(--vellum2);
    overflow-y: auto;
  }

  /* Sections */
  .section {
    margin-bottom: 28px;
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

  /* Passage */
  .passage-block {
    background: var(--vellum2);
    border: 1px solid var(--rule-strong);
    border-radius: 2px;
    padding: 16px;
  }

  .passage-route {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: 12px;
    flex-wrap: wrap;
  }

  .route-from, .route-to {
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 500;
    color: var(--ink);
    text-transform: capitalize;
  }

  .route-arrow {
    color: var(--muted);
    font-size: 12px;
  }

  .agent-id {
    font-family: var(--mono);
    font-size: 10px;
    color: var(--muted);
    margin-left: auto;
  }

  .passage-text {
    font-family: var(--serif);
    font-size: 15px;
    font-style: italic;
    line-height: 1.75;
    color: var(--ink);
  }

  :global(.passage-text em) {
    color: var(--teal);
    font-style: italic;
    font-weight: 700;
    background: var(--teal-light);
    padding: 0 2px;
    border-radius: 1px;
  }

  /* Composite score */
  .composite-score {
    display: flex;
    align-items: baseline;
    gap: 12px;
    margin-bottom: 16px;
  }

  .composite-label {
    font-family: var(--mono);
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.1em;
    color: var(--muted);
  }

  .composite-val {
    font-family: var(--mono);
    font-size: 28px;
    font-weight: 600;
    line-height: 1;
  }

  .composite-val.teal { color: var(--teal); }
  .composite-val.amber { color: var(--amber); }
  .composite-val.red { color: var(--red); }

  .score-components {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  /* Miners table */
  .table-wrap {
    overflow-x: auto;
    border: 1px solid var(--rule-strong);
    border-radius: 2px;
  }

  .miners-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }

  .miners-table thead tr {
    background: var(--vellum3);
  }

  .miners-table th {
    padding: 7px 10px;
    text-align: left;
    font-family: var(--mono);
    font-size: 9px;
    font-weight: 500;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
    border-bottom: 1px solid var(--rule-strong);
  }

  .miners-table td {
    padding: 7px 10px;
    border-bottom: 1px solid var(--rule);
    vertical-align: middle;
  }

  .miners-table tr:last-child td { border-bottom: none; }

  .selected-row td {
    background: var(--teal-light);
  }

  .mono-cell {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--ink);
  }

  .muted { color: var(--muted); }

  .score-val {
    font-family: var(--mono);
    font-size: 12px;
    font-weight: 600;
  }

  .score-val.teal { color: var(--teal); }
  .score-val.amber { color: var(--amber); }
  .score-val.red { color: var(--red); }

  .selected-badge {
    display: inline-flex;
    align-items: center;
    padding: 1px 5px;
    margin-left: 6px;
    font-family: var(--mono);
    font-size: 8px;
    font-weight: 600;
    letter-spacing: 0.08em;
    background: var(--teal);
    color: white;
    border-radius: 2px;
    vertical-align: middle;
  }

  /* Sidebar */
  .side-block {
    padding: 16px 0;
    border-bottom: 1px solid var(--rule);
  }

  .side-block:last-child { border-bottom: none; }

  /* Checks */
  .checks {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .check-row {
    display: flex;
    align-items: flex-start;
    gap: 8px;
  }

  .check-icon {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 9px;
    font-weight: 700;
    flex-shrink: 0;
    margin-top: 1px;
  }

  .check-icon.pass {
    background: var(--teal-light);
    color: var(--teal);
  }

  .check-icon.fail {
    background: var(--red-light);
    color: var(--red);
  }

  .check-text {
    display: flex;
    flex-direction: column;
    gap: 1px;
  }

  .check-label {
    font-family: var(--mono);
    font-size: 10px;
    font-weight: 500;
    color: var(--ink);
  }

  .check-detail {
    font-family: var(--mono);
    font-size: 9px;
    color: var(--muted);
  }

  /* Deltas */
  .deltas {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .delta-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 8px;
  }

  .delta-edge {
    font-family: var(--mono);
    font-size: 9px;
    color: var(--muted);
    flex: 1;
    text-transform: capitalize;
    line-height: 1.4;
  }

  .delta-val {
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 600;
    flex-shrink: 0;
  }

  .delta-val.pos { color: var(--teal); }
  .delta-val.neg { color: var(--red); }
</style>
