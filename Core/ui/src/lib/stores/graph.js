import { writable } from 'svelte/store';

// ============================================================
// Graph Data — 17 nodes from nodes.yaml
// ============================================================

export const nodes = writable([
  { id: 'quantum_mechanics', label: 'Quantum\nMechanics', domain: 'physics' },
  { id: 'relativity', label: 'Relativity', domain: 'physics' },
  { id: 'thermodynamics', label: 'Thermodynamics', domain: 'physics' },
  { id: 'information_theory', label: 'Information\nTheory', domain: 'computer_science' },
  { id: 'computability', label: 'Computability', domain: 'computer_science' },
  { id: 'emergence', label: 'Emergence', domain: 'biology' },
  { id: 'evolution', label: 'Evolution', domain: 'biology' },
  { id: 'stellar_dynamics', label: 'Stellar\nDynamics', domain: 'astronomy' },
  { id: 'cosmology', label: 'Cosmology', domain: 'astronomy' },
  { id: 'chemical_bonding', label: 'Chemical\nBonding', domain: 'chemistry' },
  { id: 'reaction_kinetics', label: 'Reaction\nKinetics', domain: 'chemistry' },
  { id: 'topology', label: 'Topology', domain: 'mathematics' },
  { id: 'number_theory', label: 'Number\nTheory', domain: 'mathematics' },
  { id: 'consciousness', label: 'Consciousness', domain: 'philosophy' },
  { id: 'epistemology', label: 'Epistemology', domain: 'philosophy' },
  { id: 'recursion', label: 'Recursion', domain: 'computer_science' },
  { id: 'signal_processing', label: 'Signal\nProcessing', domain: 'physics' },
]);

export const edges = writable([
  { source: 'quantum_mechanics', target: 'information_theory', weight: 0.7 },
  { source: 'quantum_mechanics', target: 'relativity', weight: 0.6 },
  { source: 'quantum_mechanics', target: 'thermodynamics', weight: 0.5 },
  { source: 'information_theory', target: 'computability', weight: 0.8 },
  { source: 'information_theory', target: 'signal_processing', weight: 0.7 },
  { source: 'emergence', target: 'evolution', weight: 0.75 },
  { source: 'emergence', target: 'consciousness', weight: 0.6 },
  { source: 'emergence', target: 'recursion', weight: 0.55 },
  { source: 'stellar_dynamics', target: 'cosmology', weight: 0.85 },
  { source: 'stellar_dynamics', target: 'thermodynamics', weight: 0.5 },
  { source: 'chemical_bonding', target: 'reaction_kinetics', weight: 0.8 },
  { source: 'topology', target: 'number_theory', weight: 0.7 },
  { source: 'topology', target: 'recursion', weight: 0.45 },
  { source: 'consciousness', target: 'epistemology', weight: 0.65 },
  { source: 'consciousness', target: 'recursion', weight: 0.7 },
  { source: 'recursion', target: 'computability', weight: 0.8 },
  { source: 'epistemology', target: 'information_theory', weight: 0.5 },
  { source: 'cosmology', target: 'quantum_mechanics', weight: 0.6 },
]);

// Domain color mapping (matches GraphCanvas coloring)
export const domainColors = {
  physics: '#4f7bff',        // accent (blue)
  computer_science: '#00e5b0', // accent2 (teal)
  biology: '#4caf7d',         // green
  astronomy: '#9c6fe4',       // purple
  chemistry: '#e8a44a',       // amber
  mathematics: '#e8c87a',     // gold
  philosophy: '#e06b6b',      // soft red
};
