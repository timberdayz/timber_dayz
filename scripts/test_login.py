"""Test login API endpoints."""
import urllib.request
import json


def test_login(username, password):
    data = json.dumps({'username': username, 'password': password, 'remember_me': False}).encode()
    req = urllib.request.Request(
        'http://localhost:8001/api/auth/login',
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        r = urllib.request.urlopen(req, timeout=10)
        resp = json.loads(r.read().decode())
        user = resp.get('user', {})
        if isinstance(user, dict):
            print(f"[OK] {username}: login success - id={user.get('user_id')}, status={user.get('status')}, roles={[r.get('role_code') for r in user.get('roles', [])]}")
        else:
            print(f"[OK] {username}: login success - response keys: {list(resp.keys())}")
    except urllib.error.HTTPError as e:
        resp = e.read().decode('utf-8', errors='replace')
        print(f"[FAIL] {username}: HTTP {e.code} - {resp[:300]}")
    except Exception as e:
        print(f"[ERROR] {username}: {e}")


if __name__ == '__main__':
    test_login('admin', 'Admin@123456')
    test_login('xihong', 'Xihong@2025')
