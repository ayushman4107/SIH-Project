import { getReport } from "../api/client";
import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";

import type { AssuranceReport } from '../api/types';

export default function ModelIntegrity() {

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

  if (loading) return <div className="p-8 text-center text-gray-500">Loading data...</div>;

  if (!report || report.subject_type !== 'CANDIDATE_MODEL' && report.subject_type !== 'HYBRID_DEMO') {
    return (
      <div className="p-8 text-center text-gray-500">
        <h2 className="text-2xl font-bold mb-4 text-gray-700 dark:text-gray-200">F2: Model Integrity</h2>
        <p>No candidate model data available for this report.</p>
      </div>
    );
  }

  const f2 = report.F2_model_integrity || {} as any;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8 animate-fade-in">
      <header className="mb-8">
        <h1 className="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-emerald-500 to-teal-600 mb-2">
          Model Integrity
        </h1>
        <p className="text-gray-600 dark:text-gray-400">
          Behavioral Fingerprinting & Quantization-Aware Divergence
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Anti-Distillation Behavioral Fingerprinting Card */}
        <div className="bg-white/10 dark:bg-gray-800/50 backdrop-blur-lg border border-gray-200 dark:border-gray-700 rounded-2xl p-6 shadow-xl hover:shadow-2xl transition-all duration-300">
          <h3 className="text-xl font-bold mb-4 text-gray-800 dark:text-gray-100 flex items-center">
            <span className="bg-emerald-100 text-emerald-800 text-sm font-semibold mr-3 px-2.5 py-0.5 rounded dark:bg-emerald-200 dark:text-emerald-800">Stage 2A</span>
            Behavioral Fingerprinting
          </h3>
          
          <div className="mb-4">
            <span className="text-gray-500 dark:text-gray-400 block mb-1">Status</span>
            <span className={`text-lg font-semibold ${f2.behavioral_status === 'ACCEPT' ? 'text-green-500' : 'text-amber-500'}`}>
              {f2.behavioral_status}
            </span>
          </div>

          <div className="space-y-4 mb-6">
            <div className="flex justify-between items-center p-3 bg-gray-50 dark:bg-gray-900 rounded-lg">
                <span className="text-sm text-gray-600 dark:text-gray-400">Reference Model ID</span>
                <span className="font-mono text-sm text-gray-800 dark:text-gray-200">{report.model_id || 'UNKNOWN'}</span>
            </div>
            <div className="flex justify-between items-center p-3 bg-gray-50 dark:bg-gray-900 rounded-lg">
                <span className="text-sm text-gray-600 dark:text-gray-400">Probe Set ID</span>
                <span className="font-mono text-sm text-gray-800 dark:text-gray-200">{f2.probe_set_id || 'N/A'}</span>
            </div>
          </div>

          <div className="space-y-3">
             <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300">Component Similarities</h4>
             {Object.entries(f2.fingerprint_component_scores || {}).map(([key, value]) => (
                <div key={key} className="relative pt-1">
                  <div className="flex mb-2 items-center justify-between">
                    <div>
                      <span className="text-xs font-semibold inline-block uppercase text-emerald-600 dark:text-emerald-400">
                        {key.replace('S_', '')}
                      </span>
                    </div>
                    <div className="text-right">
                      <span className="text-xs font-semibold inline-block text-gray-600 dark:text-gray-400">
                        {(value * 100).toFixed(1)}%
                      </span>
                    </div>
                  </div>
                  <div className="overflow-hidden h-2 mb-4 text-xs flex rounded bg-emerald-200 dark:bg-emerald-900/30">
                    <div style={{ width: `${Math.max(0, Math.min(100, value * 100))}%` }} className="shadow-none flex flex-col text-center whitespace-nowrap text-white justify-center bg-emerald-500"></div>
                  </div>
                </div>
             ))}
             {Object.keys(f2.fingerprint_component_scores || {}).length > 0 && (
                 <p className="text-xs text-amber-600 dark:text-amber-400 mt-2 p-2 bg-amber-50 dark:bg-amber-900/20 rounded">
                     <strong>Note:</strong> High behavioral similarity is evidence of lineage, but does not independently prove model theft.
                 </p>
             )}
          </div>
        </div>

        {/* Quantization-Aware Divergence Filter Card */}
        <div className="bg-white/10 dark:bg-gray-800/50 backdrop-blur-lg border border-gray-200 dark:border-gray-700 rounded-2xl p-6 shadow-xl hover:shadow-2xl transition-all duration-300">
          <h3 className="text-xl font-bold mb-4 text-gray-800 dark:text-gray-100 flex items-center">
            <span className="bg-teal-100 text-teal-800 text-sm font-semibold mr-3 px-2.5 py-0.5 rounded dark:bg-teal-200 dark:text-teal-800">Stage 2B</span>
            Quantization Divergence Filter
          </h3>
          
          <div className="mb-6">
            <span className="text-gray-500 dark:text-gray-400 block mb-1">Quantization Status</span>
            <span className={`text-lg font-semibold ${
                f2.quantization_status === 'NORMAL_PRECISION_DRIFT' ? 'text-green-500' : 
                f2.quantization_status === 'UNAVAILABLE' ? 'text-gray-500' : 'text-amber-500'
            }`}>
              {f2.quantization_status.replace(/_/g, ' ')}
            </span>
          </div>

          <div className="space-y-4">
             <div className="p-4 bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-100 dark:border-gray-800">
                 <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">Precision-Pair Availability</h4>
                 <p className="text-sm text-gray-600 dark:text-gray-400">
                     {f2.quantization_status === 'UNAVAILABLE' 
                        ? 'Waived: No valid INT8/quantized path available for comparison.'
                        : 'FP32 and INT8 counterparts successfully evaluated.'}
                 </p>
             </div>
             
             {f2.quant_baseline_id && (
                 <div className="flex justify-between items-center p-3 bg-gray-50 dark:bg-gray-900 rounded-lg">
                    <span className="text-sm text-gray-600 dark:text-gray-400">Calibration Baseline</span>
                    <span className="font-mono text-sm text-gray-800 dark:text-gray-200">{f2.quant_baseline_id}</span>
                 </div>
             )}

             <div className="mt-6 p-4 rounded-lg bg-teal-50 dark:bg-teal-900/20 border border-teal-100 dark:border-teal-800/30">
                 <h4 className="text-sm font-semibold text-teal-800 dark:text-teal-300 mb-2">Final Admission</h4>
                 <div className="flex items-center">
                     <div className={`w-3 h-3 rounded-full mr-2 ${f2.admission === 'ACCEPT' ? 'bg-green-500' : 'bg-amber-500'}`}></div>
                     <span className="font-bold text-gray-800 dark:text-gray-200">{f2.admission}</span>
                 </div>
             </div>
          </div>
        </div>
      </div>
    </div>
  );
}
