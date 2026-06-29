import os
import pytest
from pathlib import Path

@pytest.fixture(autouse=True)
def configure_db_path(request):
    node_id = request.node.nodeid
    backend_root = Path(__file__).resolve().parents[1]
    
    if "test_system_health.py" in node_id or "test_e2e_data_integrity.py" in node_id:
        # Integration/E2E tests read the live DB that the running backend writes to
        db_path = str(backend_root / "data" / "crisis.db")
    else:
        # Unit tests write to and read from an isolated test DB
        db_path = str(backend_root / "data" / "crisis_test.db")
        
    os.environ["CRISIS_DB_PATH"] = db_path
    
    # Dynamically update the imported module variable
    try:
        import src.db.database
        src.db.database.DB_PATH = db_path
    except ImportError:
        pass
