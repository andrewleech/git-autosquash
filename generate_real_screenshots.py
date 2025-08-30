#!/usr/bin/env python3
"""Generate all screenshots using the realistic screenshot creation system.

This is a simple wrapper script that calls the main screenshot generation
functionality from create_realistic_screenshots.py.
"""

import sys
from pathlib import Path

# Add the current directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent))

try:
    from create_realistic_screenshots import main

    if __name__ == "__main__":
        main()

except ImportError as e:
    print(f"Error importing screenshot creation module: {e}")
    print(
        "Make sure create_realistic_screenshots.py exists and dependencies are installed"
    )
    sys.exit(1)
except Exception as e:
    print(f"Error generating screenshots: {e}")
    sys.exit(1)
