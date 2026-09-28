import { useState, useEffect } from 'react';

import { useParams, useNavigate } from 'react-router-dom';
import { getReport } from '../api/client';
import type { AssuranceReport } from '../api/types';
import {
  Database, GitMerge, ListChecks, AlertTriangle,
  Box, Tag, Info
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

  if (loading) return <div className="text-gray-500 text-center py-12 animate-pulse font-medium text-lg">Loading V2 Assurance Report...</div>;
  if (error) return <div className="text-red-500 text-center py-12">Error: {error}</div>;
  if (!report) return <div className="text-gray-500 text-center py-12">Report not found</div>;

  const f1 = report.F1_data_integrity || {} as any;
  const f2 = report.F2_model_integrity || {} as any;
  const f3 = report.F3_inference_provenance || {} as any;
  const f4 = report.F4_shift_assessment || {} as any;
  const f5 = report.F5_governance || {} as any;

  const dispositionColor = f5?.action === 'ACCEPT' ? 'bg-green-500' : f5.action === 'REVIEW' ? 'bg-amber-500' : 'bg-red-500';

  return (
    <div className="space-y-8 animate-fade-in pb-12">
      {/* Header */}
      <div className="bg-white/50 dark:bg-gray-800/80 backdrop-blur-md border border-gray-200 dark:border-gray-700 rounded-2xl p-8 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-6">
          <div>
            <h1 className="text-4xl font-black tracking-tight mb-3 text-transparent bg-clip-text bg-gradient-to-r from-gray-800 to-gray-500 dark:from-white dark:to-gray-400">
              Assurance Report
            </h1>
            <div className="flex flex-wrap items-center gap-4 text-sm text-gray-500 dark:text-gray-400 font-medium">
              <span className="flex items-center gap-1.5"><Tag className="w-4 h-4 text-indigo-400" /> Case ID: {report.case_id}</span>
              <span className="flex items-center gap-1.5"><Box className="w-4 h-4 text-emerald-400" /> Subject Type: {report.subject_type?.replace(/_/g, ' ')}</span>
              <span className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">Schema v{report.schema_version}</span>
            </div>
          </div>
          <div className="flex flex-col items-end">
            <span className="text-sm font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-widest mb-2">Final Action</span>
            <div className={`px-6 py-2 rounded-lg font-bold text-white shadow-lg ${dispositionColor}`}>
              {f5.action}
            </div>
          </div>
        </div>
      </div>

      {/* Pillar Cards Grid */}
      <h2 className="text-2xl font-extrabold mb-6 mt-10 text-gray-800 dark:text-gray-100 px-2">Assurance Pillars</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 px-2">
        
        {/* F1 Card */}
        <div 
          onClick={() => navigate(`/report/${reportId}/findings`)}
          className="group cursor-pointer bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-2xl p-6 shadow-sm hover:shadow-xl transition-all duration-300 transform hover:-translate-y-1"
        >
          <div className="flex items-center gap-3 mb-4">
            <div className="p-3 bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 rounded-xl group-hover:scale-110 transition-transform"><Database className="w-6 h-6" /></div>
            <h3 className="font-bold text-gray-900 dark:text-white text-lg">F1: Data Integrity</h3>
          </div>
          <div className="space-y-2">
             <div className="flex justify-between text-sm">
                 <span className="text-gray-500 dark:text-gray-400">Box Status</span>
                 <span className="font-semibold text-gray-700 dark:text-gray-300">{f1.box_status}</span>
             </div>
             <div className="flex justify-between text-sm">
                 <span className="text-gray-500 dark:text-gray-400">Spectral Status</span>
                 <span className="font-semibold text-gray-700 dark:text-gray-300">{f1.spectral_status}</span>
             </div>
          </div>
        </div>

        {/* F2 Card */}
        <div 
          onClick={() => navigate(`/report/${reportId}/model-integrity`)}
          className="group cursor-pointer bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-2xl p-6 shadow-sm hover:shadow-xl transition-all duration-300 transform hover:-translate-y-1"
        >
          <div className="flex items-center gap-3 mb-4">
            <div className="p-3 bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400 rounded-xl group-hover:scale-110 transition-transform"><GitMerge className="w-6 h-6" /></div>
            <h3 className="font-bold text-gray-900 dark:text-white text-lg">F2: Model Integrity</h3>
          </div>
          <div className="space-y-2">
             <div className="flex justify-between text-sm">
                 <span className="text-gray-500 dark:text-gray-400">Behavioral</span>
                 <span className="font-semibold text-gray-700 dark:text-gray-300">{f2.behavioral_status}</span>
             </div>
             <div className="flex justify-between text-sm">
                 <span className="text-gray-500 dark:text-gray-400">Quantization</span>
                 <span className="font-semibold text-gray-700 dark:text-gray-300">{f2.quantization_status?.replace(/_/g, ' ')}</span>
             </div>
          </div>
        </div>

        {/* F3 Card */}
        <div 
          onClick={() => navigate(`/report/${reportId}/ledger`)}
          className="group cursor-pointer bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-2xl p-6 shadow-sm hover:shadow-xl transition-all duration-300 transform hover:-translate-y-1"
        >
          <div className="flex items-center gap-3 mb-4">
            <div className="p-3 bg-indigo-100 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 rounded-xl group-hover:scale-110 transition-transform"><ListChecks className="w-6 h-6" /></div>
            <h3 className="font-bold text-gray-900 dark:text-white text-lg">F3: Provenance</h3>
          </div>
          <div className="space-y-2">
             <div className="flex justify-between text-sm">
                 <span className="text-gray-500 dark:text-gray-400">Chain Status</span>
                 <span className="font-semibold text-gray-700 dark:text-gray-300">{f3.chain_status}</span>
             </div>
             <div className="flex justify-between text-sm">
                 <span className="text-gray-500 dark:text-gray-400">VDF Status</span>
                 <span className="font-semibold text-gray-700 dark:text-gray-300">{f3.vdf_status}</span>
             </div>
          </div>
        </div>

        {/* F4 Card */}
        <div 
          onClick={() => navigate(`/report/${reportId}/distribution-shift`)}
          className="group cursor-pointer bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-2xl p-6 shadow-sm hover:shadow-xl transition-all duration-300 transform hover:-translate-y-1"
        >
          <div className="flex items-center gap-3 mb-4">
            <div className="p-3 bg-rose-100 dark:bg-rose-900/30 text-rose-600 dark:text-rose-400 rounded-xl group-hover:scale-110 transition-transform"><AlertTriangle className="w-6 h-6" /></div>
            <h3 className="font-bold text-gray-900 dark:text-white text-lg">F4: Dist. Shift</h3>
          </div>
          <div className="space-y-2">
             <div className="flex justify-between text-sm">
                 <span className="text-gray-500 dark:text-gray-400">Risk Score</span>
                 <span className="font-semibold text-gray-700 dark:text-gray-300">{f4.risk_score?.toFixed(2) ?? 'N/A'}</span>
             </div>
             <div className="flex justify-between text-sm">
                 <span className="text-gray-500 dark:text-gray-400">Grad Response</span>
                 <span className="font-semibold text-gray-700 dark:text-gray-300">{f4.grad_h_norm?.toFixed(2) ?? 'N/A'}</span>
             </div>
          </div>
        </div>
      </div>

      {/* F5 Limitations and Notes */}
      {f5.limitation_notes?.length > 0 && (
          <div className="mt-10 px-2">
              <h2 className="text-xl font-bold mb-4 flex items-center gap-2 text-gray-800 dark:text-gray-100">
                  <Info className="w-5 h-5 text-gray-500" />
                  Governance Limitations & Analyst Notes
              </h2>
              <div className="bg-gray-50 dark:bg-gray-800/40 rounded-xl p-6 border border-gray-200 dark:border-gray-700">
                  <ul className="list-disc pl-5 space-y-2 text-sm text-gray-600 dark:text-gray-400">
                      {f5.limitation_notes?.map((note, idx) => (
                          <li key={idx}>{note}</li>
                      ))}
                  </ul>
                  {f5.analyst_decision && (
                      <div className="mt-6 pt-4 border-t border-gray-200 dark:border-gray-700">
                          <span className="font-bold text-gray-800 dark:text-gray-200 block mb-1">Analyst Decision History:</span>
                          <span className="text-sm italic text-gray-600 dark:text-gray-400">{f5.analyst_decision}</span>
                      </div>
                  )}
              </div>
          </div>
      )}
    </div>
  );
}

