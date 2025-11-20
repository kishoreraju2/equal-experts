#!/usr/bin/env python3
"""
Simple HTTP server that fetches GitHub user's public Gists with caching and pagination.
Usage: python server.py
Then visit: http://localhost:8080/<username>?page=1&per_page=10
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.error
import urllib.parse
import json
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List


class Cache:
    """Simple in-memory cache with TTL support"""
    
    def __init__(self, ttl_seconds: int = 300):
        self.cache: Dict[str, Tuple[any, float]] = {}
        self.ttl = ttl_seconds
    
    def get(self, key: str) -> Optional[any]:
        """Get value from cache if not expired"""
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return value
            else:
                # Remove expired entry
                del self.cache[key]
        return None
    
    def set(self, key: str, value: any) -> None:
        """Store value in cache with current timestamp"""
        self.cache[key] = (value, time.time())
    
    def clear(self) -> None:
        """Clear all cached entries"""
        self.cache.clear()
    
    def remove(self, key: str) -> None:
        """Remove specific key from cache"""
        if key in self.cache:
            del self.cache[key]
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        current_time = time.time()
        valid_entries = sum(
            1 for _, timestamp in self.cache.values()
            if current_time - timestamp < self.ttl
        )
        return {
            'total_entries': len(self.cache),
            'valid_entries': valid_entries,
            'expired_entries': len(self.cache) - valid_entries,
            'ttl_seconds': self.ttl
        }


# Global cache instance (5 minute TTL)
gist_cache = Cache(ttl_seconds=300)


class GistHandler(BaseHTTPRequestHandler):
    
    def parse_query_params(self) -> Dict[str, str]:
        """Parse query parameters from URL"""
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        # Convert lists to single values
        return {k: v[0] if v else '' for k, v in params.items()}
    
    def get_pagination_params(self, params: Dict[str, str]) -> Tuple[int, int]:
        """Extract and validate pagination parameters"""
        try:
            page = int(params.get('page', '1'))
            per_page = int(params.get('per_page', '30'))
            
            # Validate ranges
            page = max(1, min(page, 100))  # GitHub API limit
            per_page = max(1, min(per_page, 100))  # GitHub API limit
            
            return page, per_page
        except ValueError:
            return 1, 30  # Defaults
    
    def fetch_gists_from_github(self, username: str, page: int, per_page: int) -> List[Dict]:
        """Fetch gists from GitHub API with pagination"""
        api_url = f'https://api.github.com/users/{username}/gists?page={page}&per_page={per_page}'
        req = urllib.request.Request(
            api_url,
            headers={'User-Agent': 'Python-Gist-Viewer'}
        )
        
        with urllib.request.urlopen(req) as response:
            # Get rate limit headers
            rate_limit_remaining = response.headers.get('X-RateLimit-Remaining')
            rate_limit_reset = response.headers.get('X-RateLimit-Reset')
            
            gists = json.loads(response.read().decode())
            
            return gists, rate_limit_remaining, rate_limit_reset
    
    def format_gists(self, gists: List[Dict]) -> List[Dict]:
        """Format gist data for response"""
        gist_list = []
        for gist in gists:
            gist_info = {
                'id': gist['id'],
                'description': gist['description'] or 'No description',
                'url': gist['html_url'],
                'files': list(gist['files'].keys()),
                'file_count': len(gist['files']),
                'public': gist['public'],
                'created_at': gist['created_at'],
                'updated_at': gist['updated_at'],
                'comments': gist.get('comments', 0)
            }
            gist_list.append(gist_info)
        return gist_list
    
    def do_GET(self):
        # Parse path and query parameters
        parsed_url = urllib.parse.urlparse(self.path)
        username = parsed_url.path.strip('/')
        params = self.parse_query_params()
        
        # Handle special endpoints
        if username == '' or username == 'index.html':
            self.handle_root()
            return
        
        if username == 'cache':
            self.handle_cache_stats()
            return
        
        if username.startswith('cache/clear'):
            self.handle_cache_clear()
            return
        
        # Get pagination parameters
        page, per_page = self.get_pagination_params(params)
        
        # Check if we want to bypass cache
        bypass_cache = params.get('no_cache', '').lower() == 'true'
        
        # Create cache key
        cache_key = f"{username}:page{page}:per_page{per_page}"
        
        # Try to get from cache
        if not bypass_cache:
            cached_data = gist_cache.get(cache_key)
            if cached_data:
                self.send_cached_response(cached_data)
                return
        
        # Fetch gists from GitHub API
        try:
            gists, rate_remaining, rate_reset = self.fetch_gists_from_github(username, page, per_page)
            
            # Format response
            gist_list = self.format_gists(gists)
            
            response_data = {
                'username': username,
                'page': page,
                'per_page': per_page,
                'gist_count': len(gist_list),
                'gists': gist_list,
                'pagination': {
                    'current_page': page,
                    'per_page': per_page,
                    'has_next': len(gist_list) == per_page,
                    'next_page': page + 1 if len(gist_list) == per_page else None,
                    'prev_page': page - 1 if page > 1 else None
                },
                'rate_limit': {
                    'remaining': rate_remaining,
                    'reset_at': datetime.fromtimestamp(int(rate_reset)).isoformat() if rate_reset else None
                },
                'cache': {
                    'hit': False,
                    'ttl_seconds': gist_cache.ttl
                }
            }
            
            # Store in cache
            gist_cache.set(cache_key, response_data)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('X-Cache-Status', 'MISS')
            self.end_headers()
            self.wfile.write(json.dumps(response_data, indent=2).encode())
            
        except urllib.error.HTTPError as e:
            self.handle_http_error(e, username)
        except Exception as e:
            self.handle_server_error(e)
    
    def send_cached_response(self, cached_data: Dict):
        """Send cached response with cache hit headers"""
        cached_data['cache']['hit'] = True
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('X-Cache-Status', 'HIT')
        self.end_headers()
        self.wfile.write(json.dumps(cached_data, indent=2).encode())
    
    def handle_root(self):
        """Handle root path"""
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        html_content = """
            <html>
            <head>
                <title>GitHub Gists Viewer</title>
                <style>
                    body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
                    code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }
                    .endpoint { margin: 20px 0; padding: 15px; background: #f9f9f9; border-left: 4px solid #007bff; }
                </style>
            </head>
            <body>
                <h1>GitHub Gists Viewer API</h1>
                <p>Fetch GitHub user's public Gists with caching and pagination support.</p>
                
                <div class="endpoint">
                    <h3>GET /<username></h3>
                    <p>Fetch gists for a user</p>
                    <p><strong>Query Parameters:</strong></p>
                    <ul>
                        <li><code>page</code> - Page number (default: 1, max: 100)</li>
                        <li><code>per_page</code> - Results per page (default: 30, max: 100)</li>
                        <li><code>no_cache</code> - Bypass cache (true/false)</li>
                    </ul>
                    <p><strong>Example:</strong> <a href="/octocat?page=1&per_page=10">/octocat?page=1&per_page=10</a></p>
                </div>
                
                <div class="endpoint">
                    <h3>GET /cache</h3>
                    <p>View cache statistics</p>
                    <p><strong>Example:</strong> <a href="/cache">/cache</a></p>
                </div>
                
                <div class="endpoint">
                    <h3>GET /cache/clear</h3>
                    <p>Clear all cached entries</p>
                    <p><strong>Example:</strong> <a href="/cache/clear">/cache/clear</a></p>
                </div>
                
                <h3>Features</h3>
                <ul>
                    <li>✅ In-memory caching (5 minute TTL)</li>
                    <li>✅ Pagination support</li>
                    <li>✅ GitHub API rate limit tracking</li>
                    <li>✅ Cache bypass option</li>
                    <li>✅ Cache statistics</li>
                </ul>
            </body>
            </html>
        """
        self.wfile.write(html_content.encode('utf-8'))
    
    def handle_cache_stats(self):
        """Handle cache statistics endpoint"""
        stats = gist_cache.get_stats()
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(stats, indent=2).encode())
    
    def handle_cache_clear(self):
        """Handle cache clear endpoint"""
        entries_before = len(gist_cache.cache)
        gist_cache.clear()
        
        response = {
            'message': 'Cache cleared successfully',
            'entries_removed': entries_before
        }
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response, indent=2).encode())
    
    def handle_http_error(self, error: urllib.error.HTTPError, username: str):
        """Handle HTTP errors from GitHub API"""
        if error.code == 404:
            self.send_response(404)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {'error': f'User "{username}" not found'}
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(error.code)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = {'error': f'GitHub API error: {error.code}'}
            self.wfile.write(json.dumps(response).encode())
    
    def handle_server_error(self, error: Exception):
        """Handle internal server errors"""
        self.send_response(500)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        response = {'error': f'Server error: {str(error)}'}
        self.wfile.write(json.dumps(response).encode())
    
    def log_message(self, format, *args):
        # Custom log format with cache status
        print(f"[{self.log_date_time_string()}] {format % args}")


def run_server(port=8080):
    server_address = ('', port)
    httpd = HTTPServer(server_address, GistHandler)
    print(f'Server running on http://localhost:{port}')
    print(f'Cache TTL: {gist_cache.ttl} seconds')
    print(f'Try: http://localhost:{port}/octocat?page=1&per_page=5')
    print('Press Ctrl+C to stop the server')
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down server...')
        httpd.shutdown()


if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 8080))
    run_server(port)