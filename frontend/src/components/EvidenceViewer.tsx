interface Props {
  evidence: Record<string, any>;
  className?: string;
}

export default function EvidenceViewer({ evidence, className }: Props) {
  // Extract description if it exists
  const { description, ...rest } = evidence;

  return (
    <div className={`bg-gray-50 p-4 rounded-md border border-gray-200 ${className || ''}`}>
      {description && (
        <p className="text-sm text-gray-700 mb-4 pb-3 border-b border-gray-200">
          {description}
        </p>
      )}
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-3">
        {Object.entries(rest).map(([key, value]) => {
          // Format key: "label_quality_score" -> "Label Quality Score"
          const formattedKey = key
            .split('_')
            .map(word => word.charAt(0).toUpperCase() + word.slice(1))
            .join(' ');
            
          let formattedValue = value;
          if (typeof value === 'boolean') {
            formattedValue = value ? 'True' : 'False';
          } else if (typeof value === 'number') {
            // Format floats slightly if they are long
            formattedValue = Number.isInteger(value) ? value : Number(value.toFixed(4));
          } else if (Array.isArray(value)) {
            formattedValue = value.join(', ');
          } else if (typeof value === 'object' && value !== null) {
            formattedValue = JSON.stringify(value);
          }

          return (
            <div key={key} className="flex flex-col">
              <span className="text-xs text-gray-500 font-medium">{formattedKey}</span>
              <span className="text-sm font-mono text-gray-900 break-all">{String(formattedValue)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
