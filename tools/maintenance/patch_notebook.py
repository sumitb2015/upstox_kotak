import json
import os

notebook_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../test_expired_api.ipynb"))

with open(notebook_path, "r", encoding="utf-8") as f:
    nb = json.load(f)

# The target cell is the first one (index 0) based on the file view
# We want to replace the import and the reading logic
cell = nb["cells"][0]
source = cell["source"]

new_source = []
for line in source:
    if "from lib.core.authentication import" in line:
        new_source.append("from lib.core.authentication import check_existing_token, perform_authentication, save_access_token, get_access_token\n")
    elif "with open(\"../core/accessToken.txt\"" in line:
        continue # Skip this line
    elif "access_token = f.read().strip()" in line:
        new_source.append("    access_token = get_access_token()\n")
    else:
        new_source.append(line)

cell["source"] = new_source

with open(notebook_path, "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1)

print(f"Successfully patched {notebook_path}")
