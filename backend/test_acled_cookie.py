import os
import httpx
from dotenv import load_dotenv

load_dotenv(".env", override=True)
email = os.environ.get("ACLED_EMAIL")
password = os.environ.get("ACLED_PASSWORD")

print("Testing Cookie-based login...")
try:
    with httpx.Client(timeout=15.0) as client:
        # POST login request
        r = client.post(
            "https://acleddata.com/user/login?_format=json",
            json={"name": email, "pass": password}
        )
        print("Status code:", r.status_code)
        print("Response text:", r.text)
        
        # If successful, try reading the API
        if r.status_code == 200:
            print("Session cookies:", client.cookies)
            # Try a GET request which will automatically send session cookies
            r2 = client.get(
                "https://acleddata.com/api/acled/read",
                params={"limit": 5}
            )
            print("API response status:", r2.status_code)
            print("API response:", r2.text[:200])
except Exception as e:
    print("Error:", e)
