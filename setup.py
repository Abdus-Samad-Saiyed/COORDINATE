#!/usr/bin/env python3
"""
Campus Nexus — Root Database Setup & Interactive Management Runner.

Usage:
    python setup.py                     # Launch interactive menu
    python setup.py --migrate           # Run migrations non-interactively
    python setup.py --check-migrations  # Check for unapplied migrations
    python setup.py --add-user --admin  # Add admin user non-interactively
"""

import sys
from pathlib import Path

# Delegate directly to scripts/setup_db.py
ROOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT_DIR))

from scripts.setup_db import main

if __name__ == "__main__":
    main()
