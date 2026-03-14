import os
import sys

# load dotenv 
from dotenv import load_dotenv
_root_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_root_dir, ".env.local"), override=False)

print("ENABLE_CLOUD_COLLECTOR =", os.getenv("ENABLE_CLOUD_COLLECTOR"))
from backend.app.services.collector import is_cloud_collector_enabled
print("is_cloud_collector_enabled() =", is_cloud_collector_enabled())
