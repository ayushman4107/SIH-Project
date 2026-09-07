import { AlertCircle, CheckCircle, XCircle } from 'lucide-react';
import clsx from 'clsx';
import { twMerge } from 'tailwind-merge';

interface Props {
  status: string;
  hasRisk?: boolean;
  riskMessage?: string;
  className?: string;
}

export default function VerificationStatus({ status, hasRisk, riskMessage, className }: Props) {
  const isVerified = status.toLowerCase() === 'verified' || status.toLowerCase() === 'match' || status === 'true';
  const isUnverified = status.toLowerCase() === 'unsigned';
  
  let colorClass = isVerified ? 'bg-green-100 text-green-800 border-green-200' : 'bg-red-100 text-red-800 border-red-200';
  let Icon = isVerified ? CheckCircle : XCircle;

  if (isUnverified) {
    colorClass = 'bg-gray-100 text-gray-800 border-gray-200';
    Icon = AlertCircle;
  }

  // Override to warning if there's a risk (like tail truncation)
  if (isVerified && hasRisk) {
    colorClass = 'bg-yellow-100 text-yellow-800 border-yellow-200';
    Icon = AlertCircle;
  }

  return (
    <div className={twMerge(clsx('flex flex-col gap-2', className))}>
      <span className={clsx('inline-flex items-center gap-1.5 px-3 py-1 text-sm font-medium rounded-full border w-fit', colorClass)}>
        <Icon className="w-4 h-4" />
        {status.toUpperCase()}
      </span>
      {hasRisk && riskMessage && (
        <div className="text-xs text-amber-700 bg-amber-50 p-2 rounded border border-amber-200 max-w-md">
          <strong>Warning:</strong> {riskMessage}
        </div>
      )}
    </div>
  );
}
