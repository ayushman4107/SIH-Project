import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { getReport } from '../api/client';
import type { AssuranceReport } from '../api/types';
import { ShieldCheck, ShieldAlert, CheckCircle, XCircle } from 'lucide-react';

export default function Coverage() {
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

  const coverage = report.coverage_statement;

  return (
    <div className="space-y-8 pb-12">
      <div className="border-b border-border pb-4">
        <h1 className="text-2xl font-bold tracking-tight mb-1">F5: Coverage Statement</h1>
        <p className="text-sm text-muted">
          Framework: <span className="font-semibold text-gray-900">{coverage.framework} v{coverage.version}</span>
          <span className="mx-2">|</span>
          Generated: {new Date(coverage.generated).toLocaleString()}
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2 mb-4 text-green-700">
            <ShieldCheck className="w-5 h-5" /> Supported Attack Classes
          </h2>
          <div className="space-y-4">
            {coverage.supported_attacks.map((attack, idx) => (
              <div key={idx} className="bg-white border border-green-200 rounded-lg p-4 shadow-sm relative overflow-hidden">
                <div className="absolute top-0 left-0 w-1 h-full bg-green-500"></div>
                <div className="flex justify-between items-start mb-2">
                  <h3 className="font-bold text-gray-900">{attack.attack_class}</h3>
                  <span className="text-xs font-mono bg-gray-100 text-gray-600 px-2 py-0.5 rounded">{attack.method}</span>
                </div>
                
                <div className="grid grid-cols-2 gap-2 text-sm mt-3">
                  <div className="flex flex-col">
                    <span className="text-xs text-gray-500">Confidence Range</span>
                    <span className="font-medium text-gray-800">{(attack.confidence_range_min * 100).toFixed(0)}% - {(attack.confidence_range_max * 100).toFixed(0)}%</span>
                  </div>
                  <div className="flex flex-col">
                    <span className="text-xs text-gray-500">Tested Poison Ratio</span>
                    <span className="font-medium text-gray-800">{(attack.tested_poison_ratio * 100).toFixed(0)}%</span>
                  </div>
                  <div className="flex flex-col col-span-2">
                    <span className="text-xs text-gray-500">Tested Dataset</span>
                    <span className="font-medium text-gray-800">{attack.tested_on_dataset}</span>
                  </div>
                  <div className="flex flex-col col-span-2 mt-1">
                    <span className="text-xs text-gray-500">Evidence</span>
                    <span className="text-gray-700 italic text-xs">{attack.evidence}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2 mb-4 text-gray-700">
            <ShieldAlert className="w-5 h-5" /> Unsupported Attack Classes
          </h2>
          <div className="space-y-4">
            {coverage.unsupported_attacks.map((attack, idx) => (
              <div key={idx} className="bg-gray-50 border border-gray-200 rounded-lg p-4 relative overflow-hidden">
                <div className="absolute top-0 left-0 w-1 h-full bg-gray-400"></div>
                <h3 className="font-bold text-gray-900 mb-2">{attack.attack_class}</h3>
                <div className="flex flex-col">
                  <span className="text-xs text-gray-500 mb-1">Reason</span>
                  <p className="text-sm text-gray-700">{attack.reason}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mt-4 pt-8 border-t border-gray-200">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2 mb-4">
            <CheckCircle className="w-5 h-5 text-purple-600" /> Trust Assumptions
          </h2>
          <ul className="space-y-3">
            {coverage.assumptions.map((item, idx) => (
              <li key={idx} className="flex gap-3 items-start bg-white p-3 rounded border border-gray-100 shadow-sm">
                <span className="flex-shrink-0 w-5 h-5 flex items-center justify-center rounded-full bg-purple-100 text-purple-700 text-xs font-bold mt-0.5">{idx + 1}</span>
                <span className="text-sm text-gray-700 leading-relaxed">{item}</span>
              </li>
            ))}
          </ul>
        </div>

        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2 mb-4">
            <XCircle className="w-5 h-5 text-red-500" /> Known Limitations
          </h2>
          <ul className="space-y-3">
            {coverage.known_limitations.map((item, idx) => (
              <li key={idx} className="flex gap-3 items-start bg-red-50 p-3 rounded border border-red-100">
                <span className="flex-shrink-0 w-5 h-5 flex items-center justify-center rounded-full bg-red-200 text-red-800 text-xs font-bold mt-0.5">{idx + 1}</span>
                <span className="text-sm text-red-900 leading-relaxed">{item}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
      
    </div>
  );
}
