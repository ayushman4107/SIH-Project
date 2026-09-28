import { getReport } from "../api/client";
import { useParams } from "react-router-dom";
import { useState, useEffect } from "react";
import { Info, AlertCircle, CheckCircle, Shield } from "lucide-react";

import type { AssuranceReport } from '../api/types';

export default function Coverage() {
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

  if (!report) {
    return (
      <div className="p-8 text-center text-gray-500">
        <h2 className="text-2xl font-bold mb-4 text-gray-700 dark:text-gray-200">F5: Governance</h2>
        <p>No governance data available for this report.</p>
      </div>
    );
  }

  const f5 = report.F5_governance || {} as any;
  const actionColor = f5.action === 'ACCEPT' ? 'bg-green-500' : f5.action === 'REVIEW' ? 'bg-amber-500' : 'bg-red-500';
  const ActionIcon = f5.action === 'ACCEPT' ? CheckCircle : f5.action === 'REVIEW' ? AlertCircle : Shield;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-8 animate-fade-in">
      <header className="mb-8">
        <h1 className="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-blue-500 to-indigo-600 mb-2">
          Governance & Coverage
        </h1>
        <p className="text-gray-600 dark:text-gray-400">
          Policy Adjudication and Limitations
        </p>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        <div className="md:col-span-1 bg-white/10 dark:bg-gray-800/50 backdrop-blur-lg border border-gray-200 dark:border-gray-700 rounded-2xl p-6 shadow-xl">
          <h3 className="text-xl font-bold mb-6 text-gray-800 dark:text-gray-100">Final Disposition</h3>
          <div className="flex flex-col items-center justify-center py-6">
            <div className={`p-4 rounded-full text-white mb-4 ${actionColor} shadow-lg shadow-${actionColor}/30`}>
              <ActionIcon className="w-12 h-12" />
            </div>
            <span className="text-3xl font-black text-gray-800 dark:text-white uppercase tracking-widest">{f5.action || 'PENDING'}</span>
            <p className="mt-2 text-sm text-gray-500 text-center">System recommendation based on aggregated pillar signals.</p>
          </div>
        </div>

        <div className="md:col-span-2 bg-white/10 dark:bg-gray-800/50 backdrop-blur-lg border border-gray-200 dark:border-gray-700 rounded-2xl p-6 shadow-xl">
           <h3 className="text-xl font-bold mb-6 text-gray-800 dark:text-gray-100 flex items-center gap-2">
              <Info className="text-blue-500 w-6 h-6" />
              Analyst Notes & Limitations
           </h3>
           
           <div className="space-y-6">
             {f5.limitation_notes?.length > 0 ? (
               <div>
                 <h4 className="font-semibold text-gray-700 dark:text-gray-300 mb-2 border-b border-gray-200 dark:border-gray-700 pb-2">Identified Limitations</h4>
                 <ul className="list-disc pl-5 space-y-2 text-gray-600 dark:text-gray-400">
                   {f5.limitation_notes.map((note: string, idx: number) => (
                     <li key={idx} className="leading-relaxed">{note}</li>
                   ))}
                 </ul>
               </div>
             ) : (
               <p className="text-gray-500 italic">No limitations noted for this execution.</p>
             )}

             {f5.analyst_decision && (
               <div className="bg-blue-50 dark:bg-blue-900/20 p-4 rounded-xl border border-blue-100 dark:border-blue-800">
                 <h4 className="font-semibold text-blue-800 dark:text-blue-300 mb-1">Analyst Override Decision</h4>
                 <p className="text-blue-900 dark:text-blue-200 italic">"{f5.analyst_decision}"</p>
               </div>
             )}
           </div>
        </div>
      </div>
    </div>
  );
}
