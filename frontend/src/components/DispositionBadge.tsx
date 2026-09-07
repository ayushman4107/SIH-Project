import type { Disposition } from '../api/types';
import clsx from 'clsx';
import { twMerge } from 'tailwind-merge';

interface Props {
  disposition: Disposition | string;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

export default function DispositionBadge({ disposition, className, size = 'md' }: Props) {
  const baseClasses = "inline-flex items-center justify-center font-medium rounded-full border";
  
  const sizeClasses = {
    sm: "px-2 py-0.5 text-xs",
    md: "px-3 py-1 text-sm",
    lg: "px-4 py-1.5 text-base"
  };

  const colorClasses = {
    accept: "bg-green-100 text-green-800 border-green-200",
    review: "bg-yellow-100 text-yellow-800 border-yellow-200",
    quarantine: "bg-red-100 text-red-800 border-red-200",
    inconclusive: "bg-gray-100 text-gray-800 border-gray-200"
  };

  const normalizedDisp = (disposition || "inconclusive").toLowerCase() as Disposition;
  const colors = colorClasses[normalizedDisp] || colorClasses.inconclusive;

  return (
    <span className={twMerge(clsx(baseClasses, sizeClasses[size], colors), className)}>
      {disposition.toUpperCase()}
    </span>
  );
}
