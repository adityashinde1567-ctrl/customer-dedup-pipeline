# Design and Trade-off Note

1. **Exact matching:** normalized email OR phone provides a transparent starting point. Union-find handles transitive relationships (A shares email with B, B shares phone with C).
2. **Fuzzy matching:** candidate blocking by postal code / phone suffix avoids naive all-pairs matching. `difflib.SequenceMatcher` is dependency-free and understandable, but less sophisticated than production entity-resolution libraries.
3. **Survivorship:** completeness, recency, source trust, and stable ID tie-breaker make the result deterministic. Missing fields can be filled from lower-ranked records.
4. **Lineage:** every valid source row is linked to a master; rejects retain raw row JSON and source location.
5. **Idempotency:** master IDs derive from sorted source IDs; snapshot output tables are replaced transactionally on rerun. Run history remains.
6. **Limitations:** shared email/phone may over-merge; fuzzy candidates can miss pairs outside blocking keys; this is a batch snapshot, not CDC; review decisions are not yet persisted as an approval workflow.
