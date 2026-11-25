# Support Desk Triage Agent

## Part 1 setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and set GEMINI_API_KEY

python seed.py
python test_key.py
```

The API key is read from the `GEMINI_API_KEY` environment variable (loaded through `.env`) and must never be committed.
