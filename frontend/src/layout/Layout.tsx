import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';

export default function Layout() {
  return (
    <div className="flex h-screen w-full bg-background overflow-hidden text-left">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-6 bg-white">
        <div className="max-w-6xl mx-auto h-full">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
