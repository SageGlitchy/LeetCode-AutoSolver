import json
import os
import httpx
import asyncio
from fetch_problem import fetch_daily_problem, fetch_daily_problem_details
from solver import find_local_sol, groq_solver 

def load_session():
    with open("session.json", "r") as f:
        return json.load(f)
    
def save_session(session_data):
    with open("session.json", "w") as f:
        json.dump(session_data, f , indent=4)
    print("Cookies refreshed and saved to session.json")


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

async def check_submission_status(submission_id, slug):
    session_data= load_session()
    session_cookie= session_data["LEETCODE_SESSION"]
    csrf_cookie= session_data["csrftoken"]

    url= f"https://leetcode.com/submissions/detail/{submission_id}/check/"

    header= {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Cookie": f"LEETCODE_SESSION={session_cookie}; csrftoken={csrf_cookie};",
        "X-CSRFToken": csrf_cookie,
        "Referer": f"https://leetcode.com/problems/{slug}/"
    }

    async with httpx.AsyncClient(timeout=20.0) as client:

        for attempt in range(5):
            await asyncio.sleep(2)
            response= await client.get(url, headers= header)

            if response.status_code==200:
                result= response.json()
                state= result.get("state")

                if state=="SUCCESS":
                    return result
            else:
                print(f"Error: {response.status_code}")
    return None

async def main():
    slug= await fetch_daily_problem()
    details= await fetch_daily_problem_details(slug)

    problem_id= details["id"]
    internal_id= details["internal_id"]
    difficulty=details["difficulty"]
    title=details["title"]
    description=details["description"]
    template= details["python_template"]

    print(f"Daily problem: #{problem_id}. {title} ({difficulty})")
    code= find_local_sol(problem_id, difficulty)

    if not code:
        code= await groq_solver(description, template)
    
    print(code)

    sub_id= await submit_sol(slug, internal_id, code)

    if not sub_id:
        print("Error: Could not submit")
        return
    
    print(f"Submission ID: {sub_id}")

    result= await check_submission_status(sub_id, slug)

    if result:
        status= result.get("status_msg")
        print(f"Result: {status}")


        if status=="Accepted":
            print(f"Runtime beat: {result.get('runtime_percentile')}")
            print(f"Memory beat: {result.get('memory_percentile')}")

            padded_id = str(problem_id).zfill(4)
            directory = os.path.join("local_solutions", difficulty)
            os.makedirs(directory, exist_ok=True)
            file_path = os.path.join(directory, f"{padded_id}.py")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(code)
            print(f"Solution successfully saved to {file_path}")

            # Append the ID to solved_problems.txt
            with open("solved_problems.txt", "a") as f:
                f.write(f"{problem_id}\n")

        else:
            print(f"Error: {status}")

            if result.get('runtime_error'):
                    print("\n--- RUNTIME ERROR TRACEBACK ---")
                    print(result.get('runtime_error'))
            if result.get('compile_error'):
                    print("\n--- COMPILE ERROR ---")
                    print(result.get('compile_error'))
    else:
        print("Polling timed out. Could not verify results")

if __name__=="__main__":
    asyncio.run(main())

            












