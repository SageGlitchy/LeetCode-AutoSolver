import re
import asyncio
import os
from groq import AsyncGroq
from dotenv import load_dotenv

load_dotenv()

def find_local_sol(problem_id, difficulty):
    padded_id = str(problem_id).zfill(4)
    file_path = os.path.join("local_solutions", difficulty, f"{padded_id}.py")
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception:
            return None
    return None

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
    Your code must be clean, syntactically correct, and optimized for performance according to the constraints.
    Return ONLY the executable Python code. Do not write explanation text. 
    You may wrap your code in ```python ... ``` block. Also don't write any comment in the Code.
    """

    print("[Groq] Requesting solution from llama-3.3-70b-versatile...")

    max_retries= 5
    for attempt in range(max_retries):
        try:
            response= await client.chat.completions.create(
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                model= "llama-3.3-70b-versatile"
            )

            code= response.choices[0].message.content
            return extract_code(code)

        except Exception as e:
            if attempt < max_retries - 1:
                print(f"Attempt {attempt + 1} failed. Retrying in 20 seconds...")
                await asyncio.sleep(20)
            else:
                print("All attempts failed.")
                raise e

async def main():
    from fetch_problem import fetch_daily_problem, fetch_daily_problem_details
    
    daily_slug = await fetch_daily_problem()
    details = await fetch_daily_problem_details(daily_slug)
    
    print(f"Testing Groq Solver on Problem #{details['id']}: {details['title']}...")
    code = await groq_solver(details['description'], details['python_template'])
    
    print("\n--- GENERATED CODE ---")
    print(code)
    print("----------------------\n")

if __name__ == "__main__":
    asyncio.run(main())
