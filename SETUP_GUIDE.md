# 🐍 Raha — Python Setup Guide (VS Code)

---

## What You Need Installed

| Tool | Download |
|---|---|
| Python 3.11+ | https://www.python.org/downloads/ |
| VS Code | https://code.visualstudio.com/ |

**That's it.** No MySQL, no database server — SQLite is built into Python.

---

## Step 1 — Open the Project in VS Code

Move the `raha-python` folder anywhere on your computer, then:

**File → Open Folder → select `raha-python`**

---

## Step 2 — Install the Python Extension

`Ctrl+Shift+X` → search **Python** (by Microsoft) → Install

---

## Step 3 — Create a Virtual Environment

Open the terminal inside VS Code (`Ctrl+` ` `) and run:

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac / Linux
python3 -m venv venv
source venv/bin/activate
```

You'll see `(venv)` appear in the terminal. ✅

Then tell VS Code to use it:
`Ctrl+Shift+P` → **Python: Select Interpreter** → pick the one that says `venv`

---

## Step 4 — Install Packages

```bash
pip install -r requirements.txt
```

Takes about 20–30 seconds.

---

## Step 5 — Set Your JWT Secret in .env

Open `.env` and replace the placeholder:

```env
JWT_SECRET=change_this_to_a_long_random_secret
```

Generate a real one by running this in the terminal:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Paste the output as your `JWT_SECRET`. The database section needs nothing — SQLite handles itself.

---

## Step 6 — Run the Server

```bash
python -m uvicorn app.main:app --reload --port 4000
```

You'll see:

```
✔️  SQLite database ready → raha.db
INFO:     Uvicorn running on http://0.0.0.0:4000
```

Open your browser → **http://localhost:4000** 🎉

The file `raha.db` is created automatically in your project folder on first run.

---

## Step 7 — Create Your Admin Account

In a **new terminal tab** (keep the server running), run:

```bash
python -c "
from app.database import get_db
from app.auth_utils import hash_password
conn = get_db()
conn.execute(
    'INSERT INTO users (full_name, email, password_hash, role) VALUES (?,?,?,?)',
    ('System Administrator', 'admin@raha.com', hash_password('Raha123!'), 'admin')
)
conn.commit()
conn.close()
print('Admin created! → admin@raha.com / Raha123!')
"
```

---

## All Pages

| URL | Page | Access |
|---|---|---|
| http://localhost:4000/ | Home | Everyone |
| http://localhost:4000/login | Login | Guests |
| http://localhost:4000/signup | Sign Up | Guests |
| http://localhost:4000/analyze | Upload & Analyze | Researchers |
| http://localhost:4000/results | Scan History | Researchers |
| http://localhost:4000/profile | Profile Editor | Logged-in |
| http://localhost:4000/learn | Tutorials | Researchers |
| http://localhost:4000/contact | Contact Form | Everyone |
| http://localhost:4000/about | About | Guests |
| http://localhost:4000/admin/dashboard | Admin Overview | Admin only |
| http://localhost:4000/admin/users | User Management | Admin only |
| http://localhost:4000/admin/logs | Activity Logs | Admin only |
| http://localhost:4000/docs | Auto API Docs | Dev use |

---

## Plugging In Your AI Model Later

Open `app/routes/scans.py` and find this comment:

```python
# ── Replace this block with your real model later ──
seg_path = UPLOAD_DIR / (dest.stem + "_seg" + dest.suffix)
shutil.copy(dest, seg_path)
# ───────────────────────────────────────────────────
```

Replace it with:

```python
from app.model import run_segmentation
seg_path = run_segmentation(dest)
```

Then create `app/model.py` with your model logic.

---

## Common Errors

| Error | Fix |
|---|---|
| `ModuleNotFoundError` | Run `venv\Scripts\activate` first, then retry |
| `Address already in use` | Change port: `--port 8000` |
| `raha.db` permission error | Make sure you're running from the `raha-python/` folder |
| Page loads but API fails | Check browser console (F12) — usually a 401 = not logged in |

---

## Recommended VS Code Extensions

- **Python** — language support
- **Pylance** — autocomplete  
- **SQLite Viewer** — browse your `raha.db` file visually inside VS Code
- **Thunder Client** — test API endpoints like Postman
- **Jinja** — syntax highlighting for HTML templates
