import os
import sys
import traceback

# Add project root directory to sys.path for serverless execution
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from app import create_app
    # Vercel serverless function entrypoint
    app = create_app()
except Exception as boot_err:
    traceback.print_exc(file=sys.stderr)
    from flask import Flask
    app = Flask(__name__)

    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def _startup_error(path):
        return f"Application startup error ({type(boot_err).__name__}). Check Vercel Runtime Logs for details.", 500

if __name__ == '__main__':
    app.run()
