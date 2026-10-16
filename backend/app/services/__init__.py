"""Operations that read and write the database. Each one works in the caller's transaction and
never commits: the entry point (CLI, later the API) commits or rolls back (D-017, D-023)."""
