import os
from dotenv import load_dotenv
load_dotenv()
url = os.getenv('DATABASE_URL', 'NOT FOUND')
print(f'URL: {url[:60]}')
print(f'Has asyncpg: {"asyncpg" in url}')

print('VIDEO_ENV:', os.getenv('VIDEO_ENV', 'not set'))
print('DID_API_KEY set:', bool(os.getenv('DID_API_KEY', '')))
print('ELEVENLABS_API_KEY set:', bool(os.getenv('ELEVENLABS_API_KEY', '')))
print(f'DID_API_KEY: {os.getenv("DID_API_KEY", "NOT FOUND")}')
