import os, re

files = [
  'frontend/src/pages/Findings.tsx',
  'frontend/src/pages/ModelIntegrity.tsx',
  'frontend/src/pages/Ledger.tsx',
  'frontend/src/pages/DistShift.tsx'
]

fetch_logic = """
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
"""

for f in files:
  content = open(f).read()
  
  if 'useParams' not in content:
      content = 'import { useParams } from "react-router-dom";\n' + content
  if 'useState' not in content:
      content = 'import { useState, useEffect } from "react";\n' + content
  if 'getReport' not in content:
      content = 'import { getReport } from "../api/client";\n' + content
      
  # Replace the component signature and add fetch logic
  content = re.sub(r'export default function (\w+)\([^)]*\) \{', r'export default function \1() {\n' + fetch_logic, content)
  
  # Also handle cases where there are missing sections (prevent null pointer exceptions)
  content = content.replace("const f1 = report.F1_data_integrity;", "const f1 = report.F1_data_integrity || {} as any;")
  content = content.replace("const f2 = report.F2_model_integrity;", "const f2 = report.F2_model_integrity || {} as any;")
  content = content.replace("const f3 = report.F3_inference_provenance;", "const f3 = report.F3_inference_provenance || {} as any;")
  content = content.replace("const f4 = report.F4_shift_assessment;", "const f4 = report.F4_shift_assessment || {} as any;")

  open(f, 'w').write(content)
