<script>
  import StatPair from '$lib/components/shared/StatPair.svelte';

  // Mock miner data
  const miners = [
    {
      uid: 'uid-047',
      domain: 'Quantum / Physics',
      node: 'quantum_mechanics',
      age: '47 epochs',
      status: ['LIVE', 'HEALTHY'],
      meanScore: 0.871,
      winRate: 0.68,
      taoEarned: 1.2847,
      scoreHistory: [0.82, 0.87, 0.91, 0.84, 0.88, 0.92, 0.79, 0.91, 0.85, 0.94, 0.88, 0.87],
      passages: [
        {
          route: 'quantum_mechanics → information_theory',
          score: 0.91,
          text: `The lattice of causality folds upon itself at the threshold of <em>observation</em>. Each measurement collapses the wave-form.`,
        },
        {
          route: 'quantum_mechanics → relativity',
          score: 0.84,
          text: `At the boundary of <em>spacetime curvature</em>, quantum effects become non-negligible, revealing the unified substrate.`,
        },
      ],
      headToHead: [
        { opponent: 'uid-112', epoch: '1,847', myScore: 0.91, theirScore: 0.84, result: 'WON' },
        { opponent: 'uid-023', epoch: '1,844', myScore: 0.79, theirScore: 0.83, result: 'LOST' },
        { opponent: 'uid-187', epoch: '1,840', myScore: 0.88, theirScore: 0.71, result: 'WON' },
      ],
      stake: '847.3 τ',
      networkRank: '3rd / 256',
      totalHops: 312,
      corpusSize: '1,847 docs',
      responseTime: '312ms avg',
      activeSince: 'Epoch 1,800',
      integrity: [
        { status: 'pass', label: 'Semantic drift below 0.28', detail: '0.12 current' },
        { status: 'pass', label: 'Corpus freshness', detail: 'Updated epoch 1,847' },
        { status: 'warn', label: 'Response latency SLA', detail: '312ms / 250ms target' },
      ],
      driftValue: 0.12,
      fingerprint: [
        { label: 'Lyric density', value: 0.72 },
        { label: '2nd person', value: 0.18 },
        { label: 'Sentence len', value: 0.55 },
        { label: 'Abstraction', value: 0.81 },
        { label: 'Metaphor rate', value: 0.64 },
      ],
    },
    {
      uid: 'uid-112',
      domain: 'Information / CS',
      node: 'information_theory',
      age: '31 epochs',
      status: ['LIVE', 'HEALTHY', 'NARRATIVE'],
      meanScore: 0.801,
      winRate: 0.55,
      taoEarned: 0.8234,
      scoreHistory: [0.78, 0.82, 0.79, 0.84, 0.80, 0.77, 0.83, 0.81, 0.79, 0.85, 0.82, 0.80],
      passages: [
        {
          route: 'information_theory → computability',
          score: 0.84,
          text: `In the space between <em>knowing</em> and not-knowing, the observer becomes entangled with the observed.`,
        },
      ],
      headToHead: [
        { opponent: 'uid-047', epoch: '1,847', myScore: 0.84, theirScore: 0.91, result: 'LOST' },
        { opponent: 'uid-055', epoch: '1,844', myScore: 0.82, theirScore: 0.74, result: 'WON' },
      ],
      stake: '623.1 τ',
      networkRank: '7th / 256',
      totalHops: 198,
      corpusSize: '1,203 docs',
      responseTime: '441ms avg',
      activeSince: 'Epoch 1,816',
      integrity: [
        { status: 'pass', label: 'Semantic drift below 0.28', detail: '0.19 current' },
        { status: 'warn', label: 'Corpus freshness', detail: 'Updated epoch 1,844' },
        { status: 'pass', label: 'Response latency SLA', detail: '441ms / 500ms target' },
      ],
      driftValue: 0.19,
      fingerprint: [
        { label: 'Lyric density', value: 0.41 },
        { label: '2nd person', value: 0.33 },
        { label: 'Sentence len', value: 0.62 },
        { label: 'Abstraction', value: 0.74 },
        { label: 'Metaphor rate', value: 0.48 },
      ],
    },
  ];

  let activeTab = 0;
  $: miner = miners[activeTab];

  const statusColors = {
    LIVE: { bg: 'var(--teal-light)', color: 'var(--teal)' },
    HEALTHY: { bg: 'var(--teal-light)', color: 'var(--teal)' },
    WARNING: { bg: 'var(--amber-light)', color: 'var(--amber)' },
    SLASH: { bg: 'var(--red-light)', color: 'var(--red)' },
    NARRATIVE: { bg: 'var(--purple-light)', color: 'var(--purple)' },
  };

  // Mini bar chart: 12 bars, height proportional to score above 0.5 baseline
  function barHeight(score) {
    return Math.max(2, Math.round((score - 0.5) / 0.5 * 36));
  }
