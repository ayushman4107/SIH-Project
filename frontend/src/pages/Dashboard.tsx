import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getReport } from '../api/client';
import type { AssuranceReport } from '../api/types';
import DispositionBadge from '../components/DispositionBadge';
import StatCard from '../components/StatCard';
import {
  Database, GitMerge, ListChecks, AlertTriangle, FileText,
  Calendar, Box, Tag, Users, Network, Cpu,
} from 'lucide-react';

export default function Dashboard() {
  const { reportId } = useParams();
  const navigate = useNavigate();
  const [report, setReport] = useState<AssuranceReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

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
  const f2 = report.pillars.F2_model_integrity;
  const f3 = report.pillars.F3_inference_provenance;
  const f4 = report.pillars.F4_distribution_shift;
  const sybil = f1.sybil_collusion;
  const projector = f4.evidence.synthetic_projector;
  const activationClustering = f2.evidence.activation_clustering;

  const dispositionColors: Record<string, string> = {
    accept: 'border-l-emerald-500',
    review: 'border-l-amber-400',
    quarantine: 'border-l-red-500',
    inconclusive: 'border-l-gray-400',
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white border border-border rounded-xl p-6 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight mb-2">Assurance Report</h1>
            <div className="flex flex-wrap items-center gap-4 text-sm text-muted">
              <span className="flex items-center gap-1"><Tag className="w-4 h-4" /> {report.report_metadata.report_id}</span>
              <span className="flex items-center gap-1"><Calendar className="w-4 h-4" /> {new Date(report.report_metadata.timestamp).toLocaleString()}</span>
              <span className="flex items-center gap-1"><Box className="w-4 h-4" /> {report.report_metadata.model_name}</span>
            </div>
          </div>
          <div className="flex flex-col items-end">
            <DispositionBadge disposition={report.disposition.overall} size="lg" className="mb-2 shadow-sm" />
          </div>
        </div>
        <div className="mt-4 p-4 bg-gray-50 rounded-lg border border-gray-100">
          <p className="text-gray-800 text-sm leading-relaxed">{report.disposition.reasoning}</p>
        </div>
      </div>

      {/* Alert banners for new critical detections */}
      {sybil && sybil.syndicates.length > 0 && (
        <div className={`flex items-start gap-3 p-4 rounded-lg border-l-4 bg-red-50 border-red-400 border border-red-200 shadow-sm`}>
          <Network className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="text-sm font-bold text-red-900 mb-1">
              Sybil Collusion Detected — {sybil.syndicates.length} Syndicate{sybil.syndicates.length > 1 ? 's' : ''}
            </h3>
            <p className="text-xs text-red-700">
              {sybil.syndicates.map(s => s.members.join(' + ')).join('; ')} — coordinated poisoning suspected.
              Confidence: {(sybil.syndicates[0].calibrated_confidence * 100).toFixed(1)}%.
              See F1 Findings for details.
            </p>
          </div>
        </div>
      )}

      {activationClustering && activationClustering.suspicious_classes.length > 0 && (
        <div className="flex items-start gap-3 p-4 rounded-lg border-l-4 bg-amber-50 border-amber-400 border border-amber-200 shadow-sm">
          <Cpu className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="text-sm font-bold text-amber-900 mb-1">
              Activation Clustering Anomaly — Class{activationClustering.suspicious_classes.length > 1 ? 'es' : ''} {activationClustering.suspicious_classes.join(', ')}
            </h3>
            <p className="text-xs text-amber-700">
              Bimodal split in penultimate layer suggests a targeted backdoor. See F2 Model Integrity for full analysis.
            </p>
          </div>
        </div>
      )}

      {/* Pillar Cards */}
      <h2 className="text-xl font-semibold mb-4 mt-8">Assurance Pillars</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <StatCard
          title="F1: Data Integrity"
          value={f1.total_findings}
          subtitle={`Status: ${f1.status}`}
          icon={<Database />}
          onClick={() => navigate(`/report/${reportId}/findings`)}
        />
        <StatCard
          title="F2: Model Integrity"
          value={`${(f2.confidence * 100).toFixed(1)}%`}
          subtitle={`Status: ${f2.status}`}
          icon={<GitMerge />}
          onClick={() => navigate(`/report/${reportId}/model-integrity`)}
        />
        <StatCard
          title="F3: Provenance"
          value={f3.hmac_status}
          subtitle={`Status: ${f3.status}`}
          icon={<ListChecks />}
          onClick={() => navigate(`/report/${reportId}/ledger`)}
        />
        <StatCard
          title="F4: Distribution Shift"
          value={f4.ood_score.toFixed(3)}
          subtitle={`Status: ${f4.status}`}
          icon={<AlertTriangle />}
          onClick={() => navigate(`/report/${reportId}/distribution-shift`)}
        />
        <StatCard
          title="F5: Coverage"
          value={report.coverage_statement.supported_attacks.length}
          subtitle={`Framework: ${report.coverage_statement.framework} v${report.coverage_statement.version}`}
          icon={<FileText />}
          onClick={() => navigate(`/report/${reportId}/coverage`)}
        />
      </div>

      {/* Contributor Risk Summary */}
      {f1.contributor_risk_aggregation.length > 0 && (
        <div className="mt-8">
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <Users className="w-5 h-5 text-purple-600" />
            Contributor Risk Summary
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {f1.contributor_risk_aggregation.map(c => {
              const disposition = c.recommendation as string;
              const borderColor = dispositionColors[disposition] ?? 'border-l-gray-400';
              const riskColor = c.risk_score >= 0.9 ? 'text-red-600' : c.risk_score >= 0.75 ? 'text-amber-600' : 'text-emerald-600';
              return (
                <div
                  key={c.source_id}
                  className={`bg-white border border-border rounded-lg p-4 shadow-sm border-l-4 ${borderColor}`}
                >
                  <div className="flex justify-between items-start mb-3">
                    <span className="font-bold text-gray-900">{c.source_id}</span>
                    <DispositionBadge disposition={c.recommendation as any} size="sm" />
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <span className="text-xs text-gray-500 block">Contributed</span>
                      <span className="font-medium">{c.samples_contributed.toLocaleString()} samples</span>
                    </div>
                    <div>
                      <span className="text-xs text-gray-500 block">Problematic</span>
                      <span className="font-medium text-red-600">{c.problematic_samples}</span>
                    </div>
                    <div className="col-span-2">
                      <span className="text-xs text-gray-500 block mb-1">Risk Score</span>
                      <div className="flex items-center gap-2">
                        <div className="flex-1 bg-gray-100 rounded-full h-1.5">
                          <div
                            className={`h-1.5 rounded-full ${c.risk_score >= 0.9 ? 'bg-red-500' : c.risk_score >= 0.75 ? 'bg-amber-400' : 'bg-emerald-500'}`}
                            style={{ width: `${c.risk_score * 100}%` }}
                          />
                        </div>
                        <span className={`text-sm font-bold ${riskColor}`}>{(c.risk_score * 100).toFixed(0)}%</span>
                      </div>
                    </div>
                  </div>
                  {sybil && sybil.syndicates.some(s => s.members.includes(c.source_id)) && (
                    <div className="mt-2 flex items-center gap-1 text-xs text-red-700 font-semibold bg-red-50 border border-red-200 rounded px-2 py-1">
                      <Network className="w-3 h-3" /> Syndicate member
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Synthetic Projector quick summary */}
      {projector && (
        <div className="mt-4">
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-500" />
            Synthetic Drift Analysis (F4)
          </h2>
          <div className={`bg-white border border-border rounded-lg p-5 shadow-sm border-l-4 ${
            projector.finding_type === 'ORTHOGONAL_DRIFT_ANOMALY' ? 'border-l-amber-400' : 'border-l-emerald-400'
          }`}>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <span className={`inline-block text-xs font-bold uppercase px-2 py-1 rounded mb-1 ${
                  projector.finding_type === 'ORTHOGONAL_DRIFT_ANOMALY'
                    ? 'bg-amber-100 text-amber-800'
                    : 'bg-emerald-100 text-emerald-800'
                }`}>
                  {projector.finding_type.replace(/_/g, ' ')}
                </span>
                <p className="text-sm text-gray-600 mt-1">{projector.interpretation}</p>
              </div>
              <div className="flex gap-6 text-center flex-shrink-0">
                <div>
                  <div className="text-2xl font-bold text-gray-900">{(projector.orthogonality_ratio * 100).toFixed(1)}%</div>
                  <div className="text-xs text-gray-500">Orthogonality</div>
                </div>
                <div>
                  <div className="text-2xl font-bold text-gray-900">{projector.total_displacement.toFixed(2)}</div>
                  <div className="text-xs text-gray-500">Displacement</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* F5 Governance Summary */}
      <div className="mt-4">
        <h2 className="text-xl font-semibold mb-4">F5: Governance Aggregation</h2>
        <div className="bg-white border border-border rounded-lg p-5 shadow-sm">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            {report.pillars.F5_aggregation_and_governance.pillar_dispositions.map(p => (
              <div key={p.pillar} className="text-center p-3 bg-gray-50 rounded-lg border border-gray-100">
                <div className="text-xs font-semibold text-gray-500 uppercase mb-1">{p.pillar}</div>
                <DispositionBadge disposition={p.disposition} size="sm" className="justify-center" />
                <div className="text-xs text-gray-400 mt-1">{p.count} findings</div>
              </div>
            ))}
          </div>
          <p className="text-sm text-gray-700 leading-relaxed italic border-t border-gray-100 pt-4">
            {report.pillars.F5_aggregation_and_governance.analyst_summary}
          </p>
        </div>
      </div>
    </div>
  );
}
