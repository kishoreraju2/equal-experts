#!/usr/bin/env python3
"""
Automated integration tests for GitHub Gists server API.
Tests against real server with actual HTTP requests.

Run with: python test_server.py
"""

import unittest
import json
import time
import urllib.request
import urllib.error
from http.server import HTTPServer
from threading import Thread
import sys

# Import the server module
import server


class TestGistsAPIIntegration(unittest.TestCase):
    """Integration tests with real HTTP server and GitHub API"""
    
    @classmethod
    def setUpClass(cls):
        """Start test server in background thread"""
        cls.port = 8889
        cls.base_url = f'http://localhost:{cls.port}'
        cls.server = HTTPServer(('localhost', cls.port), server.GistHandler)
        cls.server_thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(1)  # Give server time to start
        print(f"\n[SETUP] Test server started on port {cls.port}")
    
    @classmethod
    def tearDownClass(cls):
        """Stop test server and print summary"""
        cls.server.shutdown()
        cls.server.server_close()
        print(f"\n[TEARDOWN] Test server stopped")
    
    def setUp(self):
        """Clear cache before each test"""
        try:
            urllib.request.urlopen(f'{self.base_url}/cache/clear')
            time.sleep(0.1)
        except:
            pass
    
    def make_request(self, path: str, expected_status: int = 200):
        """Helper to make HTTP request and return parsed JSON"""
        url = f'{self.base_url}{path}'
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as response:
                self.assertEqual(response.status, expected_status, 
                               f"Expected status {expected_status}, got {response.status}")
                
                content_type = response.headers.get('Content-Type', '')
                body = response.read().decode()
                
                if not body:
                    raise ValueError(f"Empty response body from {url}")
                
                if 'application/json' in content_type:
                    try:
                        return json.loads(body), response.headers
                    except json.JSONDecodeError as e:
                        print(f"Failed to parse JSON from {url}")
                        print(f"Response body: {body[:200]}...")
                        raise
                return body, response.headers
        except urllib.error.HTTPError as e:
            if e.code == expected_status:
                body = e.read().decode()
                if not body:
                    raise ValueError(f"Empty error response body from {url}")
                return json.loads(body), e.headers
            raise
        except urllib.error.URLError as e:
            raise Exception(f"Network error accessing {url}: {e}")
    
    def test_01_root_endpoint(self):
        """Test 1: Root endpoint returns HTML"""
        print("\n[TEST 1] Testing root endpoint...")
        body, headers = self.make_request('/')
        
        self.assertIn('GitHub Gists Viewer', body)
        self.assertIn('text/html', headers.get('Content-Type', ''))
        print("✓ Root endpoint returns HTML page")
    
    def test_02_valid_user_basic(self):
        """Test 2: Fetch gists for valid user (octocat)"""
        print("\n[TEST 2] Testing valid user (octocat)...")
        
        # Retry mechanism for network issues
        max_retries = 3
        for attempt in range(max_retries):
            try:
                data, headers = self.make_request('/octocat')
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"  Retry {attempt + 1}/{max_retries - 1}: {str(e)[:50]}")
                    time.sleep(1)
                else:
                    raise
        
        # Validate response structure
        self.assertIn('username', data)
        self.assertEqual(data['username'], 'octocat')
        self.assertIn('gist_count', data)
        self.assertIn('gists', data)
        self.assertIsInstance(data['gists'], list)
        
        # Validate cache status
        self.assertIn('cache', data)
        self.assertFalse(data['cache']['hit'], "First request should be cache MISS")
        self.assertEqual(headers.get('X-Cache-Status'), 'MISS')
        
        print(f"✓ Found {data['gist_count']} gists for octocat")
        print(f"✓ Cache status: {headers.get('X-Cache-Status')}")
    
    def test_03_response_structure(self):
        """Test 03: Complete response structure validation"""
        print("\n[TEST 03] Validating complete response structure...")
        
        data, headers = self.make_request('/octocat?page=1&per_page=5')
        
        # Top-level fields
        required_fields = ['username', 'page', 'per_page', 'gist_count', 'gists', 
                          'pagination', 'rate_limit', 'cache']
        for field in required_fields:
            self.assertIn(field, data, f"Missing field: {field}")
        
        # Pagination structure
        pagination_fields = ['current_page', 'per_page', 'has_next', 'next_page', 'prev_page']
        for field in pagination_fields:
            self.assertIn(field, data['pagination'], f"Missing pagination field: {field}")
        
        # Rate limit structure
        self.assertIn('remaining', data['rate_limit'])
        
        # Cache structure
        self.assertIn('hit', data['cache'])
        self.assertIn('ttl_seconds', data['cache'])
        
        # Gist structure (if gists exist)
        if data['gists']:
            gist = data['gists'][0]
            gist_fields = ['id', 'description', 'url', 'files', 'file_count', 
                          'public', 'created_at', 'updated_at', 'comments']
            for field in gist_fields:
                self.assertIn(field, gist, f"Missing gist field: {field}")
        
        print("✓ All required fields present")
        print("✓ Response structure is valid")

def run_tests():
    """Run all tests and display summary"""
    print("="*70)
    print("GITHUB GISTS API - AUTOMATED INTEGRATION TEST SUITE")
    print("="*70)
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestGistsAPIIntegration)
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"Tests Run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("="*70)
    
    # Return exit code
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(run_tests())
