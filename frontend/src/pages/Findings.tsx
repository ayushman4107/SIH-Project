import { getReport } from "../api/client";
import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";

import type { AssuranceReport } from '../api/types';

export default function Findings() {

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

  if (!report || report.subject_type !== 'TRAINING_SAMPLE' && report.subject_type !== 'HYBRID_DEMO') {
    return (
      <div className="p-8 text-center text-gray-500">
        <h2 className="text-2xl font-bold mb-4 text-gray-700 dark:text-gray-200">F1: Data Integrity</h2>
        <p>No training sample data available for this report.</p>
      </div>
    );
  }

  const f1 = report.F1_data_integrity || {} as any;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8 animate-fade-in">
      <header className="mb-8">
        <h1 className="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-blue-500 to-purple-600 mb-2">
          Training Data Integrity
        </h1>
        <p className="text-gray-600 dark:text-gray-400">
          Spatial Bounding-Box Consistency & Closed-Form Spectral-Counterfactual Attribution
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Spatial Bounding-Box Card */}
        <div className="bg-white/10 dark:bg-gray-800/50 backdrop-blur-lg border border-gray-200 dark:border-gray-700 rounded-2xl p-6 shadow-xl hover:shadow-2xl transition-all duration-300">
          <h3 className="text-xl font-bold mb-4 text-gray-800 dark:text-gray-100 flex items-center">
            <span className="bg-blue-100 text-blue-800 text-sm font-semibold mr-3 px-2.5 py-0.5 rounded dark:bg-blue-200 dark:text-blue-800">Stage 1A</span>
            Spatial Bounding-Box Consistency
          </h3>
          <div className="mb-4">
            <span className="text-gray-500 dark:text-gray-400 block mb-1">Box Status</span>
            <span className={`text-lg font-semibold ${f1.box_status === 'PASS' ? 'text-green-500' : 'text-amber-500'}`}>
              {f1.box_status}
            </span>
          </div>
          
          <div className="relative rounded-lg overflow-hidden border border-gray-200 dark:border-gray-700 bg-gray-100 dark:bg-gray-900 aspect-video flex items-center justify-center">
             {/* Mocking the Image with Bounding Box Overlay */}
             <div className="absolute inset-0 bg-[url('https://images.unsplash.com/photo-1542362567-b07e54358753?w=800&q=80')] bg-cover bg-center opacity-80 mix-blend-luminosity"></div>
             {f1.box_status !== 'PASS' && (
                 <div className="absolute border-2 border-red-500 bg-red-500/20 w-1/3 h-1/3 top-1/4 left-1/4 animate-pulse">
                     <span className="absolute -top-6 left-0 bg-red-500 text-white text-xs px-2 py-1 font-bold">Shifted/Empty Context</span>
                 </div>
             )}
             {f1.box_status === 'PASS' && (
                 <div className="absolute border-2 border-green-500 w-1/3 h-1/3 top-1/4 left-1/4">
                     <span className="absolute -top-6 left-0 bg-green-500 text-white text-xs px-2 py-1 font-bold">Valid Object</span>
                 </div>
             )}
          </div>
          <div className="mt-4">
              <span className="text-xs text-gray-500">Activation edge centroid finding IDs: {f1.activation_edge_centroid_finding_ids.join(', ') || 'None'}</span>
          </div>
        </div>

        {/* Spectral Attribution Card */}
        <div className="bg-white/10 dark:bg-gray-800/50 backdrop-blur-lg border border-gray-200 dark:border-gray-700 rounded-2xl p-6 shadow-xl hover:shadow-2xl transition-all duration-300">
          <h3 className="text-xl font-bold mb-4 text-gray-800 dark:text-gray-100 flex items-center">
            <span className="bg-purple-100 text-purple-800 text-sm font-semibold mr-3 px-2.5 py-0.5 rounded dark:bg-purple-200 dark:text-purple-800">Stage 1B</span>
            Spectral-Counterfactual Repair
          </h3>
          <div className="flex justify-between items-center mb-4">
            <div>
                <span className="text-gray-500 dark:text-gray-400 block mb-1">Spectral Status</span>
                <span className={`text-lg font-semibold ${f1.spectral_status === 'NOT_RUN' ? 'text-gray-400' : 'text-purple-500'}`}>
                  {f1.spectral_status}
                </span>
            </div>
            {f1.spectral_screen_id && (
                <div className="text-right">
                    <span className="text-xs text-gray-500 block">Screen ID</span>
                    <span className="font-mono text-sm text-gray-700 dark:text-gray-300">{f1.spectral_screen_id.split('-')[0]}...</span>
                </div>
            )}
          </div>
          
          <div className="relative rounded-lg overflow-hidden border border-gray-200 dark:border-gray-700 bg-gray-900 aspect-video flex items-center justify-center">
            {/* Mocking the Spectral Heatmap */}
             <div className="absolute inset-0 bg-[url('https://images.unsplash.com/photo-1542362567-b07e54358753?w=800&q=80')] bg-cover bg-center opacity-40"></div>
             
             {/* Heatmap Overlay Simulation */}
             <div className="absolute inset-0 bg-gradient-to-tr from-transparent via-purple-500/30 to-red-500/40 mix-blend-overlay"></div>
             
             <div className="absolute bottom-2 left-2 right-2 bg-black/60 backdrop-blur-md p-2 rounded text-xs text-amber-200 font-medium text-center border border-amber-500/30">
                 Hypothetical pixel changes produced by limiting anomalous frequency coefficients; not proof of attack location.
             </div>
          </div>
          <div className="mt-4 flex gap-4 text-xs text-gray-500">
             <div>Mask ID: <span className="font-mono">{f1.mask_id || 'N/A'}</span></div>
          </div>
        </div>
      </div>
    </div>
  );
}
