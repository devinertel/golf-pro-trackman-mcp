import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import server

class DataTests(unittest.TestCase):
    def test_summary_missing_normalized_drills_and_units(self):
        node = {'id': 'a', 'strokes': [
            {'club': '7i', 'tags': [], 'measurement': {'carry': 100, 'clubSpeed': 30, 'faceToPath': 0}},
            {'club': '7i', 'tags': [], 'measurement': {'carry': 120, 'clubSpeed': None}},
            {'club': '7i', 'tags': [{'value': 'drill'}], 'measurement': {'carry': 20}},
        ]}
        out = server.summarize(node)
        self.assertEqual(len(out['groups']), 2)
        first = out['groups'][0]['metrics']
        self.assertAlmostEqual(first['carry']['mean'], 110 * 1.0936132983)
        self.assertAlmostEqual(first['carry']['sample_sd'], 14.1421356237 * 1.0936132983)
        self.assertEqual(first['clubSpeed']['missing_count'], 1)
        self.assertEqual(first['faceToPath']['valid_count'], 1)
        self.assertIsNone(server.summarize(node, True)['groups'][0]['metrics']['carry']['mean'])

class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
    async def asyncTearDown(self):
        self.tmp.cleanup()

    async def test_pending_slowdown_success_and_private_cache(self):
        replies = [httpx.Response(200, json={'device_code': 'PRIVATE', 'user_code': 'ABC', 'verification_uri': server.AUTH + '/device', 'expires_in': 600, 'interval': 1}), httpx.Response(400, json={'error': 'slow_down'}), httpx.Response(200, json={'access_token': 'SECRET', 'refresh_token': 'REFRESH', 'expires_in': 3600})]
        c = server.Trackman(self.state, httpx.MockTransport(lambda r: replies.pop(0)))
        info = await c.begin()
        self.assertNotIn('PRIVATE', json.dumps(info))
        self.assertEqual((await c.finish())['status'], 'pending')
        pending = c.read('pending.json'); pending['next_poll'] = 0; c.save('pending.json', pending)
        result = await c.finish()
        self.assertEqual(result['retry_after_seconds'], 6)
        pending = c.read('pending.json'); pending['next_poll'] = 0; c.save('pending.json', pending)
        self.assertEqual((await c.finish())['status'], 'connected')
        self.assertEqual(os.stat(self.state / 'tokens.json').st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(self.state).st_mode & 0o777, 0o700)
        self.assertFalse((self.state / 'pending.json').exists())

    async def test_refresh_preserves_refresh_token_and_pagination(self):
        seen = []
        def handler(req):
            if req.url.path == '/connect/token':
                return httpx.Response(200, json={'access_token': 'NEW', 'expires_in': 3600})
            seen.append(json.loads(req.content))
            return httpx.Response(200, json={'data': {'me': {'activities': {'items': [{'id': 'x'}], 'totalCount': 2, 'pageInfo': {'hasNextPage': True}}}}})
        c = server.Trackman(self.state, httpx.MockTransport(handler))
        c.save('tokens.json', {'access_token': 'OLD', 'refresh_token': 'R', 'expires_at': 0})
        page = await c.activities('2026-10-01', skip=4, limit=1)
        self.assertEqual(page['next_skip'], 5)
        self.assertEqual(c.read('tokens.json')['refresh_token'], 'R')
        self.assertEqual(seen[0]['variables']['timeFrom'], '2026-10-01T00:00:00+00:00')

    async def test_partial_graphql_is_rejected_without_leaking_errors(self):
        c = server.Trackman(self.state, httpx.MockTransport(lambda r: httpx.Response(200, json={'data': {'node': {'strokes': []}}, 'errors': [{'message': 'SECRET'}]})))
        c.save('tokens.json', {'access_token': 'SECRET', 'expires_at': time.time() + 5000})
        with self.assertRaises(server.TrackmanError) as e:
            await c.session('x')
        self.assertNotIn('SECRET', str(e.exception))

    async def test_unexpected_login_host_rejected(self):
        c = server.Trackman(self.state, httpx.MockTransport(lambda r: httpx.Response(200, json={'device_code': 'x', 'verification_uri': 'https://evil.example', 'user_code': 'x', 'expires_in': 60})))
        with self.assertRaises(server.TrackmanError):
            await c.begin()
        self.assertFalse((self.state / 'pending.json').exists())

    async def test_mcp_real_stdio_handshake_and_tool_calls(self):
        params = StdioServerParameters(command=sys.executable, args=[str(Path(server.__file__))], env={**os.environ, 'GOLF_PRO_STATE_DIR': str(self.state)})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                self.assertEqual(len(listed.tools), 6)
                status = await session.call_tool('connection_status', {})
                self.assertFalse(status.isError)
                failed = await session.call_tool('list_activities', {})
                self.assertTrue(failed.isError)
                self.assertIn('Not connected', failed.content[0].text)

if __name__ == '__main__':
    unittest.main()
