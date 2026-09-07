import { Routes, Route } from 'react-router-dom';
import Layout from './layout/Layout';
import Dashboard from './pages/Dashboard';
import Findings from './pages/Findings';
import Ledger from './pages/Ledger';
import ModelIntegrity from './pages/ModelIntegrity';
import DistShift from './pages/DistShift';
import Coverage from './pages/Coverage';
import NotFound from './pages/NotFound';

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        {/* Redirect root to a default view or let Layout handle no-report-selected state */}
        <Route index element={
          <div className="flex h-full items-center justify-center text-muted">
            Select a run from the sidebar to view its report.
          </div>
        } />
        <Route path="report/:reportId">
          <Route index element={<Dashboard />} />
          <Route path="findings" element={<Findings />} />
          <Route path="ledger" element={<Ledger />} />
          <Route path="model-integrity" element={<ModelIntegrity />} />
          <Route path="distribution-shift" element={<DistShift />} />
          <Route path="coverage" element={<Coverage />} />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

export default App;
