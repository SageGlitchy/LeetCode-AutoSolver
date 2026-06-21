import sys
import os
import json
import asyncio
import datetime
import random
from typing import Set, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Import helper functions from existing files
from fetch_problem import fetch_daily_problem, fetch_daily_problem_details, fetch_unsolved_problems
from solver import find_local_sol, groq_solver
from submit import submit_sol, check_submission_status, load_session, save_session

app = FastAPI(title="LeetCode Auto-Solver Dashboard")

# Global status tracking
pipeline_lock = asyncio.Lock()
is_running = False
scheduler = AsyncIOScheduler()

# WS Log Redirector
class WSLogger:
    def __init__(self, original_stream):
        self.original_stream = original_stream
        self.subscribers: Set[asyncio.Queue] = set()
        self.loop = asyncio.get_event_loop()
        self.log_history: List[str] = []

    def write(self, message):
        self.original_stream.write(message)
        self.original_stream.flush()
        if message:
            self.log_history.append(message)
            if len(self.log_history) > 1000:
                self.log_history = self.log_history[-1000:]
            # Send to subscribers safely
            for q in list(self.subscribers):
                self.loop.call_soon_threadsafe(q.put_nowait, message)

    def flush(self):
        self.original_stream.flush()

# Redirect stdout and stderr
sys.stdout = WSLogger(sys.stdout)
sys.stderr = WSLogger(sys.stderr)

def get_logger() -> WSLogger:
    return sys.stdout

# Helper functions for files
def load_config():
    config_file = "config.json"
    if os.path.exists(config_file):
        try:
            with open(config_file, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "target_extra_count": 3,
        "difficulties": ["Easy", "Medium"],
        "run_time": "01:00"
    }

def save_config(config_data):
    with open("config.json", "w") as f:
        json.dump(config_data, f, indent=4)

def save_to_history(entry):
    history_file = "history.json"
    history = []
    if os.path.exists(history_file):
        try:
            with open(history_file, "r") as f:
                history = json.load(f)
        except Exception:
            pass
    # Insert at the beginning so the latest run is first
    history.insert(0, entry)
    with open(history_file, "w") as f:
        json.dump(history, f, indent=4)

def update_dotenv(key, value):
    lines = []
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            lines = f.readlines()
            
    key_exists = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}\n"
            key_exists = True
            break
    if not key_exists:
        lines.append(f"{key}={value}\n")
        
    with open(".env", "w") as f:
        f.writelines(lines)
    os.environ[key] = value

async def verify_leetcode_cookies():
    import httpx
    try:
        session_data = load_session()
        session_cookie = session_data.get("LEETCODE_SESSION")
        csrf_cookie = session_data.get("csrftoken")
        if not session_cookie or not csrf_cookie:
            return False, "Cookies missing"
        url = "https://leetcode.com/graphql"
        query = """
        query currentUser {
            userStatus {
                username
            }
        }
        """
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Cookie": f"LEETCODE_SESSION={session_cookie}; csrftoken={csrf_cookie}",
            "X-CSRFToken": csrf_cookie,
            "Referer": "https://leetcode.com/"
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json={"query": query}, headers=headers)
            if response.status_code == 200:
                data = response.json()
                username = data.get("data", {}).get("userStatus", {}).get("username")
                if username:
                    return True, f"Logged in as {username}"
        return False, "Invalid / Expired session"
    except Exception as e:
        return False, f"Check failed: {str(e)}"


