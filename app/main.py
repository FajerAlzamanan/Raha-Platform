"""
Raha – FastAPI Backend
Entry point: runs the server, mounts routes, and serves Jinja2 templates.
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import uvicorn, os

from app.db_setup import create_tables
from app.routes import auth, user, admin, scans, contact

app = FastAPI(title="Raha API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static",  StaticFiles(directory="app/static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"),    name="uploads")
templates = Jinja2Templates(directory="app/templates")

# ── API Routes ─────────────────────────────────────────────────────────────────
app.include_router(auth.router,    prefix="/api/auth",    tags=["auth"])
app.include_router(user.router,    prefix="/api/user",    tags=["user"])
app.include_router(admin.router,   prefix="/api/admin",   tags=["admin"])
app.include_router(scans.router,   prefix="/api/scans",   tags=["scans"])
app.include_router(contact.router, prefix="/api/contact", tags=["contact"])

# ── Startup ────────────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    create_tables()
    os.makedirs("uploads", exist_ok=True)

# ── Page Routes ────────────────────────────────────────────────────────────────
@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

@app.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request})

@app.get("/signup")
async def signup_page(request: Request):
    return templates.TemplateResponse("auth/signup.html", {"request": request})

@app.get("/analyze")
async def analyze_page(request: Request):
    return templates.TemplateResponse("user/analyze.html", {"request": request})

@app.get("/results")
async def results_page(request: Request):
    return templates.TemplateResponse("user/results.html", {"request": request})

@app.get("/profile")
async def profile_page(request: Request):
    return templates.TemplateResponse("user/profile.html", {"request": request})

@app.get("/learn")
async def learn_page(request: Request):
    return templates.TemplateResponse("user/learn.html", {"request": request})

@app.get("/contact")
async def contact_page(request: Request):
    return templates.TemplateResponse("shared/contact.html", {"request": request})

@app.get("/about")
async def about_page(request: Request):
    return templates.TemplateResponse("shared/about.html", {"request": request})

@app.get("/admin/dashboard")
async def admin_dashboard(request: Request):
    return templates.TemplateResponse("admin/dashboard.html", {"request": request})

@app.get("/admin/users")
async def admin_users(request: Request):
    return templates.TemplateResponse("admin/users.html", {"request": request})

@app.get("/admin/logs")
async def admin_logs(request: Request):
    return templates.TemplateResponse("admin/logs.html", {"request": request})

@app.get("/admin/issues")
async def admin_issues(request: Request):
    return templates.TemplateResponse("admin/issues.html", {"request": request})

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=4000, reload=True)
