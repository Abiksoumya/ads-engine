import sys
import os
from dotenv import load_dotenv

# Load .env before any tests run
load_dotenv()

# Add backend/ to Python path
sys.path.insert(0, os.path.dirname(__file__))