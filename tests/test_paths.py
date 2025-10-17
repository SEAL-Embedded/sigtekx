import pytest
from pathlib import Path

# Import the module we want to test
from ionosense_hpc.utils import paths 

def test_repo_root_not_found(monkeypatch, tmp_path: Path):
    """
    Tests that _repo_root raises FileNotFoundError when pyproject.toml
    is not found in any parent directory.
    """
    
    # 1. Create a fake 'paths.py' file deep inside the temporary directory.
    #    The _repo_root function will start its search from here.
    fake_file_path = tmp_path / "fake_project" / "src" / "paths.py"
    fake_file_path.parent.mkdir(parents=True, exist_ok=True)
    fake_file_path.touch() # Create the fake file

    # 2. Patch the __file__ attribute *within the paths module*
    #    This controls the starting point for the function's search.
    monkeypatch.setattr(paths, "__file__", str(fake_file_path))

    # 3. Assert that the function raises the expected error
    #    The 'match' argument checks that the error message is correct.
    with pytest.raises(FileNotFoundError, match="Project root not found"):
        paths._repo_root()