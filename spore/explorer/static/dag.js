// Spore Explorer — D3 DAG visualization

import { shortCid, statusColor } from './api.js';

let svg, g, linkGroup, nodeGroup, simulation;
let onNodeClick = null;

export function initDag(panelEl, onClick) {
  onNodeClick = onClick;
  const w = panelEl.clientWidth;
  const h = panelEl.clientHeight;

  svg = d3.select(panelEl)
    .append('svg')
    .attr('width', w)
    .attr('height', h);

  svg.append('defs').append('marker')
    .attr('id', 'arrowhead')
    .attr('viewBox', '0 -5 10 10')
    .attr('refX', 20)
    .attr('refY', 0)
    .attr('markerWidth', 6)
    .attr('markerHeight', 6)
    .attr('orient', 'auto')
    .append('path')
    .attr('d', 'M0,-5L10,0L0,5')
    .attr('class', 'edge-arrow');

  g = svg.append('g');

  const zoom = d3.zoom()
    .scaleExtent([0.1, 5])
    .on('zoom', (e) => g.attr('transform', e.transform));
  svg.call(zoom);

  linkGroup = g.append('g').attr('class', 'links');
  nodeGroup = g.append('g').attr('class', 'nodes');

  simulation = d3.forceSimulation()
    .force('link', d3.forceLink().id(d => d.id).distance(60).strength(0.8))
    .force('charge', d3.forceManyBody().strength(-120))
    .force('x', d3.forceX(w / 2).strength(0.05))
    .force('y', d3.forceY().strength(0.3).y(d => 80 + d.depth * 70))
    .force('collision', d3.forceCollide(20))
    .on('tick', ticked);
}

function ticked() {
  linkGroup.selectAll('line')
    .attr('x1', d => d.source.x)
    .attr('y1', d => d.source.y)
    .attr('x2', d => d.target.x)
    .attr('y2', d => d.target.y);

  nodeGroup.selectAll('.node-g')
    .attr('transform', d => `translate(${d.x},${d.y})`);
}

export function renderDag(graphData, selectedId) {
  const nodes = graphData.node;
  const edges = graphData.edge;
  const frontierSet = new Set(graphData.frontier_id);

  if (nodes.length === 0) {
    document.getElementById('dag-empty').style.display = 'block';
    return;
  }
  document.getElementById('dag-empty').style.display = 'none';

  // Links
  const links = linkGroup.selectAll('line').data(edges, d => d.source + '-' + d.target);
  links.exit().remove();
  links.enter().append('line')
    .attr('class', 'edge-line')
    .attr('marker-end', 'url(#arrowhead)');

  // Nodes
  const nodeGs = nodeGroup.selectAll('.node-g').data(nodes, d => d.id);
  nodeGs.exit().remove();

  const enter = nodeGs.enter().append('g').attr('class', 'node-g');

  enter.append('circle')
    .attr('class', 'frontier-ring')
    .attr('r', d => frontierSet.has(d.id) ? 14 : 0);

  enter.append('circle')
    .attr('class', 'selected-ring')
    .attr('r', 0);

  enter.append('circle')
    .attr('class', 'node-circle')
    .attr('r', 8)
    .attr('fill', d => statusColor(d.status))
    .on('click', (e, d) => onNodeClick && onNodeClick(d.id));

  enter.append('text')
    .attr('class', 'node-label')
    .attr('dy', 22)
    .text(d => shortCid(d.id));

  // Update frontier rings
  nodeGroup.selectAll('.frontier-ring')
    .attr('r', d => frontierSet.has(d.id) ? 14 : 0);

  // Restart simulation
  simulation.nodes(nodes);
  simulation.force('link').links(edges.map(e => ({
    source: e.source,
    target: e.target,
  })));
  simulation.alpha(0.5).restart();

  updateSelection(selectedId);
}

export function updateSelection(selectedId, ancestorPath) {
  const pathSet = new Set(ancestorPath || []);

  nodeGroup.selectAll('.selected-ring')
    .attr('r', d => d.id === selectedId ? 16 : 0);

  // Highlight ancestor path
  linkGroup.selectAll('line')
    .classed('path-highlight', d => {
      const src = typeof d.source === 'object' ? d.source.id : d.source;
      const tgt = typeof d.target === 'object' ? d.target.id : d.target;
      return pathSet.has(src) && pathSet.has(tgt);
    });

  nodeGroup.selectAll('.node-circle')
    .attr('opacity', d => {
      if (!selectedId) return 1;
      if (d.id === selectedId || pathSet.has(d.id)) return 1;
      return 0.3;
    });
}

export function resetHighlight() {
  nodeGroup.selectAll('.node-circle').attr('opacity', 1);
  linkGroup.selectAll('line').classed('path-highlight', false);
  nodeGroup.selectAll('.selected-ring').attr('r', 0);
}
