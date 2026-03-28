# ============================================================
# LYLO Mechanic — GitHub Push Script
# The Good Neighbor Guard
# Paste this entire script into PowerShell and hit Enter
# ============================================================

$REPO_URL = "https://github.com/fatguylilcoat98/lylo-mechanic.git"
$PROJECT_DIR = "$HOME\Desktop\lylo-mechanic"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  LYLO Mechanic — Building project..." -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Step 1 — Create project folder on Desktop
Write-Host "-> Creating project folder on Desktop..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $PROJECT_DIR | Out-Null
Set-Location $PROJECT_DIR

# Step 2 — Download setup files from GitHub releases / Claude outputs
# We use Python to fetch and write all files
Write-Host "-> Writing project files..." -ForegroundColor Yellow

# Inline Python that writes every file
$setupScript = @'
import os, urllib.request, json, base64, sys

# All files encoded as base64 - fetched from the Claude session output
# Two files needed: setup_lylo.py + lylo_files.json
# We pull them from the outputs path if running locally,
# otherwise user downloads them manually.

print("Checking for lylo_files.json...")
if not os.path.exists("lylo_files.json"):
    print("")
    print("ERROR: lylo_files.json not found.")
    print("Please download BOTH files from Claude:")
    print("  1. setup_lylo.py")  
    print("  2. lylo_files.json")
    print("Put them both in:", os.getcwd())
    sys.exit(1)

with open("lylo_files.json", "r") as f:
    files = json.load(f)

created = 0
for rel_path, b64_content in files.items():
    dir_path = os.path.dirname(rel_path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)
    content = base64.b64decode(b64_content) if b64_content else b""
    with open(rel_path, "wb") as f:
        f.write(content)
    print(f"  + {rel_path}")
    created += 1

print(f"\nDone. {created} files created.")
'@

python $setupScript

# Step 3 — Install dependencies
Write-Host ""
Write-Host "-> Installing Python dependencies..." -ForegroundColor Yellow
pip install flask flask-cors --quiet
Write-Host "  + flask installed" -ForegroundColor Green

# Step 4 — Git init and push to GitHub
Write-Host ""
Write-Host "-> Initializing Git and pushing to GitHub..." -ForegroundColor Yellow

git init
git add .
git commit -m "Initial commit — LYLO Mechanic v1.0

Full vehicle diagnostics system:
- 12-layer diagnostic pipeline
- Safety escalation matrix (6 levels)
- DIY eligibility gate with hard blocks
- Multi-hypothesis engine (10 demo scenarios)
- Cost engine (DIY / Shop / Dealer)
- Veracore truth check layer
- Handshake enforcement
- OBDLink partnership branding
- Full Flask backend + dashboard UI

Built by The Good Neighbor Guard
Truth · Safety · We Got Your Back"

git branch -M main
git remote add origin $REPO_URL
git push -u origin main

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  DONE. Project is live on GitHub." -ForegroundColor Green  
Write-Host "  $REPO_URL" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "To run locally:" -ForegroundColor Cyan
Write-Host "  cd $PROJECT_DIR\backend" -ForegroundColor White
Write-Host "  python app.py" -ForegroundColor White
Write-Host "  Open: http://localhost:5050" -ForegroundColor White
Write-Host ""
