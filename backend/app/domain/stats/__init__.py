"""Statistics of module I (docs/SPEC.md section 4). Pure Python.

Every function takes small dataclasses read from the logs and a `DayOf` function that maps an
instant to its study day (D-014). Nothing here opens a session, reads the clock or imports `fsrs`.
Each value comes with its count, and a rate whose count is under its threshold is `None` with
`insufficient = True` (no misleading figure).
"""
