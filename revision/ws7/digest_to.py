"""Write the run digest (experiments/run_digest.py) to a file: digest_to.py OUT_JSON."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                                "experiments"))
import run_digest  # noqa: E402

with open(sys.argv[1], "w") as f:
    json.dump(run_digest.collect(), f, indent=1, default=list)
