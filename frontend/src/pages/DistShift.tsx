import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { getReport } from '../api/client';
import type { AssuranceReport } from '../api/types';
import DispositionBadge from '../components/DispositionBadge';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { AlertTriangle, Compass } from 'lucide-react';

export default function DistShift() {
  const { reportId } = useParams();
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

  const f4 = report.pillars.F4_distribution_shift;
  const { mahalanobis_distances, predictive_entropy_ratio, synthetic_projector } = f4.evidence;

  const chartData = [
    {
      name: 'Mean',
      Reference: mahalanobis_distances.reference_mean,
      Submitted: mahalanobis_distances.mean,
    },
    {
      name: '95th Percentile',
      Reference: mahalanobis_distances.reference_95th_percentile,
      Submitted: mahalanobis_distances["95th_percentile"],
    }
  ];

  const limitations = Array.isArray(f4.limitations) ? f4.limitations : [f4.limitations];

  return (
    <div className="space-y-6 pb-12">
      <div className="flex flex-col md:flex-row md:items-start justify-between gap-4 border-b border-border pb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight mb-1">F4: Distribution Shift</h1>
          <p className="text-sm text-muted">Status: <span className="font-semibold text-gray-900">{f4.status}</span></p>
        </div>
        <div className="flex flex-col items-end">
          <DispositionBadge disposition={f4.disposition} />
        </div>
      </div>

      {f4.recommendation && (
        <div className="bg-white p-5 rounded-lg border border-border shadow-sm flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
          <div>
            <h3 className="text-sm font-semibold text-gray-900 mb-1">Recommendation</h3>
            <p className="text-sm text-gray-700">{f4.recommendation}</p>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* OOD Score gauge */}
        <div className="bg-white p-5 rounded-lg border border-border shadow-sm flex flex-col items-center justify-center">
          <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-2 self-start w-full text-center">OOD Score</h3>

          <div className="relative w-48 h-48 flex items-center justify-center my-4">
            <svg className="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
              <circle cx="50" cy="50" r="40" stroke="#f3f4f6" strokeWidth="12" fill="none" />
              <circle
                cx="50" cy="50" r="40"
                stroke={f4.ood_score > f4.threshold ? "#ef4444" : "#10b981"}
                strokeWidth="12" fill="none"
                strokeDasharray={`${Math.min(f4.ood_score * 251.2, 251.2)} 251.2`}
                strokeLinecap="round"
                className="transition-all duration-1000 ease-out"
              />
            </svg>
            <div className="absolute flex flex-col items-center">
              <span className="text-3xl font-bold">{f4.ood_score.toFixed(3)}</span>
              <span className="text-xs text-gray-500 mt-1">Threshold: {f4.threshold.toFixed(2)}</span>
            </div>
          </div>

          <p className="text-sm text-gray-600 text-center mt-2 px-4">{f4.explanation}</p>
        </div>

        {/* Predictive Entropy */}
        <div className="bg-white p-5 rounded-lg border border-border shadow-sm flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-4">Predictive Entropy</h3>
            <div className="space-y-4">
              <div className="flex justify-between items-center pb-3 border-b border-gray-100">
                <span className="text-sm text-gray-600">Reference Entropy</span>
                <span className="text-lg font-medium">{predictive_entropy_ratio.reference_entropy.toFixed(4)}</span>
              </div>
              <div className="flex justify-between items-center pb-3 border-b border-gray-100">
                <span className="text-sm text-gray-600">Submitted Entropy</span>
                <span className="text-lg font-medium">{predictive_entropy_ratio.submitted_entropy.toFixed(4)}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-600">Ratio</span>
                <span className={`text-xl font-bold ${predictive_entropy_ratio.ratio > 1.2 ? 'text-red-600' : 'text-green-600'}`}>
                  {predictive_entropy_ratio.ratio.toFixed(3)}
                </span>
              </div>
            </div>
          </div>
          <div className="mt-6 bg-gray-50 p-4 rounded-md border border-gray-100">
            <p className="text-sm text-gray-700 italic">{predictive_entropy_ratio.interpretation}</p>
          </div>
        </div>
      </div>

      {/* Synthetic Drift Projector */}
      {synthetic_projector && (
        <section>
          <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <Compass className="w-5 h-5 text-indigo-600" />
            Synthetic Drift Projector
            <span className={`ml-1 px-2 py-0.5 text-xs font-bold rounded-full ${
              synthetic_projector.finding_type === 'ORTHOGONAL_DRIFT_ANOMALY'
                ? 'bg-amber-100 text-amber-800'
                : 'bg-emerald-100 text-emerald-800'
            }`}>
              {synthetic_projector.finding_type.replace(/_/g, ' ')}
            </span>
          </h2>
          <div className={`bg-white border border-border rounded-lg p-6 shadow-sm border-l-4 ${
            synthetic_projector.finding_type === 'ORTHOGONAL_DRIFT_ANOMALY'
              ? 'border-l-amber-400'
              : 'border-l-emerald-400'
          }`}>
            <div className="flex flex-col md:flex-row gap-6">
              {/* Orthogonality ratio dial */}
              <div className="flex flex-col items-center justify-center min-w-[160px]">
                <div className="relative w-36 h-36">
                  <svg className="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
                    <circle cx="50" cy="50" r="38" stroke="#f3f4f6" strokeWidth="10" fill="none" />
                    <circle
                      cx="50" cy="50" r="38"
                      stroke={synthetic_projector.orthogonality_ratio >= (synthetic_projector.ortho_threshold ?? 0.40) ? "#f59e0b" : "#10b981"}
                      strokeWidth="10" fill="none"
                      strokeDasharray={`${synthetic_projector.orthogonality_ratio * 238.76} 238.76`}
                      strokeLinecap="round"
                      className="transition-all duration-1000 ease-out"
                    />
                  </svg>
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="text-2xl font-bold text-gray-900">
                      {(synthetic_projector.orthogonality_ratio * 100).toFixed(1)}%
                    </span>
                    <span className="text-[10px] text-gray-500 mt-1">Orthogonality</span>
                  </div>
                </div>
                <div className="text-xs text-gray-500 mt-2 text-center">
                  Threshold: {((synthetic_projector.ortho_threshold ?? 0.40) * 100).toFixed(0)}%
                </div>
              </div>

              {/* Metrics */}
              <div className="flex-1">
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 mb-4">
                  <div className="bg-gray-50 rounded-lg p-3 border border-gray-100 text-center">
                    <div className="text-xl font-bold text-gray-900">{synthetic_projector.total_displacement.toFixed(3)}</div>
                    <div className="text-xs text-gray-500 mt-1">Total Displacement</div>
                  </div>
                  {synthetic_projector.manifold_basis_components !== undefined && (
                    <div className="bg-gray-50 rounded-lg p-3 border border-gray-100 text-center">
                      <div className="text-xl font-bold text-gray-900">{synthetic_projector.manifold_basis_components}</div>
                      <div className="text-xs text-gray-500 mt-1">Manifold Basis (k)</div>
                    </div>
                  )}
                  {synthetic_projector.variance_threshold !== undefined && (
                    <div className="bg-gray-50 rounded-lg p-3 border border-gray-100 text-center">
                      <div className="text-xl font-bold text-gray-900">{(synthetic_projector.variance_threshold * 100).toFixed(0)}%</div>
                      <div className="text-xs text-gray-500 mt-1">Variance Retained</div>
                    </div>
                  )}
                </div>

                {/* Visual bar decomposition */}
                <div className="mb-4">
                  <div className="flex justify-between text-xs text-gray-500 mb-1">
                    <span>Natural displacement</span>
                    <span>Orthogonal (unnatural)</span>
                  </div>
                  <div className="w-full h-4 bg-gray-100 rounded-full overflow-hidden flex">
                    <div
                      className="h-full bg-emerald-400 transition-all duration-1000"
                      style={{ width: `${(1 - synthetic_projector.orthogonality_ratio) * 100}%` }}
                    />
                    <div
                      className="h-full bg-amber-400 transition-all duration-1000"
                      style={{ width: `${synthetic_projector.orthogonality_ratio * 100}%` }}
                    />
                  </div>
                  <div className="flex gap-4 mt-2 text-xs">
                    <span className="flex items-center gap-1"><span className="inline-block w-3 h-2 rounded-sm bg-emerald-400" /> Natural ({((1 - synthetic_projector.orthogonality_ratio) * 100).toFixed(1)}%)</span>
                    <span className="flex items-center gap-1"><span className="inline-block w-3 h-2 rounded-sm bg-amber-400" /> Orthogonal ({(synthetic_projector.orthogonality_ratio * 100).toFixed(1)}%)</span>
                  </div>
                </div>

                <div className="flex items-center gap-2 mt-2">
                  <span className="text-sm font-semibold text-gray-700">Disposition:</span>
                  <span className={`px-2 py-1 rounded text-xs font-bold ${
                    synthetic_projector.disposition === 'QUARANTINE'
                      ? 'bg-red-100 text-red-800'
                      : 'bg-yellow-100 text-yellow-800'
                  }`}>
                    {synthetic_projector.disposition}
                  </span>
                </div>
              </div>
            </div>

            {synthetic_projector.interpretation && (
              <div className="mt-5 p-4 bg-gray-50 rounded-lg border border-gray-100">
                <p className="text-sm text-gray-700 italic">{synthetic_projector.interpretation}</p>
              </div>
            )}

            <div className="mt-4 text-xs text-gray-500 space-y-1">
              <p>
                <span className="font-semibold">How it works:</span> The natural drift manifold U<sub>k</sub> is
                fit offline via SVD on displacement covariance from physical perturbations (brightness, blur, noise).
                Incoming OOD embeddings are then projected onto U<sub>k</sub>; the residual orthogonal component
                indicates synthetic or adversarial manipulation not explained by natural physics.
              </p>
            </div>
          </div>
        </section>
      )}

      {/* Mahalanobis Distribution Chart */}
      <div className="bg-white p-5 rounded-lg border border-border shadow-sm">
        <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-6">Mahalanobis Distance Distribution</h3>
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }} barGap={8}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
              <XAxis dataKey="name" stroke="#9ca3af" />
              <YAxis stroke="#9ca3af" />
              <Tooltip
                cursor={{ fill: '#f3f4f6' }}
                contentStyle={{ borderRadius: '8px', border: '1px solid #e5e7eb', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)' }}
              />
              <Legend wrapperStyle={{ paddingTop: '20px' }} />
              <Bar dataKey="Reference" fill="#9ca3af" radius={[4, 4, 0, 0]} maxBarSize={60} />
              <Bar dataKey="Submitted" fill="#f59e0b" radius={[4, 4, 0, 0]} maxBarSize={60} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Limitations */}
      {limitations.length > 0 && (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
          <h3 className="text-xs font-semibold text-gray-600 uppercase tracking-wider mb-2">Limitations</h3>
          <ul className="space-y-1">
            {limitations.map((lim, i) => (
              <li key={i} className="text-xs text-gray-600 flex gap-2">
                <span className="flex-shrink-0 text-gray-400">•</span>
                {lim}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
