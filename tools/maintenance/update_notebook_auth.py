import json
import os

notebook_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../test_expired_api.ipynb"))

with open(notebook_path, "r", encoding="utf-8") as f:
    nb = json.load(f)

# Update the first cell with a simpler, more robust approach
new_source = [
    "import sys\n",
    "import os\n",
    "\n",
    "# Add root directory to path to import core modules\n",
    "sys.path.insert(0, os.path.abspath(\"..\"))\n",
    "\n",
    "import requests\n",
    "\n",
    "# Reload the authentication module to pick up latest changes\n",
    "import importlib\n",
    "if 'core.authentication' in sys.modules:\n",
    "    import lib.core.authentication\n",
    "    importlib.reload(core.authentication)\n",
    "\n",
    "from lib.core.authentication import check_existing_token, perform_authentication, save_access_token, get_access_token\n",
    "\n",
    "# Authenticate\n",
    "if check_existing_token():\n",
    "    print(\"✅ Valid token found.\")\n",
    "    access_token = get_access_token()\n",
    "    if access_token:\n",
    "        print(f\"Token length: {len(access_token)}\")\n",
    "    else:\n",
    "        print(\"⚠️ Token file exists but couldn't read token\")\n",
    "        access_token = \"\"\n",
    "else:\n",
    "    print(\"🔐 Token missing/expired. Authenticating...\")\n",
    "    try:\n",
    "        access_token = perform_authentication()\n",
    "        save_access_token(access_token)\n",
    "        print(\"✅ Authentication successful.\")\n",
    "    except Exception as e:\n",
    "        print(f\"❌ Authentication failed: {e}\")\n",
    "        access_token = \"\"\n"
]

nb["cells"][0]["source"] = new_source
nb["cells"][0]["outputs"] = []  # Clear old outputs
nb["cells"][0]["execution_count"] = None  # Reset execution count

with open(notebook_path, "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1)

print(f"✅ Successfully updated {notebook_path}")
print("📝 The notebook now includes importlib.reload() to pick up the latest authentication.py changes")
print("🔄 Please re-run the first cell in your Jupyter notebook")
