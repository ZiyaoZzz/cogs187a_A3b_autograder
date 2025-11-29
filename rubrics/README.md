# Rubrics

Central home for rubric definitions consumed by the autograder pipeline (and future LLM evaluators).

- `a3_rubric.json` – canonical structure for COGS 187A Assignment 3.
  - `criteria`: core required scoring dimensions (total 95 pts)
  - `bonusCriteria`: optional extra credit dimensions (5 pts)

## Using the rubric

```text
rubrics/
  └── a3_rubric.json
```

When the LLM evaluation step is implemented, load this JSON and map each criterion to the analysis output. Having the rubric in machine‑readable form lets us:

1. Keep the course rubric under version control.
2. Share identical scoring logic between human graders and the automated pipeline.
3. Extend easily if future assignments need different weighting (add another JSON file).

Feel free to add new files here for other assignments (e.g., `a4_rubric.json`). Each rubric file should follow the same structure so downstream tooling can load them generically.

