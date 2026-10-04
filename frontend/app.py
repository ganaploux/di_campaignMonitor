"""
Campaign Monitor Frontend - Flask server
Serves the SPA with proper routing and caching headers.
"""

from flask import Flask, send_file, send_from_directory
from pathlib import Path
import sys
import os

app = Flask(__name__)

# Get the directory where this script is located
FRONTEND_DIR = Path(__file__).parent


@app.route("/")
def index():
    """Serve index.html for root."""
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:filename>")
def serve_file(filename):
    """Serve static files or fall back to index.html for SPA routing."""
    file_path = (FRONTEND_DIR / filename).resolve()
    
    # Prevent directory traversal
    try:
        if not str(file_path).startswith(str(FRONTEND_DIR.resolve())):
            return "Not found", 404
    except ValueError:
        return "Not found", 404
    
    # If it's a file with an extension, serve it as-is
    if file_path.is_file() and "." in file_path.name:
        response = send_from_directory(FRONTEND_DIR, filename)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    
    # Otherwise, serve index.html for SPA routing
    return send_from_directory(FRONTEND_DIR, "index.html")


if __name__ == "__main__":
    port = 5500
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port: {sys.argv[1]}")
            sys.exit(1)
    
    print(f"Frontend serving on http://localhost:{port}")
    print(f"API configured at http://localhost:3000")
    print("Press Ctrl+C to stop")
    
    app.run(host="127.0.0.1", port=port, debug=False)
