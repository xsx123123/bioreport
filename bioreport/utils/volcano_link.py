"""Stable gene identity shared by the interactive DEG table and volcano plot."""
import hashlib
import json


def gene_id_column(frame):
    names = {str(column).casefold(): column for column in frame.columns}
    for name in ('ensembl', 'geneid', 'gene_id', 'symbol', 'gene_name', 'gene'):
        if name in names:
            return names[name]
    return None


def source_digest(frame):
    """Exact source rows/columns, independent of the DataFrame's index labels."""
    import pandas as pd
    try:
        values = pd.util.hash_pandas_object(frame, index=False).values.tobytes()
    except TypeError:
        return None
    return hashlib.sha256(json.dumps(list(map(str, frame.columns))).encode() + values).hexdigest()
