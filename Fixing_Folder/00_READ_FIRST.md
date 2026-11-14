# Read first: how to use this folder

This folder collects known problems and proposed fixes, to be applied once the frontend exists:
- `errors.md`: DTO bundle vs. data, schema v2 review, decisions (oldest)
- `backend_review_2026-11-14.md`: backend review, open issues and proposals
- `project_validation_2026-11-14.md`: whole project (harmonisation + backend + frontend), technical and contextual errors (newest)

## Instruction for the AI that picks this up

Validate all files in `Fixing_Folder`. Do not take them as ground truth or as given. Evaluate everything anew
with all the information you have now: the frontend (the ultimate goal), the backend and the data harmonisation.

Address all issues, not only on a technical level but, more importantly, on a contextual level. Evaluate whether
some things do not make sense.

Questions to ask for every item:
- Is it still true? Check it against the current code and data instead of the text here (numbers, line references and
  file paths may be outdated).
- Does the frontend actually need it? An issue about an output the frontend never shows may be dropped together with
  that output.
- Does the proposed fix serve the goal (an honest, harmonised MODIS + VIIRS fire record for Spain and Portugal), or
  only make the code tidier?
- Would a user read the result correctly? (Example: a metric called `fires` that is really VIIRS-scale detections.)
- Are two items in conflict, or is one decision missing that several items depend on?

Report back first (what is still valid, what is outdated, what makes no sense, what is new) and agree on the decisions
with the user before changing code.

## Ground rules

- Never commit or push. The user commits.
- Do not modify `harmonisation/CONTEXT.md`. Never commit `.env`, data files or keys.
- Verify with real data: load the harmonised Parquet into a scratch database (`pipeline/load_to_db.py --database-url ...`)
  and run `backend/tests` and `pipeline/tests`. Do not overwrite the user's database.
