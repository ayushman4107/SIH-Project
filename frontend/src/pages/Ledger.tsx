import { getReport } from "../api/client";
import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";

import type { AssuranceReport } from '../api/types';

export default function Ledger() {

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

  if (!report || report.subject_type !== 'INFERENCE' && report.subject_type !== 'HYBRID_DEMO') {
    return (
      <div className="p-8 text-center text-gray-500">
        <h2 className="text-2xl font-bold mb-4 text-gray-700 dark:text-gray-200">F3: Inference Provenance</h2>
        <p>No inference data available for this report.</p>
      </div>
    );
  }

  const f3 = report.F3_inference_provenance || {} as any;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8 animate-fade-in">
      <header className="mb-8">
        <h1 className="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-blue-600 to-indigo-600 mb-2">
          Inference Provenance
        </h1>
        <p className="text-gray-600 dark:text-gray-400">
          Forward-Secure Temporal and Runtime Provenance Engine
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Verification Status Card */}
        <div className="bg-white/10 dark:bg-gray-800/50 backdrop-blur-lg border border-gray-200 dark:border-gray-700 rounded-2xl p-6 shadow-xl hover:shadow-2xl transition-all duration-300">
          <h3 className="text-xl font-bold mb-6 text-gray-800 dark:text-gray-100 flex items-center border-b border-gray-200 dark:border-gray-700 pb-3">
            <svg className="w-6 h-6 mr-3 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path></svg>
            Verification Results
          </h3>
          
          <div className="space-y-5">
            <div className="flex justify-between items-center p-3 rounded-lg bg-gray-50 dark:bg-gray-900 border-l-4 border-indigo-500">
                <div>
                    <span className="text-sm text-gray-500 dark:text-gray-400 block">Hash Chain Status</span>
                    <span className="font-semibold text-gray-800 dark:text-gray-200">{f3.chain_status}</span>
                </div>
                <div className="text-right">
                    <span className="text-sm text-gray-500 dark:text-gray-400 block">Audit Sequence</span>
                    <span className="font-mono text-indigo-600 dark:text-indigo-400">#{f3.audit_seq || 'N/A'}</span>
                </div>
            </div>

            <div className="flex justify-between items-center p-3 rounded-lg bg-gray-50 dark:bg-gray-900 border-l-4 border-indigo-500">
                <div>
                    <span className="text-sm text-gray-500 dark:text-gray-400 block">VDF Proof Status</span>
                    <span className="font-semibold text-gray-800 dark:text-gray-200">{f3.vdf_status}</span>
                </div>
                <div className="text-right">
                    <span className="text-sm text-gray-500 dark:text-gray-400 block">Checkpoint ID</span>
                    <span className="font-mono text-xs text-gray-600 dark:text-gray-400">{f3.checkpoint_id || 'N/A'}</span>
                </div>
            </div>

            <div className="flex justify-between items-center p-3 rounded-lg bg-gray-50 dark:bg-gray-900 border-l-4 border-indigo-500">
                <div>
                    <span className="text-sm text-gray-500 dark:text-gray-400 block">Telemetry Bounds</span>
                    <span className="font-semibold text-gray-800 dark:text-gray-200">{f3.telemetry_status}</span>
                </div>
                <div className="text-right">
                    <span className="text-sm text-gray-500 dark:text-gray-400 block">Local Clock Claim</span>
                    <span className="text-sm text-gray-600 dark:text-gray-400">{new Date().toISOString()}</span>
                </div>
            </div>
          </div>
          
          <div className="mt-6 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-sm text-blue-800 dark:text-blue-300">
              <strong>Note:</strong> Record authenticity confirms the log has not been tampered with. It does not independently verify the truthfulness of the recorded runtime or clock measurements.
          </div>
        </div>

        {/* Cryptographic Digests Card */}
        <div className="bg-white/10 dark:bg-gray-800/50 backdrop-blur-lg border border-gray-200 dark:border-gray-700 rounded-2xl p-6 shadow-xl hover:shadow-2xl transition-all duration-300 flex flex-col">
          <h3 className="text-xl font-bold mb-6 text-gray-800 dark:text-gray-100 flex items-center border-b border-gray-200 dark:border-gray-700 pb-3">
            <svg className="w-6 h-6 mr-3 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"></path></svg>
            Cryptographic Payload Binding
          </h3>
          
          <div className="flex-1 space-y-4">
            <div className="bg-gray-100 dark:bg-gray-900 rounded p-3">
                <span className="text-xs font-semibold text-gray-500 uppercase block mb-1">Model ID</span>
                <div className="font-mono text-sm text-gray-800 dark:text-gray-300 break-all">{report.model_id || 'UNKNOWN'}</div>
            </div>
            
            <div className="bg-gray-100 dark:bg-gray-900 rounded p-3">
                <span className="text-xs font-semibold text-gray-500 uppercase block mb-1">Raw Input Digest</span>
                <div className="font-mono text-sm text-gray-800 dark:text-gray-300 break-all">{report.raw_input_digest || 'N/A'}</div>
            </div>

            <div className="bg-gray-100 dark:bg-gray-900 rounded p-3">
                <span className="text-xs font-semibold text-gray-500 uppercase block mb-1">Raw Output Digest</span>
                <div className="font-mono text-sm text-gray-800 dark:text-gray-300 break-all">{f3.raw_output_digest || 'N/A'}</div>
            </div>

            <div className="bg-gray-100 dark:bg-gray-900 rounded p-3">
                <span className="text-xs font-semibold text-gray-500 uppercase block mb-1">Record Hash</span>
                <div className="font-mono text-sm text-gray-800 dark:text-gray-300 break-all">{f3.raw_record_hash || 'N/A'}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
