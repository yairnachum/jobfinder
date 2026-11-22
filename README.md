Automated state branch for jobfinder. Do not edit by hand.

Holds `state/seen.jsonl`, the record of which postings have already been
notified. Kept off `main` so the watch workflow does not add ~96 commits
per day to the main history.
