# Wrapper launcher script
import sys
import os

# Insert the nested 'ira' folder into sys.path to resolve internal imports cleanly
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ira"))

# Import the actual main module
import main as main_entry

if __name__ == "__main__":
    main_entry.main()
