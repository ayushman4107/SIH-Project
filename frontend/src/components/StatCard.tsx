import type { ReactNode } from 'react';

interface Props {
  title: string;
  value: ReactNode;
  subtitle?: ReactNode;
  icon?: ReactNode;
  onClick?: () => void;
}

export default function StatCard({ title, value, subtitle, icon, onClick }: Props) {
  return (
    <div 
      className={`bg-white border border-border rounded-lg p-5 shadow-sm ${onClick ? 'cursor-pointer hover:border-purple-300 hover:shadow-md transition-all' : ''}`}
      onClick={onClick}
    >
      <div className="flex justify-between items-start mb-2">
        <h3 className="text-sm font-medium text-muted">{title}</h3>
        {icon && <div className="text-gray-400">{icon}</div>}
      </div>
      <div className="text-2xl font-bold text-gray-900 mb-1">{value}</div>
      {subtitle && <div className="text-xs text-gray-500">{subtitle}</div>}
    </div>
  );
}
