1. Why can't you just edit the database schema by hand with psql instead of using Alembic?
    - a hand edit with psql is invisible to everyone else. migrations are team coodination, not just data safety

2. If a teammate adds a migration on a separate branch, and your branch also adds one, what does Alembic do at upgrade head?
    - it applies both, in order by revision ID

3. What is the "head" in alembic upgrade head? (Two sentences max.)
    - head is the most recent revision in the chain

----------------------------------------------

1. Looking at the #03 checklist, the list says "B-tree composto (gestor_id, empresa_id, data)". That's the read pattern the index serves. State in your own words what query this index is supposed to make fast, and why all three columns go together (not just one).
    - compound index. 

2. The same checklist says "Partial Index: (data) WHERE status = 'completed'". What's a partial index, and why would we only index rows that are completed instead of all of them? Tie it to the read-write trade-off from above.
