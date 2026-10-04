#!/usr/bin/env python3
"""
Simple HTTP server for the Campaign Monitor frontend.
Serves on http://localhost:5500 by default.

Usage:
    python serve.py
    python serve.py 8000  # Custom port
"""

import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


class FrontendHandler(SimpleHTTPRequestHandler):
    """Serve index.html for all paths (SPA behavior)."""
    
    def end_headers(self):
        """Add cache-control headers to prevent stale files."""
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()
    
    def do_GET(self):
        """Serve index.html for routes, actual files if they exist."""
        # Serve actual files
        if self.path.startswith("/") and "." in self.path.split("/")[-1]:
            # Has an extension, try to serve it
            return super().do_GET()
        
        # No extension or root, serve index.html for SPA routing
        self.path = "/index.html"
        return super().do_GET()
    
    def log_message(self, format, *args):
        """Quieter logging."""
        if "GET" in format:
            print(f"[{self.client_address[0]}] {format % args}")


def main():
    port = 5500
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port: {sys.argv[1]}")
            sys.exit(1)
    
    # Change to the frontend directory
    frontend_dir = Path(__file__).parent
    os.chdir(frontend_dir)
    
    server = HTTPServer(("127.0.0.1", port), FrontendHandler)
    print(f"Frontend serving on http://localhost:{port}")
    print(f"API configured at http://localhost:3000")
    print("Press Ctrl+C to stop")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutdown...")
        server.shutdown()


if __name__ == "__main__":
    main()
