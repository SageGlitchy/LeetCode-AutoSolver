import json
import os
import httpx
import asyncio
from fetch_problem import fetch_daily_problem, fetch_daily_problem_details, fetch_unsolved_problems
from solver import groq_solver 

def load_session():
    with open("session.json", "r") as f:
        return json.load(f)
    
def save_session(session_data):
    with open("session.json", "w") as f:
        json.dump(session_data, f , indent=4)
    print("Cookies refreshed and saved to session.json")

def load_solved_problems():
    try:
        with open("solved_problems.txt", "r") as f:
            return {line.strip() for line in f if line.strip()}
    except FileNotFoundError:
        return set()

async def submit_sol(slug, prob_id, code):
    session_data= load_session()
    session_cookie= session_data["LEETCODE_SESSION"]
    csrf_cookie= session_data["csrftoken"]


    url= f"https://leetcode.com/problems/{slug}/submit/"

    payload={
        "lang":"python3",
        "question_id":str(prob_id),
        "typed_code":code
    }

    headers= {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Cookie": f"LEETCODE_SESSION={session_cookie}; csrftoken={csrf_cookie}",
        "X-CSRFToken":csrf_cookie,
        "Referer": f"https://leetcode.com/problems/{slug}/",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        response= await client.post(url, json=payload, headers=headers)

        new_session= response.cookies.get("LEETCODE_SESSION")
        if new_session:
            session_data["LEETCODE_SESSION"]=new_session
            save_session(session_data)
        
        if response.status_code != 200:
            print(f"Error Code {response.status_code}: ",response.text)
            return None

        data= response.json()
        submission_id= data.get("submission_id")
        return submission_id


async def check_submission_status(submission_id, slug, max_attempts=10):
    session_data= load_session()
    session_cookie= session_data["LEETCODE_SESSION"]
    csrf_cookie= session_data["csrftoken"]

    url= f"https://leetcode.com/submissions/detail/{submission_id}/check/"
    headers= {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Cookie": f"LEETCODE_SESSION={session_cookie}; csrftoken={csrf_cookie}",
        "X-CSRFToken": csrf_cookie,
        "Referer": f"https://leetcode.com/problems/{slug}/",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        for attempt in range(max_attempts):
            response= await client.get(url, headers=headers)
            if response.status_code == 200:
                data= response.json()
                if data.get("state") == "SUCCESS":
                    return data
            print(f"  Polling... ({attempt + 1}/{max_attempts})")
            await asyncio.sleep(2)
    return None


async def solve_and_submit_problem(slug):
    details= await fetch_daily_problem_details(slug)

    problem_id= details["id"]
    internal_id= details["internal_id"]
    difficulty= details["difficulty"]
    title= details["title"]
    description= details["description"]
    template= details["python_template"]

    print(f"\n{'='*50}")
    print(f"Problem: #{problem_id}. {title} ({difficulty})")
    print(f"{'='*50}")

    solved= load_solved_problems()
    if str(problem_id) in solved:
        answer= input(f"Problem #{problem_id} is already solved. Submit again? (y/N): ").strip().lower()
        if answer != 'y':
            print("Skipping.")
            return

    code= await groq_solver(description, template)
    print("\n[Generated Code]")
    print(code)

    sub_id= await submit_sol(slug, internal_id, code)
    if not sub_id:
        print("Error: Could not submit.")
        return

    print(f"Submission ID: {sub_id}")
    result= await check_submission_status(sub_id, slug)

    if result:
        status= result.get("status_msg")
        print(f"Result: {status}")

        if status == "Accepted":
            print(f"Runtime: {result.get('runtime_percentile')}% | Memory: {result.get('memory_percentile')}%")

            padded_id= str(problem_id).zfill(4)
            directory= os.path.join("local_solutions", difficulty)
            os.makedirs(directory, exist_ok=True)
            file_path= os.path.join(directory, f"{padded_id}.py")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(code)
            print(f"Saved to {file_path}")

            with open("solved_problems.txt", "a") as f:
                f.write(f"{problem_id}\n")
        else:
            print(f"Status: {status}")
            if result.get('runtime_error'):
                print("\n--- RUNTIME ERROR ---")
                print(result.get('runtime_error'))
            if result.get('compile_error'):
                print("\n--- COMPILE ERROR ---")
                print(result.get('compile_error'))
    else:
        print("Polling timed out.")


async def main():
    RANDOM_PROBLEMS = 3  # Adjust between 2-5

    print("--- [STEP 1] Daily Challenge ---")
    daily_slug= await fetch_daily_problem()
    await solve_and_submit_problem(daily_slug)

    print(f"\n--- [STEP 2] Fetching {RANDOM_PROBLEMS} Random Unsolved Problems ---")
    random_slugs= await fetch_unsolved_problems(count=RANDOM_PROBLEMS)

    for i, slug in enumerate(random_slugs, start=1):
        print(f"\nWaiting 30 seconds before next problem...")
        await asyncio.sleep(30)
        print(f"--- Random Problem {i}/{len(random_slugs)} ---")
        await solve_and_submit_problem(slug)


if __name__=="__main__":
    asyncio.run(main())


            












