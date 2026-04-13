# 1. Go to project
cd /mnt/c/Users/LENOVO/desktop/Customy

# 2. Create venv
python3 -m venv .venv

# 3. Activate venv
source .venv/bin/activate

# 4. Upgrade pip (optional but good)
pip install --upgrade pip

# 5. Install deps
pip install -r requirements.txt

# 6. Setup env file
cp .env.example .env

# 7. Edit API key
nano .env
# → add OPENAI_API_KEY=your_key

# 8. Run app
pkill -f "python3 main.py"

set -a
source .env
set +a

python3 main.py --host 0.0.0.0 --port 8080

# 9. Push Code to github
git status --short --branch
git add .
git commit -m "Describe what changed"
git push origin main