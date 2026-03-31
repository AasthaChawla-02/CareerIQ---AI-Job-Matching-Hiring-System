from sqlalchemy import create_engine, text
engine = create_engine('postgresql+psycopg://postgres:postgres@localhost:5432/job_assistant')
with engine.connect() as conn:
    result = conn.execute(text("SELECT source, COUNT(*) FROM jobs GROUP BY source"))
    print("Jobs by source:")
    for row in result:
        print(row)
    print("\nSample matches:")
    result = conn.execute(text("""
        SELECT m.match_score, j.title, j.company_name, j.source, u.email as candidate
        FROM matches m 
        JOIN jobs j ON m.job_id = j.id 
        JOIN users u ON m.candidate_id = u.id 
        ORDER BY m.match_score DESC LIMIT 10
    """))
    for row in result:
        print(row)

