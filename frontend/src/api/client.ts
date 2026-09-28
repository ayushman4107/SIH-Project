import type { AssuranceReport } from './types';

const API_BASE = '/api';

export async function listRuns(): Promise<string[]> {
  const response = await fetch(`${API_BASE}/runs`);
  if (!response.ok) {
    throw new Error(`Failed to fetch runs: ${response.statusText}`);
  }
  return response.json();
}

export async function getReport(reportId: string): Promise<AssuranceReport> {
  const response = await fetch(`${API_BASE}/runs/${reportId}`);
  if (!response.ok) {
    throw new Error(`Failed to fetch report: ${response.statusText}`);
  }
  return response.json();
}
