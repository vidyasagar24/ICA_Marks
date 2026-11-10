import os
import sys

# Add project root directory to sys.path for serverless execution
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app

# Vercel serverless function entrypoint (must stay top-level for @vercel/python AST detection)
app = create_app()

if __name__ == '__main__':
    app.run()
