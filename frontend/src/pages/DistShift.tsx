import { getReport } from "../api/client";
import { useParams } from "react-router-dom";
import { useState, useEffect } from 'react';

import type { AssuranceReport } from '../api/types';

export default function DistShift() {

  const { reportId } = useParams();
  const [report, setReport] = useState<AssuranceReport | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!reportId) return;
    getReport(reportId)
      .then(data => setReport(data))
      .catch(err => console.error(err))
      .finally(() => setLoading(false));
  }, [reportId]);

  

  const [analystAction, setAnalystAction] = useState<string | null>(null);

  if (loading) return <div className="p-8 text-center text-gray-500">Loading data...</div>;

  if (!report || report.subject_type !== 'INFERENCE' && report.subject_type !== 'HYBRID_DEMO') {
    return (
      <div className="p-8 text-center text-gray-500">
        <h2 className="text-2xl font-bold mb-4 text-gray-700 dark:text-gray-200">F4: Distribution Shift</h2>
        <p>No live inference data available for this report.</p>
      </div>
    );
  }

  const f4 = report.F4_shift_assessment || {} as any;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8 animate-fade-in">
      <header className="mb-8">
        <h1 className="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-rose-500 to-orange-500 mb-2">
          Distribution-Shift Assessment
        </h1>
        <p className="text-gray-600 dark:text-gray-400">
          Gradient-Norm Energy Spoofing Defense
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Signals Display */}
        <div className="lg:col-span-2 space-y-6">
            <div className="bg-white/10 dark:bg-gray-800/50 backdrop-blur-lg border border-gray-200 dark:border-gray-700 rounded-2xl p-6 shadow-xl">
                <h3 className="text-xl font-bold mb-6 text-gray-800 dark:text-gray-100 flex items-center border-b border-gray-200 dark:border-gray-700 pb-3">
                    <svg className="w-6 h-6 mr-3 text-rose-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path></svg>
                    Component Signals
                </h3>

                <div className="space-y-6">
                    {/* Energy */}
                    <div className="relative">
                        <div className="flex justify-between mb-1">
                            <span className="font-semibold text-gray-700 dark:text-gray-300">Logit Energy</span>
                            <span className="text-gray-600 dark:text-gray-400">{f4.energy?.toFixed(2) ?? 'N/A'}</span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2.5 dark:bg-gray-700">
                            <div className="bg-rose-500 h-2.5 rounded-full" style={{ width: `${Math.min(100, Math.max(0, ((f4.energy || 0) + 20) * 2.5))}%` }}></div>
                        </div>
                        <p className="text-xs text-gray-500 mt-1">Baseline Range: [-15.0, -5.0]</p>
                    </div>

                    {/* Entropy */}
                    <div className="relative">
                        <div className="flex justify-between mb-1">
                            <span className="font-semibold text-gray-700 dark:text-gray-300">Predictive Entropy</span>
                            <span className="text-gray-600 dark:text-gray-400">{f4.entropy?.toFixed(2) ?? 'N/A'}</span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2.5 dark:bg-gray-700">
                            <div className="bg-orange-500 h-2.5 rounded-full" style={{ width: `${Math.min(100, (f4.entropy || 0) * 50)}%` }}></div>
                        </div>
                        <p className="text-xs text-gray-500 mt-1">Baseline Range: [0.0, 1.2]</p>
                    </div>

                    {/* Mahalanobis */}
                    <div className="relative">
                        <div className="flex justify-between mb-1">
                            <span className="font-semibold text-gray-700 dark:text-gray-300">Mahalanobis Feature Distance</span>
                            <span className="text-gray-600 dark:text-gray-400">{f4.mahalanobis_distance?.toFixed(2) ?? 'N/A'}</span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2.5 dark:bg-gray-700">
                            <div className="bg-amber-500 h-2.5 rounded-full" style={{ width: `${Math.min(100, (f4.mahalanobis_distance || 0) * 10)}%` }}></div>
                        </div>
                        <p className="text-xs text-gray-500 mt-1">Baseline Range: [0.0, 5.0]</p>
                    </div>

                    {/* Gradient Norm */}
                    <div className="relative">
                        <div className="flex justify-between mb-1">
                            <span className="font-semibold text-gray-700 dark:text-gray-300">Internal Gradient Response (||∇_h L||)</span>
                            <span className="text-gray-600 dark:text-gray-400">{f4.grad_h_norm?.toFixed(2) ?? 'N/A'}</span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2.5 dark:bg-gray-700">
                            <div className="bg-red-500 h-2.5 rounded-full" style={{ width: `${Math.min(100, (f4.grad_h_norm || 0) * 20)}%` }}></div>
                        </div>
                        <p className="text-xs text-gray-500 mt-1">Baseline Range: [0.0, 3.5]</p>
                    </div>
                </div>

                {f4.missing_signals && f4.missing_signals.length > 0 && (
                    <div className="mt-6 p-4 bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg">
                        <h4 className="text-sm font-bold text-yellow-800 dark:text-yellow-400 mb-1">Unavailable Signals</h4>
                        <p className="text-sm text-yellow-700 dark:text-yellow-500">{f4.missing_signals.join(', ')}</p>
                    </div>
                )}
            </div>
        </div>

        {/* Analyst Override & Disposition */}
        <div className="space-y-6">
            <div className="bg-white/10 dark:bg-gray-800/50 backdrop-blur-lg border border-gray-200 dark:border-gray-700 rounded-2xl p-6 shadow-xl text-center">
                <h3 className="text-lg font-bold text-gray-800 dark:text-gray-200 mb-2">Fused Risk Score</h3>
                <div className="text-5xl font-black text-rose-600 dark:text-rose-400 mb-4">
                    {f4.risk_score?.toFixed(2) || 'N/A'}
                </div>
                <div className="inline-block px-4 py-2 rounded-full font-bold text-white shadow-md bg-amber-500">
                    {f4.disposition}
                </div>
            </div>

            <div className="bg-white/10 dark:bg-gray-800/50 backdrop-blur-lg border border-gray-200 dark:border-gray-700 rounded-2xl p-6 shadow-xl">
                <h3 className="text-lg font-bold text-gray-800 dark:text-gray-200 mb-4">Analyst Adjudication</h3>
                <div className="space-y-3">
                    <button onClick={() => setAnalystAction('APPROVE')} className={`w-full py-2 px-4 rounded font-semibold transition-colors ${analystAction === 'APPROVE' ? 'bg-green-600 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-600'}`}>
                        Approve
                    </button>
                    <button onClick={() => setAnalystAction('QUARANTINE')} className={`w-full py-2 px-4 rounded font-semibold transition-colors ${analystAction === 'QUARANTINE' ? 'bg-red-600 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-600'}`}>
                        Quarantine
                    </button>
                    <button onClick={() => setAnalystAction('RE_INSPECT')} className={`w-full py-2 px-4 rounded font-semibold transition-colors ${analystAction === 'RE_INSPECT' ? 'bg-blue-600 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-600'}`}>
                        Request Inspection
                    </button>
                    <button onClick={() => setAnalystAction('FALSE_POSITIVE')} className={`w-full py-2 px-4 rounded font-semibold transition-colors ${analystAction === 'FALSE_POSITIVE' ? 'bg-orange-600 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-600'}`}>
                        Mark False Positive
                    </button>
                </div>
                {analystAction && (
                    <div className="mt-4 p-3 bg-gray-100 dark:bg-gray-900 rounded text-sm text-gray-600 dark:text-gray-400">
                        Will be saved as a new authenticated, linked event.
                    </div>
                )}
            </div>
        </div>
      </div>
    </div>
  );
}

