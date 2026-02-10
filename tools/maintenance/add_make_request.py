import json
import os

notebook_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../test_expired_api.ipynb"))

with open(notebook_path, "r", encoding="utf-8") as f:
    nb = json.load(f)

# Code from image
code_content = [
    "import requests\n",
    "\n",
    "headers = {\n",
    "    'accept': 'application/json',\n",
    "    'Authorization': f'Bearer {access_token}'\n",
    "}\n",
    "\n",
    "def make_request(method, url, headers=None, params=None, data=None):\n",
    "    response = None\n",
    "    \n",
    "    try:\n",
    "        if method == 'GET':\n",
    "            response = requests.get(url, headers=headers, params=params)\n",
    "        elif method == 'POST':\n",
    "            response = requests.post(url, headers=headers, params=params, json=data)\n",
    "        elif method == 'PUT':\n",
    "            response = requests.put(url, headers=headers, params=params, json=data)\n",
    "        else:\n",
    "            raise ValueError('Invalid HTTP method.')\n",
    "            \n",
    "        if response.status_code == 200:\n",
    "            return response.json()\n",
    "        else:\n",
    "            print(f\"Error: {response.status_code} - {response.text}\")\n",
    "            return None\n",
    "            \n",
    "    except Exception as e:\n",
    "        print(f\"Request failed: {e}\")\n",
    "        return None\n"
]

new_cell = {
    "cell_type": "code",
    "execution_count": None,
    "metadata": {},
    "outputs": [],
    "source": code_content
}

# Insert as the second cell (index 1), right after authentication
nb["cells"].insert(1, new_cell)

with open(notebook_path, "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1)

print(f"✅ Successfully added make_request cell to {notebook_path}")