# Setup solve and submit pipeline
async def solve_and_submit_for_app(slug):
    details = await fetch_daily_problem_details(slug)

    problem_id = details["id"]
    internal_id = details["internal_id"]
    difficulty = details["difficulty"]
    title = details["title"]
    description = details["description"]
    template = details["python_template"]

    print(f"\nProcessing problem: #{problem_id}. {title} ({difficulty})")
    
    # Check if already solved
    solved_problems = set()
    if os.path.exists("solved_problems.txt"):
        with open("solved_problems.txt", "r") as f:
            solved_problems = {line.strip() for line in f if line.strip()}
            
    if str(problem_id) in solved_problems:
        print(f"Problem #{problem_id} is already solved. Skipping.")
        return

    code = find_local_sol(problem_id, difficulty)
    source = "Local Solutions Folder"

    if not code:
        print("No local solution found. Generating via Groq Llama-3.3...")
        code = await groq_solver(description, template)
        source = "Groq Llama-3.3"
    else:
        print("Found existing local solution. Re-submitting local version...")
    
    sub_id = await submit_sol(slug, internal_id, code)
    if not sub_id:
        print("Error: Could not submit to LeetCode.")
        save_to_history({
            "timestamp": datetime.datetime.now().isoformat(),
            "problem_id": str(problem_id),
            "title": title,
            "difficulty": difficulty,
            "status": "Submission Failed",
            "runtime_percentile": "N/A",
            "memory_percentile": "N/A",
            "source": source
        })
        return
    
    print(f"Submission successful! ID: {sub_id}. Polling status...")
    result = await check_submission_status(sub_id, slug)

    if result:
        status = result.get("status_msg")
        print(f"Result: {status}")

        runtime = result.get('runtime_percentile')
        memory = result.get('memory_percentile')

        if status == "Accepted":
            print(f"Runtime beat: {runtime}% | Memory beat: {memory}%")

            padded_id = str(problem_id).zfill(4)
            directory = os.path.join("local_solutions", difficulty)
            os.makedirs(directory, exist_ok=True)
            file_path = os.path.join(directory, f"{padded_id}.py")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(code)
            print(f"Solution successfully saved to {file_path}")

            with open("solved_problems.txt", "a") as f:
                f.write(f"{problem_id}\n")
        else:
            print(f"Error status: {status}")
            if result.get('runtime_error'):
                print("\n--- RUNTIME ERROR TRACEBACK ---")
                print(result.get('runtime_error'))
            if result.get('compile_error'):
                print("\n--- COMPILE ERROR ---")
                print(result.get('compile_error'))

        save_to_history({
            "timestamp": datetime.datetime.now().isoformat(),
            "problem_id": str(problem_id),
            "title": title,
            "difficulty": difficulty,
            "status": status,
            "runtime_percentile": f"{runtime:.2f}%" if isinstance(runtime, (int, float)) else str(runtime or "N/A"),
            "memory_percentile": f"{memory:.2f}%" if isinstance(memory, (int, float)) else str(memory or "N/A"),
            "source": source
        })
    else:
        print("Polling status timed out. LeetCode may be slow or rate limiting.")
        save_to_history({
            "timestamp": datetime.datetime.now().isoformat(),
            "problem_id": str(problem_id),
            "title": title,
            "difficulty": difficulty,
            "status": "Polling Timeout",
            "runtime_percentile": "N/A",
            "memory_percentile": "N/A",
            "source": source
        })

