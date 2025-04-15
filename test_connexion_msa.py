# app.py (dans le container)
import psycopg
import os

#print(os.getenv("POSTGRES_PASSWORD"))   
print(os.getenv("SUPABASE_HOST"))

def main():
    conn = psycopg.connect(
        host='aws-0-eu-west-3.pooler.supabase.com',
        port=5432,# 5432 , 6543 
        dbname="postgres",
        user="postgres.zpjemgpnfaeayofvnkzo",
        password=os.getenv("POSTGRES_PASSWORD"),
        sslmode="require"
    )
    
    with conn.cursor() as cur:
        cur.execute("SELECT version()")
        print(cur.fetchone())
    
    conn.close()

if __name__ == "__main__":
    main()