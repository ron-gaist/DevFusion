import os
import sys
from pathlib import Path

# Add project root directory to Python path
project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root) 