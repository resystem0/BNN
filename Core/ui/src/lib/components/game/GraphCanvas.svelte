<script>
  import { onMount, onDestroy } from 'svelte';
  import * as d3 from 'd3';
  import { nodes, edges } from '$lib/stores/graph.js';
  import { currentNode } from '$lib/stores/session.js';
  import { navigate } from '$lib/stores/session.js';

  let svgEl;
  let containerEl;
  let simulation;
  let width = 300;
  let height = 400;
  let resizeObserver;

  // Domain color map
  const domainColor = {
    physics: '#4f7bff',
    computer_science: '#00e5b0',
    biology: '#4caf7d',
    astronomy: '#9c6fe4',
    chemistry: '#e8a44a',
    mathematics: '#e8c87a',
    philosophy: '#e06b6b',
  };

  function getColor(domain) {
    return domainColor[domain] || '#888';
  }

  function buildGraph(nodesData, edgesData, currentNodeId) {
    if (!svgEl) return;

    d3.select(svgEl).selectAll('*').remove();

    const svg = d3.select(svgEl)
      .attr('width', width)
      .attr('height', height);

    // Defs: glow filter
    const defs = svg.append('defs');
    const filter = defs.append('filter').attr('id', 'node-glow');
    filter.append('feGaussianBlur').attr('stdDeviation', '3').attr('result', 'blur');
    const feMerge = filter.append('feMerge');
    feMerge.append('feMergeNode').attr('in', 'blur');
    feMerge.append('feMergeNode').attr('in', 'SourceGraphic');

    // Deep copy to avoid D3 mutating the store objects
    const nodesCopy = nodesData.map((n) => ({ ...n }));
    const edgesCopy = edgesData.map((e) => ({ ...e }));

    // Link source/target to node objects
    const nodeById = new Map(nodesCopy.map((n) => [n.id, n]));
    const links = edgesCopy.map((e) => ({
      ...e,
      source: nodeById.get(e.source) || e.source,
      target: nodeById.get(e.target) || e.target,
    }));

    simulation = d3
      .forceSimulation(nodesCopy)
      .force('link', d3.forceLink(links).id((d) => d.id).distance(65).strength(0.6))
      .force('charge', d3.forceManyBody().strength(-180))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide(22));

    // Edges
    const link = svg.append('g')
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('stroke', 'rgba(79,123,255,0.2)')
      .attr('stroke-width', (d) => Math.max(0.5, d.weight * 2));

    // Node groups
    const node = svg.append('g')
      .selectAll('g')
      .data(nodesCopy)
      .join('g')
      .attr('class', 'node-group')
      .style('cursor', 'pointer')
      .call(
        d3.drag()
          .on('start', (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on('drag', (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on('end', (event, d) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          })
      )
      .on('click', (event, d) => {
        event.stopPropagation();
        navigate(d.id);
      });

    // Gold ring for current node
    node.append('circle')
      .attr('r', (d) => (d.id === currentNodeId ? 13 : 0))
      .attr('fill', 'none')
      .attr('stroke', '#e8c87a')
      .attr('stroke-width', 1.5)
      .attr('opacity', 0.8);

    // Node circle
    node.append('circle')
      .attr('r', 8)
      .attr('fill', (d) => getColor(d.domain))
      .attr('fill-opacity', (d) => (d.id === currentNodeId ? 1 : 0.7))
      .attr('stroke', (d) => (d.id === currentNodeId ? '#e8c87a' : 'rgba(255,255,255,0.15)'))
      .attr('stroke-width', (d) => (d.id === currentNodeId ? 1.5 : 0.5))
      .style('filter', (d) => (d.id === currentNodeId ? 'url(#node-glow)' : 'none'));

    // Labels — split on \n
    node.each(function (d) {
      const parts = d.label.split('\n');
      const g = d3.select(this);
      parts.forEach((part, i) => {
        g.append('text')
          .attr('dy', 18 + i * 11)
          .attr('text-anchor', 'middle')
          .attr('fill', d.id === currentNodeId ? '#e8c87a' : 'rgba(220,215,205,0.65)')
          .attr('font-family', "'JetBrains Mono', monospace")
          .attr('font-size', '7px')
          .attr('font-weight', d.id === currentNodeId ? '500' : '300')
          .attr('pointer-events', 'none')
          .text(part);
      });
    });

    // Hover tooltip
    node
      .on('mouseenter', function (event, d) {
        d3.select(this).select('circle:last-of-type')
          .attr('fill-opacity', 1)
          .attr('stroke', '#e8c87a')
          .attr('stroke-width', 1);
      })
      .on('mouseleave', function (event, d) {
        d3.select(this).select('circle:last-of-type')
          .attr('fill-opacity', d.id === currentNodeId ? 1 : 0.7)
          .attr('stroke', d.id === currentNodeId ? '#e8c87a' : 'rgba(255,255,255,0.15)')
          .attr('stroke-width', d.id === currentNodeId ? 1.5 : 0.5);
      });

    // Tick
    simulation.on('tick', () => {
      link
        .attr('x1', (d) => d.source.x)
        .attr('y1', (d) => d.source.y)
        .attr('x2', (d) => d.target.x)
        .attr('y2', (d) => d.target.y);

      node.attr('transform', (d) => `translate(${d.x},${d.y})`);
    });
  }

  // Reactive rebuild when currentNode changes
  let unsubNodes, unsubEdges, unsubCurrent;
  let nodesVal, edgesVal, currentVal;

  onMount(() => {
    if (containerEl) {
      width = containerEl.clientWidth || 300;
      height = containerEl.clientHeight || 400;
    }

    unsubNodes = nodes.subscribe((v) => { nodesVal = v; maybeRebuild(); });
    unsubEdges = edges.subscribe((v) => { edgesVal = v; maybeRebuild(); });
    unsubCurrent = currentNode.subscribe((v) => { currentVal = v; maybeRebuild(); });

    resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        width = entry.contentRect.width;
        height = entry.contentRect.height;
        maybeRebuild();
      }
    });
    if (containerEl) resizeObserver.observe(containerEl);
  });

  onDestroy(() => {
    if (simulation) simulation.stop();
    if (unsubNodes) unsubNodes();
    if (unsubEdges) unsubEdges();
    if (unsubCurrent) unsubCurrent();
    if (resizeObserver) resizeObserver.disconnect();
  });

  function maybeRebuild() {
    if (nodesVal && edgesVal && currentVal !== undefined && svgEl && width > 0 && height > 0) {
      if (simulation) simulation.stop();
      buildGraph(nodesVal, edgesVal, currentVal);
    }
  }
</script>

<div class="graph-container" bind:this={containerEl}>
  <svg bind:this={svgEl}></svg>
</div>

<style>
  .graph-container {
    width: 100%;
    height: 100%;
    position: relative;
    background: var(--void);
    overflow: hidden;
  }

  svg {
    width: 100%;
    height: 100%;
    display: block;
  }

  :global(.node-group) {
    transition: opacity 0.2s ease;
  }
</style>
