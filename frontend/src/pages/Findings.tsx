import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { getReport } from '../api/client';
import type { AssuranceReport, SampleFinding } from '../api/types';
import DispositionBadge from '../components/DispositionBadge';
import EvidenceViewer from '../components/EvidenceViewer';
import { ChevronDown, ChevronUp, Network, TrendingUp, Users } from 'lucide-react';

export default function Findings() {
  const { reportId } = useParams();
  const [report, setReport] = useState<AssuranceReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [filterType, setFilterType] = useState<string>('all');
  const [filterSeverity, setFilterSeverity] = useState<string>('all');
  const [expandedRow, setExpandedRow] = useState<string | null>(null);

  useEffect(() => {
    if (!reportId) return;
    setLoading(true);
    getReport(reportId)
      .then(data => setReport(data))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [reportId]);

  if (loading) return <div className="text-muted text-center py-12">Loading report...</div>;
  if (error) return <div className="text-red-500 text-center py-12">Error: {error}</div>;
  if (!report) return <div className="text-muted text-center py-12">Report not found</div>;

  const f1 = report.pillars.F1_data_integrity;
  const canonical = report.canonical_findings;
  const sybil = f1.sybil_collusion;
  const influenceFns = f1.influence_functions;

  const filteredFindings = f1.sample_findings.filter(finding => {
    const typeMatch = filterType === 'all' || finding.type === filterType;
    const severityMatch = filterSeverity === 'all' || finding.severity === filterSeverity;
    return typeMatch && severityMatch;
  });

  const toggleRow = (id: string) => {
    setExpandedRow(expandedRow === id ? null : id);
  };

  const severityColors: Record<string, string> = {
    critical: 'bg-purple-100 text-purple-900',
    high: 'bg-red-100 text-red-800',
    medium: 'bg-yellow-100 text-yellow-800',
    low: 'bg-green-100 text-green-800',
  };

  return (
    <div className="space-y-6 pb-12">
      <div className="flex justify-between items-end border-b border-border pb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight mb-1">F1: Data Integrity</h1>
          <p className="text-sm text-muted">
            Status: <span className="font-semibold text-gray-900">{f1.status}</span> | Total Findings: {f1.total_findings}
          </p>
        </div>
      </div>

      {/* Sybil Collusion Section */}
      {sybil && sybil.syndicates.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <Network className="w-5 h-5 text-red-500" />
            Sybil Collusion Syndicates
            <span className="ml-1 px-2 py-0.5 bg-red-100 text-red-800 text-xs font-bold rounded-full">
              {sybil.syndicates.length} detected
            </span>
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {sybil.syndicates.map((syndicate, idx) => (
              <div
                key={idx}
                className="bg-white border border-red-200 rounded-lg p-5 shadow-sm relative overflow-hidden"
              >
                <div className="absolute top-0 left-0 w-1.5 h-full bg-red-500" />
                <div className="flex justify-between items-start mb-3">
                  <div>
                    <span className="text-xs font-semibold text-red-700 uppercase tracking-wider">
                      Syndicate {idx + 1}
                    </span>
                    <div className="flex flex-wrap gap-2 mt-1">
                      {syndicate.members.map(m => (
                        <span
                          key={m}
                          className="inline-flex items-center gap-1 px-2 py-0.5 bg-red-50 border border-red-200 rounded text-xs font-mono text-red-900"
                        >
                          <Users className="w-3 h-3" />{m}
                        </span>
                      ))}
                    </div>
                  </div>
                  <span className={`px-2 py-1 rounded text-xs font-bold ${
                    syndicate.disposition === 'QUARANTINE'
                      ? 'bg-red-100 text-red-800'
                      : 'bg-yellow-100 text-yellow-800'
                  }`}>
                    {syndicate.disposition}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-3 mt-3 pt-3 border-t border-gray-100">
                  <div>
                    <span className="text-xs text-gray-500 block">Edge Density</span>
                    <div className="flex items-center gap-2 mt-1">
                      <div className="flex-1 bg-gray-100 rounded-full h-1.5">
                        <div
                          className="h-1.5 rounded-full bg-red-500"
                          style={{ width: `${syndicate.internal_edge_density * 100}%` }}
                        />
                      </div>
                      <span className="text-sm font-bold text-gray-800">
                        {(syndicate.internal_edge_density * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                  <div>
                    <span className="text-xs text-gray-500 block">Confidence</span>
                    <div className="flex items-center gap-2 mt-1">
                      <div className="flex-1 bg-gray-100 rounded-full h-1.5">
                        <div
                          className="h-1.5 rounded-full bg-purple-500"
                          style={{ width: `${syndicate.calibrated_confidence * 100}%` }}
                        />
                      </div>
                      <span className="text-sm font-bold text-gray-800">
                        {(syndicate.calibrated_confidence * 100).toFixed(1)}%
                      </span>
                    </div>
                  </div>
                </div>
                <p className="text-xs text-gray-500 mt-3">
                  Method: Marginal-Excess Binomial Gate + Cross-Cluster Permutation Test (BH-corrected)
                </p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Influence Functions Top Suspects */}
      {influenceFns && influenceFns.top_suspects.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-purple-600" />
            Influence Functions — Top Poisoning Suspects
          </h2>
          <div className="bg-white border border-border rounded-lg overflow-hidden shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-gray-700 uppercase bg-purple-50 border-b border-border">
                  <tr>
                    <th className="px-4 py-3">Rank</th>
                    <th className="px-4 py-3">Sample ID</th>
                    <th className="px-4 py-3">Contributor</th>
                    {influenceFns.top_suspects[0].class_id !== undefined && (
                      <th className="px-4 py-3">Class</th>
                    )}
                    <th className="px-4 py-3">Influence Score</th>
                  </tr>
                </thead>
                <tbody>
                  {influenceFns.top_suspects.map((s, rank) => (
                    <tr key={s.sample_id} className="border-b border-border hover:bg-gray-50">
                      <td className="px-4 py-3 text-gray-400 font-mono text-xs">#{rank + 1}</td>
                      <td className="px-4 py-3 font-mono text-xs text-gray-800">{s.sample_id}</td>
                      <td className="px-4 py-3 text-gray-700">{s.source_id}</td>
                      {s.class_id !== undefined && (
                        <td className="px-4 py-3">
                          <span className="px-2 py-0.5 bg-blue-100 text-blue-800 rounded text-xs font-mono">
                            class {s.class_id}
                          </span>
                        </td>
                      )}
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="w-24 bg-gray-100 rounded-full h-1.5">
                            <div
                              className="h-1.5 rounded-full bg-purple-500"
                              style={{ width: `${s.influence_score * 100}%` }}
                            />
                          </div>
                          <span className="text-sm font-bold text-purple-700">
                            {s.influence_score.toFixed(3)}
                          </span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="p-3 bg-gray-50 border-t border-border">
              <p className="text-xs text-gray-500">Method: <span className="font-mono">{influenceFns.method}</span></p>
            </div>
          </div>
        </section>
      )}

      {/* Filters */}
      <div className="flex gap-4 p-4 bg-gray-50 rounded-lg border border-border">
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Type</label>
          <select
            className="text-sm border-gray-300 rounded-md bg-white border px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-purple-500"
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
          >
            <option value="all">All Types ({canonical.total_count})</option>
            {Object.entries(canonical.by_type).map(([key, count]) => (
              <option key={key} value={key}>{key} ({count})</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-gray-700 mb-1">Severity</label>
          <select
            className="text-sm border-gray-300 rounded-md bg-white border px-3 py-1.5 focus:outline-none focus:ring-1 focus:ring-purple-500"
            value={filterSeverity}
            onChange={(e) => setFilterSeverity(e.target.value)}
          >
            <option value="all">All Severities</option>
            {Object.entries(canonical.by_severity).map(([key, count]) => (
              <option key={key} value={key}>{key} ({count})</option>
            ))}
          </select>
        </div>
      </div>

      {/* Sample Findings Table */}
      <div className="bg-white border border-border rounded-lg overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs text-gray-700 uppercase bg-gray-50 border-b border-border">
              <tr>
                <th className="px-4 py-3 w-8"></th>
                <th className="px-4 py-3">Finding ID</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Severity</th>
                <th className="px-4 py-3">Confidence</th>
                <th className="px-4 py-3">Disposition</th>
              </tr>
            </thead>
            <tbody>
              {filteredFindings.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-muted">No findings match the current filters.</td>
                </tr>
              ) : (
                filteredFindings.map((finding: SampleFinding) => (
                  <React.Fragment key={finding.finding_id}>
                    <tr
                      className={`border-b border-border hover:bg-gray-50 cursor-pointer ${expandedRow === finding.finding_id ? 'bg-gray-50' : ''}`}
                      onClick={() => toggleRow(finding.finding_id)}
                    >
                      <td className="px-4 py-3 text-gray-400">
                        {expandedRow === finding.finding_id ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">{finding.finding_id.split('-')[0]}...</td>
                      <td className="px-4 py-3">
                        <span className="flex items-center gap-1">
                          {finding.type === 'sybil_collusion' && <Network className="w-3.5 h-3.5 text-red-500" />}
                          {finding.type}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-1 rounded text-xs font-medium ${severityColors[finding.severity] ?? 'bg-gray-100 text-gray-700'}`}>
                          {finding.severity}
                        </span>
                      </td>
                      <td className="px-4 py-3">{(finding.confidence * 100).toFixed(0)}%</td>
                      <td className="px-4 py-3">
                        <DispositionBadge disposition={finding.disposition} size="sm" />
                      </td>
                    </tr>
                    {expandedRow === finding.finding_id && (
                      <tr className="bg-gray-50 border-b border-border">
                        <td colSpan={6} className="px-4 py-4 px-12">
                          <div className="mb-4 flex flex-wrap gap-4">
                            <div>
                              <span className="block text-xs text-gray-500 font-medium">Recommended Action</span>
                              <span className="text-sm font-medium">{finding.recommended_action}</span>
                            </div>
                            {finding.sample_id && (
                              <div>
                                <span className="block text-xs text-gray-500 font-medium">Sample ID</span>
                                <span className="text-sm font-mono">{finding.sample_id}</span>
                              </div>
                            )}
                            {finding.sample_ids && finding.sample_ids.length > 0 && (
                              <div>
                                <span className="block text-xs text-gray-500 font-medium">Sample IDs</span>
                                <span className="text-sm font-mono">{finding.sample_ids.length} samples</span>
                              </div>
                            )}
                          </div>

                          <h4 className="text-xs font-semibold text-gray-700 uppercase mb-2">Evidence</h4>
                          <EvidenceViewer evidence={finding.evidence} />
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