</script>

<svelte:head>
  <title>Axon Graph — Dossier</title>
</svelte:head>

<div class="page theme-light">
  <!-- Tab bar -->
  <div class="tab-bar">
    <a href="/" class="back-link">← GRAPH</a>
    {#each miners as m, i}
      <button
        class="tab"
        class:active={activeTab === i}
        on:click={() => activeTab = i}
      >
        <span class="tab-uid">{m.uid}</span>
        <span class="tab-domain">{m.domain}</span>
      </button>
    {/each}
  </div>

  <!-- Panel body -->
  <div class="panel-body">
    <!-- Main column -->
    <div class="main-col">
      <!-- Identity block -->
      <section class="section">
        <div class="section-heading">IDENTITY</div>
        <div class="identity-block">
          <div class="glyph-sq">{miner.uid.replace('uid-', '')}</div>
          <div class="identity-info">
            <div class="miner-uid">{miner.uid}</div>
            <div class="miner-sub">{miner.domain} · {miner.node.replace(/_/g, ' ')} · {miner.age}</div>
            <div class="badges">
              {#each miner.status as s}
                <span
                  class="badge"
                  style="background: {statusColors[s]?.bg ?? '#eee'}; color: {statusColors[s]?.color ?? '#333'}"
                >{s}</span>
              {/each}
            </div>
          </div>
        </div>
      </section>

      <!-- Performance block -->
      <section class="section">
        <div class="section-heading">PERFORMANCE</div>
        <div class="perf-grid">
          <div class="perf-cell">
            <span class="perf-label">MEAN SCORE</span>
            <span class="perf-val {miner.meanScore >= 0.8 ? 'teal' : miner.meanScore >= 0.65 ? 'amber' : 'red'}">
              {miner.meanScore.toFixed(3)}
            </span>
          </div>
          <div class="perf-cell">
            <span class="perf-label">WIN RATE</span>
            <span class="perf-val">{(miner.winRate * 100).toFixed(0)}%</span>
          </div>
          <div class="perf-cell">
            <span class="perf-label">TAO EARNED</span>
            <span class="perf-val teal">{miner.taoEarned.toFixed(4)} τ</span>
          </div>
        </div>

        <!-- Score history mini chart -->
        <div class="score-history">
          <div class="score-history-label">SCORE HISTORY</div>
          <div class="bar-chart">
            {#each miner.scoreHistory as score, idx}
              <div class="bar-col">
                <div
                  class="bar"
                  style="height: {barHeight(score)}px"
                  class:teal={score >= 0.8}
                  class:amber={score >= 0.65 && score < 0.8}
                  class:red={score < 0.65}
                  title="{score.toFixed(2)}"
                ></div>
              </div>
            {/each}
          </div>
          <div class="bar-baseline"></div>
        </div>
      </section>

      <!-- Sample passages -->
      <section class="section">
        <div class="section-heading">SAMPLE PASSAGES</div>
        <div class="passages">
          {#each miner.passages as p}
            <div class="passage-card">
              <div class="passage-card-header">
                <span class="passage-route">{p.route.replace(/_/g, ' ')}</span>
                <span class="passage-score {p.score >= 0.8 ? 'teal' : p.score >= 0.65 ? 'amber' : 'red'}">
                  {p.score.toFixed(2)}
                </span>
              </div>
              <p class="passage-text">{@html p.text}</p>
            </div>
          {/each}
        </div>
      </section>

      <!-- Head-to-head record -->
      <section class="section">
        <div class="section-heading">HEAD-TO-HEAD RECORD</div>
        <div class="table-wrap">
          <table class="h2h-table">
            <thead>
              <tr>
                <th>OPPONENT</th>
                <th>EPOCH</th>
                <th>MY SCORE</th>
                <th>THEIR SCORE</th>
                <th>RESULT</th>
              </tr>
            </thead>
            <tbody>
              {#each miner.headToHead as h}
                <tr>
                  <td class="mono-cell">{h.opponent}</td>
                  <td class="mono-cell">{h.epoch}</td>
                  <td>
                    <span class="score-val {h.myScore >= 0.8 ? 'teal' : h.myScore >= 0.65 ? 'amber' : 'red'}">
                      {h.myScore.toFixed(2)}
                    </span>
                  </td>
                  <td>
                    <span class="score-val {h.theirScore >= 0.8 ? 'teal' : h.theirScore >= 0.65 ? 'amber' : 'red'}">
                      {h.theirScore.toFixed(2)}
                    </span>
                  </td>
                  <td>
                    <span class="result-badge {h.result === 'WON' ? 'won' : 'lost'}">{h.result}</span>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <!-- Side column -->
    <aside class="side-col">
      <!-- Stake & network -->
      <div class="side-block">
        <div class="section-heading">STAKE & NETWORK</div>
        <StatPair label="Stake" value={miner.stake} />
        <StatPair label="Network Rank" value={miner.networkRank} />
        <StatPair label="Total Hops" value={String(miner.totalHops)} />
        <StatPair label="Corpus Size" value={miner.corpusSize} />
        <StatPair label="Response" value={miner.responseTime} />
        <StatPair label="Active Since" value={miner.activeSince} />
      </div>

      <!-- Corpus integrity -->
      <div class="side-block">
        <div class="section-heading">CORPUS INTEGRITY</div>
        <div class="checks">
          {#each miner.integrity as check}
            <div class="check-row">
              <span class="check-icon {check.status}">{check.status === 'pass' ? '✓' : check.status === 'warn' ? '!' : '✗'}</span>
              <div class="check-text">
                <span class="check-label">{check.label}</span>
                <span class="check-detail">{check.detail}</span>
              </div>
            </div>
          {/each}
        </div>

        <!-- Semantic drift bar -->
        <div class="drift-bar-wrap">
          <div class="drift-header">
            <span class="drift-label">SEMANTIC DRIFT</span>
            <span class="drift-val {miner.driftValue < 0.2 ? 'teal' : miner.driftValue < 0.28 ? 'amber' : 'red'}">
              {miner.driftValue.toFixed(2)} / 0.28
            </span>
          </div>
          <div class="drift-track">
            <div
              class="drift-fill {miner.driftValue < 0.2 ? 'teal' : miner.driftValue < 0.28 ? 'amber' : 'red'}"
              style="width: {(miner.driftValue / 0.28) * 100}%"
            ></div>
            <!-- Threshold marker -->
            <div class="drift-threshold"></div>
          </div>
        </div>
      </div>

      <!-- Narrative fingerprint -->
      <div class="side-block">
        <div class="section-heading">NARRATIVE FINGERPRINT</div>
        <div class="fingerprint">
          {#each miner.fingerprint as dim}
            <div class="fp-row">
              <span class="fp-label">{dim.label}</span>
              <div class="fp-track">
                <div class="fp-fill" style="width: {dim.value * 100}%"></div>
              </div>
              <span class="fp-val">{dim.value.toFixed(2)}</span>
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
    padding: 10px 20px;
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

  .tab.active { border-bottom-color: var(--purple); }

  .tab-uid {
    font-family: var(--mono);
    font-size: 12px;
    font-weight: 500;
    color: rgba(245,240,232,0.7);
  }

  .tab.active .tab-uid { color: rgba(245,240,232,0.95); }

  .tab-domain {
    font-family: var(--mono);
    font-size: 9px;
    color: rgba(245,240,232,0.35);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  /* Body layout */
  .panel-body {
    display: grid;
    grid-template-columns: 1fr 220px;
    flex: 1;
    overflow: hidden;
    max-height: calc(100vh - 62px);
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
  .section { margin-bottom: 28px; }

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

  /* Identity */
  .identity-block {
    display: flex;
    align-items: flex-start;
    gap: 16px;
  }

  .glyph-sq {
    width: 48px;
    height: 48px;
    background: var(--vellum3);
    border: 1px solid var(--rule-strong);
    border-radius: 2px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: var(--mono);
    font-size: 13px;
    font-weight: 600;
    color: var(--ink);
    flex-shrink: 0;
  }

  .identity-info {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .miner-uid {
    font-family: var(--mono);
    font-size: 18px;
    font-weight: 600;
    color: var(--ink);
    line-height: 1.2;
  }

  .miner-sub {
    font-family: var(--mono);
    font-size: 10px;
    color: var(--muted);
    letter-spacing: 0.04em;
    text-transform: capitalize;
  }

  .badges {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
    margin-top: 2px;
  }

  .badge {
    font-family: var(--mono);
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.08em;
    padding: 2px 6px;
    border-radius: 2px;
  }

  /* Performance grid */
  .perf-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1px;
    background: var(--rule-strong);
    border: 1px solid var(--rule-strong);
    border-radius: 2px;
    margin-bottom: 16px;
  }

  .perf-cell {
    background: var(--vellum2);
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .perf-label {
    font-family: var(--mono);
    font-size: 9px;
    font-weight: 500;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
  }

  .perf-val {
    font-family: var(--mono);
    font-size: 20px;
    font-weight: 600;
    color: var(--ink);
    line-height: 1.2;
  }

  .perf-val.teal { color: var(--teal); }
  .perf-val.amber { color: var(--amber); }
  .perf-val.red { color: var(--red); }

  /* Score history chart */
  .score-history {
    position: relative;
  }

  .score-history-label {
    font-family: var(--mono);
    font-size: 9px;
    font-weight: 500;
    letter-spacing: 0.1em;
    color: var(--muted);
    margin-bottom: 8px;
    text-transform: uppercase;
  }

  .bar-chart {
    display: flex;
    align-items: flex-end;
    gap: 3px;
    height: 40px;
    padding-bottom: 2px;
  }

  .bar-col {
    flex: 1;
    display: flex;
    align-items: flex-end;
  }

  .bar {
    width: 100%;
    border-radius: 1px 1px 0 0;
    min-height: 2px;
    transition: height 0.3s ease;
  }

  .bar.teal { background: var(--teal); }
  .bar.amber { background: var(--amber); }
  .bar.red { background: var(--red); }

  .bar-baseline {
    height: 1px;
    background: var(--rule-strong);
    margin-top: 0;
  }

  /* Passages */
  .passages {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .passage-card {
    background: var(--vellum2);
    border: 1px solid var(--rule-strong);
    border-radius: 2px;
    padding: 12px 14px;
  }

  .passage-card-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 8px;
  }

  .passage-route {
    font-family: var(--mono);
    font-size: 10px;
    font-weight: 500;
    color: var(--muted);
    text-transform: capitalize;
  }

  .passage-score {
    font-family: var(--mono);
    font-size: 12px;
    font-weight: 600;
  }

  .passage-score.teal { color: var(--teal); }
  .passage-score.amber { color: var(--amber); }
  .passage-score.red { color: var(--red); }

  .passage-text {
    font-family: var(--serif);
    font-size: 14px;
    font-style: italic;
    line-height: 1.65;
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

  /* Head to head table */
  .table-wrap {
    overflow-x: auto;
    border: 1px solid var(--rule-strong);
    border-radius: 2px;
  }

  .h2h-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }

  .h2h-table thead tr { background: var(--vellum3); }

  .h2h-table th {
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

  .h2h-table td {
    padding: 7px 10px;
    border-bottom: 1px solid var(--rule);
    vertical-align: middle;
  }

  .h2h-table tr:last-child td { border-bottom: none; }

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

  .result-badge {
    font-family: var(--mono);
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.08em;
    padding: 2px 6px;
    border-radius: 2px;
  }

  .result-badge.won {
    background: var(--teal-light);
    color: var(--teal);
  }

  .result-badge.lost {
    background: var(--red-light);
    color: var(--red);
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
    margin-bottom: 12px;
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

  .check-icon.pass { background: var(--teal-light); color: var(--teal); }
  .check-icon.warn { background: var(--amber-light); color: var(--amber); }
  .check-icon.fail { background: var(--red-light); color: var(--red); }

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

  /* Drift bar */
  .drift-bar-wrap { margin-top: 4px; }

  .drift-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    margin-bottom: 4px;
  }

  .drift-label {
    font-family: var(--mono);
    font-size: 9px;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted);
  }

  .drift-val {
    font-family: var(--mono);
    font-size: 11px;
    font-weight: 600;
  }

  .drift-val.teal { color: var(--teal); }
  .drift-val.amber { color: var(--amber); }
  .drift-val.red { color: var(--red); }

  .drift-track {
    height: 5px;
    background: var(--rule-strong);
    border-radius: 2px;
    overflow: hidden;
    position: relative;
  }

  .drift-fill {
    height: 100%;
    border-radius: 2px;
    transition: width 0.4s ease;
  }

  .drift-fill.teal { background: var(--teal); }
  .drift-fill.amber { background: var(--amber); }
  .drift-fill.red { background: var(--red); }

  .drift-threshold {
    position: absolute;
    right: 0;
    top: 0;
    width: 1px;
    height: 100%;
    background: var(--ink);
    opacity: 0.3;
  }

  /* Fingerprint */
  .fingerprint {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .fp-row {
    display: grid;
    grid-template-columns: 90px 1fr 32px;
    align-items: center;
    gap: 6px;
  }

  .fp-label {
    font-family: var(--mono);
    font-size: 9px;
    font-weight: 500;
    letter-spacing: 0.04em;
    color: var(--ink);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .fp-track {
    height: 4px;
    background: var(--rule-strong);
    border-radius: 2px;
    overflow: hidden;
  }

  .fp-fill {
    height: 100%;
    background: var(--purple);
    border-radius: 2px;
    transition: width 0.4s ease;
  }

  .fp-val {
    font-family: var(--mono);
    font-size: 9px;
    color: var(--muted);
    text-align: right;
  }
</style>
