import os, psycopg
os.environ['DATABASE_URL_INGEST'] = 'postgresql://postgres.uggmvjzoknjbhmjcjmgn:l4lJCfKK3W1xOPSk@aws-0-eu-west-1.pooler.supabase.com:5432/postgres?sslmode=require'
conn = psycopg.connect(os.environ['DATABASE_URL_INGEST'], prepare_threshold=None, sslmode='require')

with conn.cursor() as cur:
    cur.execute('SELECT country, chamber, count(*) FROM political_tracker.members WHERE is_current GROUP BY country, chamber')
    print('Members:', cur.fetchall())
    cur.execute('SELECT country, chamber, count(*) FROM political_tracker.votes GROUP BY country, chamber')
    print('Votes:', cur.fetchall())
    cur.execute('SELECT v.country, count(*) FROM political_tracker.member_votes mv JOIN political_tracker.votes v ON v.id=mv.vote_id GROUP BY v.country')
    print('Member votes:', cur.fetchall())

conn.close()