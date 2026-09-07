import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { getReport } from '../api/client';
import type { AssuranceReport } from '../api/types';
import VerificationStatus from '../components/VerificationStatus';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { GitMerge, Activity, Layers, Zap, TrendingUp } from 'lucide-react';

export default function ModelIntegrity() {
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

  const f2 = report.pillars.F2_model_integrity;
  const { per_layer_analysis, leave_one_out_calibration, nextafter_max_clean_threshold } = f2.evidence;
  const activationClustering = f2.evidence.activation_clustering;
  const gradientClustering = f2.evidence.gradient_clustering;
  const influenceFns = f2.evidence.influence_functions;

  const layerData = per_layer_analysis.map((layer, index) => ({
    name: layer.layer_name.split('.').pop() || `Layer ${index}`,
    distance: layer.wasserstein_distance,
    threshold: layer.threshold,
    status: layer.status
  }));

  const severityColors: Record<string, string> = {
    critical: 'bg-purple-100 text-purple-900 border-purple-300',
    high: 'bg-red-100 text-red-800 border-red-200',
    medium: 'bg-yellow-100 text-yellow-800 border-yellow-200',
    low: 'bg-green-100 text-green-800 border-green-200',
  };

  return (
    <div className="space-y-6 pb-12">
      <div className="flex flex-col md:flex-row md:items-start justify-between gap-4 border-b border-border pb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight mb-1">F2: Model Integrity</h1>
          <p className="text-sm text-muted">
            Status: <span className="font-semibold text-gray-900">{f2.status}</span> | Confidence: {(f2.confidence * 100).toFixed(1)}%
          </p>
        </div>
      </div>

      <div className="bg-white p-5 rounded-lg border border-border shadow-sm mb-6">
        <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-2">Interpretation</h3>
        <p className="text-sm text-gray-700">{f2.interpretation}</p>
      </div>

      {/* Activation Clustering */}
      {activationClustering && (
        <section>
          <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <Activity className="w-5 h-5 text-purple-600" />
            Activation Clustering
            <span className={`ml-1 px-2 py-0.5 text-xs font-bold rounded-full ${
              activationClustering.suspicious_classes.length > 0
                ? 'bg-red-100 text-red-800'
                : 'bg-emerald-100 text-emerald-800'
            }`}>
              {activationClustering.suspicious_classes.length > 0
                ? `${activationClustering.suspicious_classes.length} suspicious class${activationClustering.suspicious_classes.length > 1 ? 'es' : ''}`
                : 'Clean'}
            </span>
          </h2>
          <div className="bg-white border border-border rounded-lg p-5 shadow-sm">
            <div className="grid grid-cols-3 gap-4 mb-5 text-center">
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-100">
                <div className="text-2xl font-bold text-gray-900">{activationClustering.classes_analyzed}</div>
                <div className="text-xs text-gray-500 mt-1">Classes Analyzed</div>
              </div>
              <div className="bg-emerald-50 rounded-lg p-3 border border-emerald-100">
                <div className="text-2xl font-bold text-emerald-700">{activationClustering.clean_classes}</div>
                <div className="text-xs text-emerald-600 mt-1">Clean Classes</div>
              </div>
              <div className={`rounded-lg p-3 border ${activationClustering.suspicious_classes.length > 0 ? 'bg-red-50 border-red-100' : 'bg-gray-50 border-gray-100'}`}>
                <div className={`text-2xl font-bold ${activationClustering.suspicious_classes.length > 0 ? 'text-red-700' : 'text-gray-400'}`}>
                  {activationClustering.suspicious_classes.length}
                </div>
                <div className={`text-xs mt-1 ${activationClustering.suspicious_classes.length > 0 ? 'text-red-600' : 'text-gray-400'}`}>Suspicious Classes</div>
              </div>
            </div>

            {activationClustering.findings.length > 0 ? (
              <div className="space-y-4">
                {activationClustering.findings.map((finding, i) => (
                  <div key={i} className={`border rounded-lg p-4 ${severityColors[finding.severity] ?? 'bg-gray-50 border-gray-200'}`}>
                    <div className="flex justify-between items-center mb-3">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-gray-900">Class {finding.class_id}</span>
                        <span className="text-xs font-mono bg-white/70 px-2 py-0.5 rounded border">
                          Layer: {finding.layer_name}
                        </span>
                      </div>
                      <span className={`px-2 py-1 rounded text-xs font-bold ${severityColors[finding.severity] ?? 'bg-gray-100 text-gray-700'}`}>
                        {finding.severity.toUpperCase()}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
                      <div>
                        <span className="text-xs text-gray-600 block">Silhouette Score</span>
                        <div className="flex items-center gap-2 mt-1">
                          <div className="flex-1 bg-white/60 rounded-full h-1.5">
                            <div className="h-1.5 rounded-full bg-red-500" style={{ width: `${finding.silhouette_score * 100}%` }} />
                          </div>
                          <span className="font-bold text-gray-900">{finding.silhouette_score.toFixed(3)}</span>
                        </div>
                      </div>
                      <div>
                        <span className="text-xs text-gray-600 block">Minority Fraction</span>
                        <span className="font-bold text-gray-900">{(finding.minority_fraction * 100).toFixed(1)}%</span>
                      </div>
                      <div>
                        <span className="text-xs text-gray-600 block">Suspected Samples</span>
                        <span className="font-bold text-gray-900">{finding.suspected_sample_count}</span>
                      </div>
                    </div>
                    <p className="text-xs text-gray-600 mt-3">
                      ICA (n_components=6) + k-means bimodal split on penultimate layer activations.
                      Silhouette ≥ 0.55 with minority fraction 2–30% indicates backdoor-consistent separation.
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-6 text-emerald-700 bg-emerald-50 rounded-lg border border-emerald-100">
                <Activity className="w-8 h-8 mx-auto mb-2 opacity-60" />
                <p className="text-sm font-medium">No activation clustering anomalies detected.</p>
                <p className="text-xs text-emerald-600 mt-1">All {activationClustering.classes_analyzed} classes exhibit unimodal activation distributions.</p>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Gradient Clustering */}
      {gradientClustering && (
        <section>
          <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <Layers className="w-5 h-5 text-blue-600" />
            Gradient Clustering
            <span className={`ml-1 px-2 py-0.5 text-xs font-bold rounded-full ${
              gradientClustering.suspicious_classes.length > 0
                ? 'bg-red-100 text-red-800'
                : 'bg-emerald-100 text-emerald-800'
            }`}>
              {gradientClustering.suspicious_classes.length > 0
                ? `${gradientClustering.suspicious_classes.length} suspicious`
                : 'Clean'}
            </span>
          </h2>
          <div className="bg-white border border-border rounded-lg p-5 shadow-sm">
            <div className="grid grid-cols-3 gap-4 mb-5 text-center">
              <div className="bg-gray-50 rounded-lg p-3 border border-gray-100">
                <div className="text-2xl font-bold text-gray-900">{gradientClustering.classes_analyzed}</div>
                <div className="text-xs text-gray-500 mt-1">Classes Analyzed</div>
              </div>
              <div className="bg-emerald-50 rounded-lg p-3 border border-emerald-100">
                <div className="text-2xl font-bold text-emerald-700">{gradientClustering.clean_classes}</div>
                <div className="text-xs text-emerald-600 mt-1">Clean Classes</div>
              </div>
              <div className={`rounded-lg p-3 border ${gradientClustering.suspicious_classes.length > 0 ? 'bg-red-50 border-red-100' : 'bg-gray-50 border-gray-100'}`}>
                <div className={`text-2xl font-bold ${gradientClustering.suspicious_classes.length > 0 ? 'text-red-700' : 'text-gray-400'}`}>
                  {gradientClustering.suspicious_classes.length}
                </div>
                <div className={`text-xs mt-1 ${gradientClustering.suspicious_classes.length > 0 ? 'text-red-600' : 'text-gray-400'}`}>Suspicious Classes</div>
              </div>
            </div>

            {gradientClustering.findings.length > 0 ? (
              <div className="space-y-4">
                {gradientClustering.findings.map((finding, i) => (
                  <div key={i} className={`border rounded-lg p-4 ${severityColors[finding.severity] ?? 'bg-gray-50 border-gray-200'}`}>
                    <div className="flex justify-between items-center mb-3">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-gray-900">Class {finding.class_id}</span>
                        <span className="text-xs font-mono bg-white/70 px-2 py-0.5 rounded border">
                          Layer: {finding.layer_name}
                        </span>
                      </div>
                      <span className={`px-2 py-1 rounded text-xs font-bold ${severityColors[finding.severity] ?? 'bg-gray-100 text-gray-700'}`}>
                        {finding.severity.toUpperCase()}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 text-sm">
                      <div>
                        <span className="text-xs text-gray-600 block">Cluster Separation</span>
                        <div className="flex items-center gap-2 mt-1">
                          <div className="flex-1 bg-white/60 rounded-full h-1.5">
                            <div className="h-1.5 rounded-full bg-blue-500" style={{ width: `${finding.cluster_separation_score * 100}%` }} />
                          </div>
                          <span className="font-bold text-gray-900">{finding.cluster_separation_score.toFixed(3)}</span>
                        </div>
                      </div>
                      <div>
                        <span className="text-xs text-gray-600 block">Minority Fraction</span>
                        <span className="font-bold text-gray-900">{(finding.minority_fraction * 100).toFixed(1)}%</span>
                      </div>
                      <div>
                        <span className="text-xs text-gray-600 block">Suspected Samples</span>
                        <span className="font-bold text-gray-900">{finding.suspected_sample_count}</span>
                      </div>
                    </div>
                    <p className="text-xs text-gray-600 mt-3">
                      Method: <span className="font-mono">{gradientClustering.method}</span>.
                      Gradient signature k-means clustering on final-layer weights corroborates activation clustering anomaly.
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-6 text-emerald-700 bg-emerald-50 rounded-lg border border-emerald-100">
                <Layers className="w-8 h-8 mx-auto mb-2 opacity-60" />
                <p className="text-sm font-medium">No gradient clustering anomalies detected.</p>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Influence Functions */}
      {influenceFns && influenceFns.top_suspects.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-amber-500" />
            Influence Functions — High-Impact Training Samples
          </h2>
          <div className="bg-white border border-border rounded-lg overflow-hidden shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-gray-700 uppercase bg-amber-50 border-b border-border">
                  <tr>
                    <th className="px-4 py-3">Rank</th>
                    <th className="px-4 py-3">Sample ID</th>
                    <th className="px-4 py-3">Contributor</th>
                    {influenceFns.top_suspects[0]?.class_id !== undefined && (
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
                              className="h-1.5 rounded-full bg-amber-500"
                              style={{ width: `${s.influence_score * 100}%` }}
                            />
                          </div>
                          <span className="text-sm font-bold text-amber-700">{s.influence_score.toFixed(3)}</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="p-3 bg-gray-50 border-t border-border">
              <p className="text-xs text-gray-500">
                Method: <span className="font-mono">{influenceFns.method}</span> — gradient-based influence ranking.
                High scores indicate samples with disproportionate impact on model loss for the target class.
              </p>
            </div>
          </div>
        </section>
      )}

      {/* Spectral Analysis */}
      <section>
        <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
          <Zap className="w-5 h-5 text-gray-600" />
          Spectral Analysis
        </h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-white p-5 rounded-lg border border-border shadow-sm">
            <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-4">Leave-One-Out Calibration</h3>
            <div className="space-y-3">
              <div className="flex justify-between items-center pb-2 border-b border-gray-100">
                <span className="text-sm text-gray-600">Clean Reference Acc.</span>
                <span className="text-sm font-medium">{(leave_one_out_calibration.accuracy_on_clean_reference * 100).toFixed(2)}%</span>
              </div>
              <div className="flex justify-between items-center pb-2 border-b border-gray-100">
                <span className="text-sm text-gray-600">Submitted Acc.</span>
                <span className="text-sm font-medium">{(leave_one_out_calibration.accuracy_on_submitted_model * 100).toFixed(2)}%</span>
              </div>
              <div className="flex justify-between items-center pb-2 border-b border-gray-100">
                <span className="text-sm text-gray-600">Delta</span>
                <span className="text-sm font-medium font-mono">{leave_one_out_calibration.delta.toFixed(4)}</span>
              </div>
              <div className="flex justify-between items-center pb-2 border-b border-gray-100">
                <span className="text-sm text-gray-600">Threshold</span>
                <span className="text-sm font-medium font-mono">{leave_one_out_calibration.threshold.toFixed(4)}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-600">Status</span>
                <VerificationStatus status={leave_one_out_calibration.status} />
              </div>
            </div>
          </div>

          <div className="bg-white p-5 rounded-lg border border-border shadow-sm">
            <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-4">Max-Clean Threshold (Nextafter)</h3>
            <div className="space-y-3">
              <div className="flex justify-between items-center pb-2 border-b border-gray-100">
                <span className="text-sm text-gray-600">Computed Clean Max</span>
                <span className="text-sm font-medium font-mono">{nextafter_max_clean_threshold.computed_clean_max_spectra.toFixed(4)}</span>
              </div>
              <div className="flex justify-between items-center pb-2 border-b border-gray-100">
                <span className="text-sm text-gray-600">Submitted Spectra Max</span>
                <span className="text-sm font-medium font-mono">{nextafter_max_clean_threshold.submitted_max_spectra.toFixed(4)}</span>
              </div>
              <div className="flex justify-between items-center pb-2 border-b border-gray-100">
                <span className="text-sm text-gray-600">Boundary Limit</span>
                <span className="text-sm font-medium font-mono">{nextafter_max_clean_threshold.nextafter_boundary.toFixed(4)}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-600">Status</span>
                <VerificationStatus status={nextafter_max_clean_threshold.status} />
              </div>
            </div>
          </div>
        </div>

        <div className="bg-white p-5 rounded-lg border border-border shadow-sm mt-6">
          <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-6 flex items-center gap-2">
            <GitMerge className="w-4 h-4" /> Per-Layer Wasserstein Distances
          </h3>
          <div className="h-80 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={layerData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorDistance" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                <XAxis dataKey="name" tick={{ fontSize: 10 }} tickMargin={10} minTickGap={30} stroke="#9ca3af" />
                <YAxis tick={{ fontSize: 12 }} stroke="#9ca3af" width={60} />
                <Tooltip
                  contentStyle={{ borderRadius: '8px', border: '1px solid #e5e7eb', boxShadow: '0 4px 6px -1px rgba(0,0,0,0.1)' }}
                  labelStyle={{ fontWeight: 'bold', color: '#374151' }}
                />
                <Legend verticalAlign="top" height={36} />
                <Area type="monotone" dataKey="threshold" stroke="#ef4444" fillOpacity={0} strokeWidth={2} name="Threshold" strokeDasharray="5 5" />
                <Area type="monotone" dataKey="distance" stroke="#8b5cf6" fillOpacity={1} fill="url(#colorDistance)" strokeWidth={2} name="Wasserstein Distance" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </section>
    </div>
  );
}
