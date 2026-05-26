import duckdb
import os

def get_db(): return duckdb.connect(":memory:")
