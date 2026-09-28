import logging
import asyncio
from pathlib import Path
from visiops.pipeline import AssurancePipeline
from visiops.adapters.datasets import YOLOAdapter

logging.basicConfig(level=logging.INFO)

async def main():
    print("🚀 Initializing VisiOps Data Assurance...")
    
    # Initialize the Pipeline
    pipeline = AssurancePipeline()
    
    # Load dataset adapter (Mocking a local YOLO dataset directory)
    # In a real environment, point this to your actual dataset path
    dataset = YOLOAdapter(root_dir=Path("./mock_dataset"))
    
    print("🛡️ Running VisiOps F1 & FF6 Spatial Consistency Engine...")
    report = await pipeline.verify_dataset(dataset)
    
    print("\\n=== 📊 VisiOps Assurance Report ===")
    print(report.model_dump_json(indent=2))

if __name__ == "__main__":
    asyncio.run(main())
