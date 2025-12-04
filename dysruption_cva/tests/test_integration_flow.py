import os
import shutil
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from pathlib import Path

# Import the app. 
# Note: We need to make sure sys.path is correct or run pytest from root.
from modules.api import app

client = TestClient(app)

@pytest.fixture
def mock_pipeline():
    """Mock the background task pipeline to avoid running real analysis."""
    with patch("modules.api.run_verification_pipeline") as mock:
        yield mock

def test_health_check():
    """Verify the deep health check works."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert "checks" in data
    assert data["checks"]["filesystem"] == "ok"

def test_chain_of_custody_flow(tmp_path, mock_pipeline):
    """
    End-to-End Chain of Custody Verification.
    1. Upload a file.
    2. Get the path.
    3. Start a run.
    4. Verify the EXACT path was passed to the pipeline.
    """
    # 1. Create a dummy file to upload
    file_content = b"print('Hello World')"
    filename = "test_script.py"
    
    # We use the TestClient's multipart upload
    files = {"files": (filename, file_content, "text/x-python")}
    # We also need to provide the 'paths' form field as expected by the endpoint
    data = {"paths": [filename]}

    # 2. Upload
    response = client.post("/upload", files=files, data=data)
    assert response.status_code == 200, f"Upload failed: {response.text}"
    
    upload_data = response.json()
    assert "path" in upload_data
    uploaded_path = upload_data["path"]
    
    # Verify file actually exists on disk (Integration check)
    assert os.path.exists(uploaded_path)
    
    # 3. Start Run
    # We pass the path we just got back from the upload
    run_payload = {
        "target_dir": uploaded_path,
        "spec_content": "Ensure code prints Hello World",
        "watch_mode": False,
        "generate_patches": False
    }
    
    run_response = client.post("/run", json=run_payload)
    assert run_response.status_code == 200, f"Run start failed: {run_response.text}"
    
    run_data = run_response.json()
    assert "run_id" in run_data
    
    # 4. VERIFY CHAIN OF CUSTODY
    # The mock_pipeline should have been called with the run_id
    mock_pipeline.assert_called_once()
    
    # We can't easily check the arguments passed to the background task function 
    # because it takes run_id, not target_dir. 
    # However, we can check the internal state if we mock the RunState creation 
    # OR we can trust that if the endpoint returned 200, it validated the path.
    
    # Let's verify the RunState was created correctly in the global _runs dict
    # We need to import the _runs variable from the module
    from modules.api import _runs
    
    run_id = run_data["run_id"]
    assert run_id in _runs
    
    stored_config = _runs[run_id].config
    
    # THIS IS THE CRITICAL CHECK
    # Does the config stored in memory match the path we uploaded?
    assert stored_config.target_dir == uploaded_path
    
    print(f"\n✅ Chain of Custody Verified!")
    print(f"   Uploaded Path: {uploaded_path}")
    print(f"   Stored Config: {stored_config.target_dir}")

    # Cleanup
    if os.path.exists(uploaded_path):
        shutil.rmtree(uploaded_path, ignore_errors=True)
