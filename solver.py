import os
import re
import asyncio
from google import genai
from dotenv import load_dotenv
from fetch_problem import fetch_daily_problem, fetch_daily_problem_details

load_dotenv()

def extract_code(text):
    match= re.search(r"```(?:python)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()

async def gemini_solver(description, template):
    client= genai.Client()

    prompt = f"""
    You are an expert software engineer solving LeetCode problems in Python.
    
    Problem Description:
    {description}
    
    Python Code Template:
    {template}
    
    Write the complete Python solution matching the class and method structure of the template.
    Your code must be clean, syntactically correct, and optimized for performance.
    Return ONLY the executable Python code. Do not write explanation text. 
    You may wrap your code in ```python ... ``` block. Also don't write any comment in the Code.
    """

    print("[Gemini] Requesting solution from gemini-2.5-flash...")
    response= await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    return extract_code(response.text)


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
        print("Calling Fallback to Gemini...")

        code= await gemini_solver(details['description'], details['python_template'])
        print('GEMINI SOLUTION: \n')
        print(code)

if __name__=="__main__":
    asyncio.run(main())
