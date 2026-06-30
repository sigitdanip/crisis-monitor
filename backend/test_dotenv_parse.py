
import os
from dotenv import load_dotenv
load_dotenv(".env", override=True)
print("VAL:", repr(os.environ.get("ACLED_PASSWORD")))
