"""End-to-end smoke test script for RecallAI API.

Validates the full lifecycle per CLAUDE.md:
  save → process → search → open → delete
"""

import asyncio
import os
import sys

import httpx

API_URL = os.environ.get("API_URL", "http://localhost:8000/api/v1")
TEST_EMAIL = f"smoke_test_{os.getpid()}@example.com"
TEST_PASSWORD = "StrongTestPassword123!"
SAMPLE_URL = "https://example.com/test-page"


async def run_smoke_test():
    print("=" * 60)
    print("RecallAI End-to-End Smoke Test")
    print(f"Target API: {API_URL}")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1. Register test user
        print("1. Registering test user...")
        reg_resp = await client.post(
            f"{API_URL}/auth/register",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD, "display_name": "Smoke Tester"},
        )
        if reg_resp.status_code not in (200, 201):
            print(f"  Registration error: {reg_resp.status_code} - {reg_resp.text}")
            return False
        user_id = reg_resp.json()["id"]
        print(f"  ✓ User registered: {user_id}")

        # 2. Login to get token
        print("2. Logging in...")
        login_resp = await client.post(
            f"{API_URL}/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        token = login_resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("  ✓ Authenticated with JWT")

        # 3. Save bookmark (POST /bookmarks)
        print("3. Saving bookmark...")
        bm_resp = await client.post(
            f"{API_URL}/bookmarks",
            headers=headers,
            json={
                "url": SAMPLE_URL,
                "title": "Smoke Test Page",
                "notes": "Testing automated smoke flow",
                "tags": ["testing", "smoke"],
            },
        )
        assert bm_resp.status_code in (200, 201), f"Save failed: {bm_resp.text}"
        bm = bm_resp.json()
        bm_id = bm["id"]
        print(f"  ✓ Bookmark saved: {bm_id} (status: {bm['status']})")

        # 4. Check status & process
        print("4. Checking bookmark status...")
        status_resp = await client.get(
            f"{API_URL}/bookmarks/{bm_id}/status",
            headers=headers,
        )
        assert status_resp.status_code == 200
        print(f"  ✓ Status retrieved: {status_resp.json()['status']}")

        # 5. Hybrid search (GET /search?q=)
        print("5. Running hybrid search...")
        search_resp = await client.get(
            f"{API_URL}/search",
            headers=headers,
            params={"q": "smoke test page"},
        )
        assert search_resp.status_code == 200
        print(f"  ✓ Search responded with {search_resp.json()['total']} matches")

        # 6. Open / read bookmark (GET /bookmarks/{id})
        print("6. Opening bookmark details...")
        get_resp = await client.get(
            f"{API_URL}/bookmarks/{bm_id}",
            headers=headers,
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == bm_id
        print("  ✓ Bookmark details verified")

        # 7. Delete bookmark (DELETE /bookmarks/{id})
        print("7. Deleting bookmark...")
        del_resp = await client.delete(
            f"{API_URL}/bookmarks/{bm_id}",
            headers=headers,
        )
        assert del_resp.status_code in (200, 204)
        print("  ✓ Bookmark deleted")

        # Verify deletion (404)
        verify_del = await client.get(
            f"{API_URL}/bookmarks/{bm_id}",
            headers=headers,
        )
        assert verify_del.status_code == 404
        print("  ✓ Verified deletion returns 404")

    print("=" * 60)
    print("🎉 All smoke test stages passed successfully!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(run_smoke_test())
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"Smoke test failed with exception: {e}")
        sys.exit(1)
