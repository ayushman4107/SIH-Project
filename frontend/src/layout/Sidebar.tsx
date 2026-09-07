import { useState, useEffect } from 'react';
import { NavLink, useParams } from 'react-router-dom';
import { Shield, FileText, Database, GitMerge, AlertTriangle, ListChecks } from 'lucide-react';
import { listRuns } from '../api/client';

export default function Sidebar() {
  const { reportId } = useParams();
  const [runs, setRuns] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    listRuns()
      .then(data => setRuns(data))
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const menuItems = [
    { id: '', label: 'Dashboard', icon: Shield },
    { id: 'findings', label: 'F1: Data Integrity', icon: Database },
    { id: 'model-integrity', label: 'F2: Model Integrity', icon: GitMerge },
    { id: 'ledger', label: 'F3: Provenance', icon: ListChecks },
    { id: 'distribution-shift', label: 'F4: Dist. Shift', icon: AlertTriangle },
    { id: 'coverage', label: 'F5: Coverage', icon: FileText },
  ];

  return (
    <aside className="w-64 border-r border-border bg-gray-50 flex flex-col h-screen overflow-y-auto">
      <div className="p-4 border-b border-border">
        <h1 className="text-lg font-semibold flex items-center gap-2">
          <Shield className="w-5 h-5 text-purple-600" />
          VisiOps Assurance
        </h1>
      </div>

      <div className="p-4 flex-1">
        <h2 className="text-xs font-semibold text-muted uppercase tracking-wider mb-2">Available Runs</h2>
        {loading && <p className="text-sm text-muted">Loading runs...</p>}
        {error && <p className="text-sm text-red-500">{error}</p>}
        {!loading && runs.length === 0 && <p className="text-sm text-muted">No runs found.</p>}
        
        <ul className="space-y-1 mb-6">
          {runs.map(runId => (
            <li key={runId}>
              <NavLink 
                to={`/report/${runId}`}
                className={({ isActive }) => 
                  `block px-3 py-2 text-sm rounded-md truncate ${isActive || reportId === runId ? 'bg-purple-100 text-purple-900 font-medium' : 'text-gray-700 hover:bg-gray-200'}`
                }
                title={runId}
              >
                {runId}
              </NavLink>
            </li>
          ))}
        </ul>

        {reportId && (
          <>
            <h2 className="text-xs font-semibold text-muted uppercase tracking-wider mb-2">Report Details</h2>
            <nav className="space-y-1">
              {menuItems.map(item => (
                <NavLink
                  key={item.id}
                  to={`/report/${reportId}${item.id ? `/${item.id}` : ''}`}
                  end={item.id === ''}
                  className={({ isActive }) => 
                    `flex items-center gap-2 px-3 py-2 text-sm rounded-md ${isActive ? 'bg-white shadow-sm font-medium text-purple-700 border border-border' : 'text-gray-700 hover:bg-gray-200'}`
                  }
                >
                  <item.icon className="w-4 h-4" />
                  {item.label}
                </NavLink>
              ))}
            </nav>
          </>
        )}
      </div>
    </aside>
  );
}
