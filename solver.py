import os
import asyncio
from fetch_problem import fetch_daily_problem, fetch_daily_problem_details

def find_local_sol(prob_id, difficulty):
    initial_id= str(prob_id).zfill(4)

    file_path= os.path.join("local_solutions", difficulty, f"{initial_id}.py")

    if os.path.exists(file_path):
        print(f"[Local Repo] Solution found for Problem #{prob_id} at {file_path}")
        
        with open(file_path, "r", encoding= "utf-8") as f:
            return f.read()
        
    print(f"[Local Repo] No solution found at {file_path}")
    return None

async def main():
    slug= await fetch_daily_problem()

    details= await fetch_daily_problem_details(slug)
    print(f"Checking local solution for Problem #{details['id']} ({details['title']})...")

    local_code= find_local_sol(details['id'], details['difficulty'])

    if local_code:
        print("LOCAL SOLUTION: \n")
        print(local_code)
    else:
        print("Calling Fallback to Gemini")

if __name__=="__main__":
    asyncio.run(main())
