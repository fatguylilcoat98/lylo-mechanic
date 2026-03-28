#!/usr/bin/env python3
"""
LYLO Mechanic - Project Setup
The Good Neighbor Guard
Run this script to build the entire project.
"""
import os, base64, json, sys

print("")
print("Building LYLO Mechanic...")
print("")

# Load the file manifest
script_dir = os.path.dirname(os.path.abspath(__file__))
manifest_path = os.path.join(script_dir, "lylo_files.json")

if not os.path.exists(manifest_path):
    print("ERROR: lylo_files.json not found next to this script.")
    sys.exit(1)

with open(manifest_path, "r") as f:
    files = json.load(f)

created = 0
for rel_path, b64_content in files.items():
    dir_path = os.path.dirname(rel_path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
    if b64_content:
        content = base64.b64decode(b64_content)
    else:
        content = b""
    with open(rel_path, "wb") as f:
        f.write(content)
    print(f"  + {rel_path}")
    created += 1

print("")
print(f"Done. {created} files created.")
print("")
print("Next step - run setup:")
print("  pip install flask flask-cors")
print("  cd backend")
print("  python app.py")
print("  Open: http://localhost:5050")
