import os
from dotenv import load_dotenv
load_dotenv()
url = os.getenv('DATABASE_URL', 'NOT FOUND')
print(f'URL: {url[:60]}')
print(f'Has asyncpg: {"asyncpg" in url}')