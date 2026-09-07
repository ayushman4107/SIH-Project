import type { AssuranceReport, AuditLog } from './types';

// Depending on the Vite proxy or production setup, this could be adjusted.
// With vite.config.ts proxy, we just use relative URLs.
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

export async function getLedger(reportId: string): Promise<AuditLog> {
  const response = await fetch(`${API_BASE}/runs/${reportId}/ledger`);
  if (!response.ok) {
    throw new Error(`Failed to fetch ledger: ${response.statusText}`);
  }
  return response.json();
}
