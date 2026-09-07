from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import json
import re

app = FastAPI(title="Sentinel Assurance API")

# Add CORS middleware for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RUNS_DIR = Path("output/runs")
# For testing when the real directory doesn't exist, we can fallback to the mock_data directory
MOCK_DIR = Path("api/mock_data")

def is_valid_report_id(report_id: str) -> bool:
    """Validate report_id to prevent path traversal (allow alphanumeric, hyphens, underscores)."""
    return bool(re.match(r"^[a-zA-Z0-9_-]+$", report_id))

@app.get("/api/runs")
def list_runs():
    runs = []
    if RUNS_DIR.exists():
        runs.extend([p.name for p in RUNS_DIR.iterdir() if p.is_dir()])
    
    # Also include mock data if available
    if MOCK_DIR.exists():
        # Just check if there's an example assurance report there
        if (MOCK_DIR / "example_assurance_report.json").exists():
            if "mock-example" not in runs:
                runs.append("mock-example")
                
    return sorted(list(set(runs)))

def get_file_path(report_id: str, filename: str) -> Path:
    if not is_valid_report_id(report_id):
        raise HTTPException(400, "Invalid report ID format")
        
    if report_id == "mock-example" and MOCK_DIR.exists():
        if filename == "assurance_report.json":
            return MOCK_DIR / "example_assurance_report.json"
        elif filename == "audit_log.json":
            return MOCK_DIR / "example_audit_log.json"
            
    return RUNS_DIR / report_id / filename

@app.get("/api/runs/{report_id}")
def get_report(report_id: str):
    path = get_file_path(report_id, "assurance_report.json")
    if not path.exists():
        raise HTTPException(404, "Report not found")
    return json.loads(path.read_text(encoding="utf-8"))

@app.get("/api/runs/{report_id}/ledger")
def get_ledger(report_id: str):
    path = get_file_path(report_id, "audit_log.json")
    if not path.exists():
        raise HTTPException(404, "Ledger not found")
    return json.loads(path.read_text(encoding="utf-8"))
