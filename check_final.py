import os, psycopg
os.environ['DATABASE_URL_INGEST'] = 'postgresql://postgres.uggmvjzoknjbhmjcjmgn:l4lJCfKK3W1xOPSk@aws-0-eu-west-1.pooler.supabase.com:5432/postgres?sslmode=require'
conn = psycopg.connect(os.environ['DATABASE_URL_INGEST'], connect_timeout=10)
with conn.cursor() as cur:
    cur.execute('SELECT count(*) FROM political_tracker.member_votes')
    print('member_votes count:', cur.fetchone()[0])
    cur.execute('SELECT count(*) FROM political_tracker.members WHERE country=\'US\' AND is_current')
    print('US members:', cur.fetchone()[0])
    cur.execute('SELECT count(*) FROM political_tracker.votes WHERE country=\'US\'')
    print('US votes:', cur.fetchone()[0])
conn.close()