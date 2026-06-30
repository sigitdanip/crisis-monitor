import os
import httpx
from dotenv import load_dotenv

# Load environment
load_dotenv(".env", override=True)

email = os.environ.get("ACLED_EMAIL")
password = os.environ.get("ACLED_PASSWORD")

print("Raw from env:")
print(f"email: {email}")
print(f"password: {repr(password)}")

# If password has single quotes or double quotes, strip them
if password and (password.startswith("'") and password.endswith("'")):
    password = password[1:-1]
elif password and (password.startswith('"') and password.endswith('"')):
    password = password[1:-1]

print("Cleaned password:")
print(f"password: {repr(password)}")

# Let's perform the login request
print("\nPerforming ACLED OAuth login...")
try:
    r = httpx.post(
        "https://acleddata.com/oauth/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "username": email,
            "password": password,
            "grant_type": "password",
            "client_id": "acled",
            "scope": "authenticated",
        },
        timeout=15.0
    )
    print("Response status code:", r.status_code)
    print("Response text:", r.text)
except Exception as e:
    print("Error occurred:", str(e))
