import httpx
import asyncio
import re


def clean_html(html_str):
    if not html_str:
        return ""

    text= re.sub(r'<code>(.*?)</code>', r'`\1`', html_str)

    text= re.sub(r'<[^>]+>', '', text)

    text= text.replace("&nbsp;", ' ').replace("&lt;", "<").replace("&gt;", ">")
    
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
            "title": question_data['title'],
            "difficulty": question_data['difficulty'],
            "description": clean_desc,
            "python_template": python_template
        }


async def main():
    title_slug= await fetch_daily_problem()
    print(f'Daily Challenge Slug: {title_slug}')

    details= await fetch_daily_problem_details(title_slug)

    print("_"*50)
    print(f'PROBLEM #{details["id"]}: {details["title"]} ({details["difficulty"]})')
    print("_"*50)
    print(f'Description: {details["description"]}')
    print("_"*50)
    print(f'Py template: {details["python_template"]}')

if __name__=="__main__":
    asyncio.run(main())