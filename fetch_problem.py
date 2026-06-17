import httpx
import asyncio
import re


def clean_html(html_str):
    if not html_str:
        return ""

    text= re.sub(r'<code>(.*?)</code>', r'`\1`', html_str)

    text= re.sub(r'<[^>]+>', '', text)

    text= text.replace("&nbsp;", ' ').replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'").replace("`", "").replace("&quot;", '"')
    
    return text.strip()


async def fetch_daily_problem():
    url= "https://leetcode.com/graphql"

    query= """
    query questionOfToday{
        activeDailyCodingChallengeQuestion{
            date
            question{
                title
                titleSlug
            }
        }
    }
    """

    payload= {
        "query": query
    }

    headers= {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    async with httpx.AsyncClient() as client:

        response= await client.post(url, json=payload, headers=headers)

        data= response.json()

        slug= data["data"]["activeDailyCodingChallengeQuestion"]["question"]["titleSlug"]
        return slug

async def fetch_daily_problem_details(title_slug):
    url="https://leetcode.com/graphql"

    query="""
    query questionData($titleSlug: String!){
        question(titleSlug: $titleSlug){
            questionId
            questionFrontendId
            title
            titleSlug
            content
            difficulty
            codeSnippets{
                lang
                langSlug
                code
            }
        }
    }
    """

    payload= {
        "query":query,
        "variables":{
            "titleSlug":title_slug
        }
    }

    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    async with httpx.AsyncClient() as client:
        response= await client.post(url, json=payload, headers= headers)
        data = response.json()

        question_data=data["data"]["question"]
        python_template=""

        for snippet in question_data["codeSnippets"]:
            if snippet['langSlug']=='python3':
                python_template= snippet["code"]
                break

        clean_desc= clean_html(question_data['content'])


        return {
            "id": question_data['questionFrontendId'],
            "internal_id": question_data['questionId'],
            "title": question_data['title'],
            "difficulty": question_data['difficulty'],
            "description": clean_desc,
            "python_template": python_template
        }

def load_solved_problems():
    import os
    if not os.path.exists("solved_problems.txt"):
        # Auto-initialize by scanning local_solutions folder once
        solved = set()
        if os.path.exists("local_solutions"):
            for root, dirs, files in os.walk("local_solutions"):
                for file in files:
                    if file.endswith(".py"):
                        prob_id = file[:-3].lstrip("0")
                        if not prob_id:
                            prob_id = "0"
                        solved.add(prob_id)
        with open("solved_problems.txt", "w") as f:
            for prob_id in sorted(list(solved), key=int):
                f.write(f"{prob_id}\n")
        return solved
        
    try:
        with open("solved_problems.txt", "r") as f:
            return {line.strip() for line in f if line.strip()}
    except Exception:
        return set()

def load_session_for_fetch():
    import json
    try:
        with open("session.json", "r") as f:
            return json.load(f)
    except Exception:
        return {}

async def fetch_unsolved_problems(count=3, difficulties=None):
    url = "https://leetcode.com/graphql"
    session_data = load_session_for_fetch()
    session_cookie = session_data.get("LEETCODE_SESSION", "")
    csrf_cookie = session_data.get("csrftoken", "")

    query = """
    query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
        problemsetQuestionList: questionList(
            categorySlug: $categorySlug
            limit: $limit
            skip: $skip
            filters: $filters
        ) {
            total: totalNum
            questions: data {
                questionFrontendId
                questionId
                title
                titleSlug
                difficulty
                status
            }
        }
    }
    """
    
    payload = {
        "query": query,
        "variables": {
            "categorySlug": "",
            "limit": 100,
            "skip": 0,
            "filters": {}
        }
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    }
    if session_cookie and csrf_cookie:
        headers["Cookie"] = f"LEETCODE_SESSION={session_cookie}; csrftoken={csrf_cookie}"
        headers["X-CSRFToken"] = csrf_cookie
        
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            print(f"[Error] Failed to fetch unsolved problems: {response.status_code} - {response.text}")
            return []
            
        data = response.json()
        questions = data.get("data", {}).get("problemsetQuestionList", {}).get("questions", [])
        
        # Load solved problems and filter them out
        solved_set = load_solved_problems()
        questions = [q for q in questions if str(q.get("questionFrontendId")) not in solved_set]
        
        if difficulties:
            target_diffs = [d.upper() for d in difficulties]
            questions = [q for q in questions if q.get("difficulty", "").upper() in target_diffs]
            
        if not questions:
            print("[Fetcher] No questions match the filter criteria.")
            return []
            
        import random
        selected = random.sample(questions, min(count, len(questions)))
        return [q["titleSlug"] for q in selected]


async def main():
    title_slug= await fetch_daily_problem()
    print(f'Daily Challenge Slug: {title_slug}')

    details= await fetch_daily_problem_details(title_slug)

    print("_"*50)
    print(f'PROBLEM #{details["id"]}: {details["title"]} ({details["difficulty"]})')
    print("_"*50)
    print(f'Description: {details["description"][:150]}...')
    print("_"*50)
    
    print("\nFetching 3 random unsolved Medium or Easy problems...")
    random_slugs = await fetch_unsolved_problems(count=3, difficulties=["EASY", "MEDIUM"])
    print(f"Selected random slugs: {random_slugs}")

if __name__ == "__main__":
    asyncio.run(main())