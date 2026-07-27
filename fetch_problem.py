import httpx
import asyncio
import re
import os
import random
import json


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

    async with httpx.AsyncClient(timeout=20.0) as client:

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

    async with httpx.AsyncClient(timeout=20.0) as client:
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


async def fetch_unsolved_problems(count=random.randint(2,5), difficulties=["Easy", "Medium"]):
    solved_set = set()
    if os.path.exists("solved_problems.txt"):
        with open("solved_problems.txt", "r") as f:
            solved_set = {line.strip() for line in f if line.strip()}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Content-Type": "application/json"
    }
    
    filters = {}
    if os.path.exists("session.json"):
        try:
            with open("session.json", "r") as f:
                session_data = json.load(f)
            session_cookie = session_data.get("LEETCODE_SESSION")
            csrf_cookie = session_data.get("csrftoken")
            if session_cookie and csrf_cookie:
                headers["Cookie"] = f"LEETCODE_SESSION={session_cookie}; csrftoken={csrf_cookie}"
                headers["X-CSRFToken"] = csrf_cookie
                headers["Referer"] = "https://leetcode.com/problemset/all/"
                filters["status"] = "NOT_STARTED"
        except Exception as e:
            print(f"Warning loading session: {e}")

    url = "https://leetcode.com/graphql"
    query = """
    query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, $filters: QuestionListFilterInput) {
        problemsetQuestionList: questionList(
            categorySlug: $categorySlug
            limit: $limit
            skip: $skip
            filters: $filters
        ) {
            totalNum
            questions: data {
                frontendQuestionId: questionFrontendId
                titleSlug
                difficulty
                isPaidOnly
            }
        }
    }
    """

    async with httpx.AsyncClient(timeout=20.0) as client:
        # Step 1: Get total matching questions to properly pick a random skip offset
        payload1 = {
            "query": query,
            "variables": {
                "categorySlug": "",
                "skip": 0,
                "limit": 1,
                "filters": filters
            }
        }
        
        response1 = await client.post(url, json=payload1, headers=headers)
        if response1.status_code != 200:
            print(f"Error fetching question total: {response1.status_code}")
            return []

        data1 = response1.json()
        total_num = data1["data"]["problemsetQuestionList"]["totalNum"]

        # Step 2: Fetch a random slice of questions using the random skip
        limit_val = 100
        max_skip = max(0, total_num - limit_val)
        random_skip = random.randint(0, max_skip)

        payload2 = {
            "query": query,
            "variables": {
                "categorySlug": "",
                "skip": random_skip,
                "limit": limit_val,
                "filters": filters
            }
        }

        response2 = await client.post(url, json=payload2, headers=headers)
        if response2.status_code != 200:
            print(f"Error fetching question list: {response2.status_code}")
            return []

        data2 = response2.json()
        questions = data2["data"]["problemsetQuestionList"]["questions"]

        candidates = []
        for q in questions:
            q_id = str(q["frontendQuestionId"])
            q_slug = q["titleSlug"]
            q_diff = q["difficulty"]
            is_paid = q["isPaidOnly"]

            if q_diff in difficulties and not is_paid and q_id not in solved_set:
                candidates.append(q_slug)

        return random.sample(candidates, min(count, len(candidates)))


async def main():
    title_slug= await fetch_daily_problem()
    print(f'Daily Challenge Slug: {title_slug}')

    details= await fetch_daily_problem_details(title_slug)

    print("_"*50)
    print(f'PROBLEM #{details["id"]}: {details["title"]} ({details["difficulty"]})')
    print("_"*50)
    print(f'Description: {details["description"][:150]}...')
    print("_"*50)
    

if __name__ == "__main__":
    asyncio.run(main())