async def run_auto_solve_pipeline():
    global is_running
    if is_running:
        print("Pipeline run requested, but it is already running. Skipping duplicate trigger.")
        return
        
    async with pipeline_lock:
        is_running = True
        print(f"\n==================================================")
        print(f"STARTING LEETCODE PIPELINE RUN ({datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        print(f"==================================================")
        try:
            # 1. Solve Daily Challenge
            print("\n>>> FETCHING DAILY CHALLENGE...")
            try:
                daily_slug = await fetch_daily_problem()
                await solve_and_submit_for_app(daily_slug)
            except Exception as e:
                print(f"Failed processing daily challenge: {e}")

            # 2. Fetch config and solve random unsolved problems
            config = load_config()
            target_extra = config.get("target_extra_count", 3)
            difficulties = config.get("difficulties", ["Easy", "Medium"])
            
            print(f"\n>>> FETCHING {target_extra} RANDOM UNSOLVED PROBLEMS ({'/'.join(difficulties)})...")
            try:
                random_slugs = await fetch_unsolved_problems(count=target_extra, difficulties=difficulties)
                print(f"Selected problems: {random_slugs}")
                
                for i, slug in enumerate(random_slugs):
                    # Mimic human delay to avoid triggers
                    sleep_time = random.randint(45, 90)
                    print(f"\nWaiting {sleep_time} seconds before starting extra problem {i+1}/{len(random_slugs)}...")
                    await asyncio.sleep(sleep_time)
                    
                    print(f"\n--- SOLVING EXTRA PROBLEM {i+1} OF {len(random_slugs)}: {slug} ---")
                    await solve_and_submit_for_app(slug)
            except Exception as e:
                print(f"Failed processing random unsolved problems: {e}")

        except Exception as e:
            print(f"Pipeline encountered critical exception: {e}")
        finally:
            is_running = False
            print(f"LEETCODE PIPELINE RUN COMPLETE")

def configure_scheduler():
    config = load_config()
    run_time = config.get("run_time", "01:00")
    try:
        hour, minute = run_time.split(":")
        hour, minute = int(hour), int(minute)
    except Exception:
        hour, minute = 1, 0
        
    for job in list(scheduler.get_jobs()):
        job.remove()
        
    scheduler.add_job(
        run_auto_solve_pipeline,
        trigger=CronTrigger(hour=hour, minute=minute),
        id="daily_solve_job",
        replace_existing=True
    )
    print(f"Daily solver scheduled to trigger at {hour:02d}:{minute:02d} local time.")

# Startup & Shutdown events
@app.on_event("startup")
async def startup_event():
    configure_scheduler()
    scheduler.start()
    print("FastAPI background scheduler started.")

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown()
    print("FastAPI background scheduler stopped.")

# Pydantic models for configuration API
class ConfigUpdate(BaseModel):
    target_extra_count: int
    difficulties: List[str]
    run_time: str
    leetcode_session: str
    leetcode_csrf: str
    groq_api_key: str

# API Router
@app.get("/api/status")
async def get_status():
    solved_count = 0
    if os.path.exists("solved_problems.txt"):
        with open("solved_problems.txt", "r") as f:
            solved_count = len([line for line in f if line.strip()])
            
    cookie_valid, cookie_msg = await verify_leetcode_cookies()
    
    next_run = None
    job = scheduler.get_job("daily_solve_job")
    if job and job.next_run_time:
        next_run = job.next_run_time.isoformat()

    return {
        "is_running": is_running,
        "next_run": next_run,
        "cookie_valid": cookie_valid,
        "cookie_status": cookie_msg,
        "solved_count": solved_count
    }

@app.get("/api/config")
async def get_config():
    config = load_config()
    
    # Load session cookies
    leetcode_session = ""
    leetcode_csrf = ""
    try:
        session = load_session()
        leetcode_session = session.get("LEETCODE_SESSION", "")
        leetcode_csrf = session.get("csrftoken", "")
    except Exception:
        pass
        
    return {
        "target_extra_count": config.get("target_extra_count", 3),
        "difficulties": config.get("difficulties", ["Easy", "Medium"]),
        "run_time": config.get("run_time", "01:00"),
        "leetcode_session": leetcode_session,
        "leetcode_csrf": leetcode_csrf,
        "groq_api_key": os.getenv("GROQ_API_KEY", "")
    }

@app.post("/api/config")
async def post_config(data: ConfigUpdate):
    # Save base configs
    config = {
        "target_extra_count": data.target_extra_count,
        "difficulties": data.difficulties,
        "run_time": data.run_time
    }
    save_config(config)
    
    # Save cookies to session.json
    session = {
        "LEETCODE_SESSION": data.leetcode_session,
        "csrftoken": data.leetcode_csrf
    }
    save_session(session)
    
    # Save Groq API Key to .env
    update_dotenv("GROQ_API_KEY", data.groq_api_key)
    
    # Reconfigure the scheduler
    configure_scheduler()
    
    return {"status": "success", "message": "Configuration updated successfully"}

@app.get("/api/history")
async def get_history():
    history_file = "history.json"
    if os.path.exists(history_file):
        try:
            with open(history_file, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []

@app.post("/api/run")
async def trigger_run(background_tasks: BackgroundTasks):
    global is_running
    if is_running:
        raise HTTPException(status_code=400, detail="Pipeline is already running.")
    background_tasks.add_task(run_auto_solve_pipeline)
    return {"status": "success", "message": "Pipeline run triggered in background"}

# WebSocket for streaming logs
@app.websocket("/ws/logs")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger = get_logger()
    queue = asyncio.Queue()
    logger.subscribers.add(queue)
    
    # Send historical logs first so they see recent output
    try:
        for history_msg in logger.log_history:
            await websocket.send_text(history_msg)
            
        while True:
            log_msg = await queue.get()
            await websocket.send_text(log_msg)
    except WebSocketDisconnect:
        pass
    finally:
        logger.subscribers.remove(queue)

# Serve Frontend static files
# Make sure the directory exists or FastAPI startup won't crash
os.makedirs("public", exist_ok=True)

@app.get("/")
async def get_index():
    return FileResponse("public/index.html")

app.mount("/", StaticFiles(directory="public"), name="public")
