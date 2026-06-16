import os
import re
import asyncio
from groq import AsyncGroq
from dotenv import load_dotenv
from fetch_problem import fetch_daily_problem, fetch_daily_problem_details

load_dotenv()

def extract_code(text):
    match= re.search(r"```(?:python)?\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()

async def groq_solver(description, template):
    client= AsyncGroq()

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

    print("[Groq] Requesting solution from gemini-2.5-flash...")

    max_retries= 5
    for attempt in range(max_retries):
        try:
            response= await client.chat.completions.create(
                messages=[
                    {
                        "role":"user",
                        "content":prompt,
                    }
                ],
                model= "llama-3.3-70b-versatile"
            )

            code= response.choices[0].message.content
            return extract_code(code)

        except Exception as e:
            if attempt<max_retries-1:
                print(f"Attempt {attempt} failed.")
                await asyncio.sleep(20)
            else:
                print("All attempts failed.")
                raise e



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
