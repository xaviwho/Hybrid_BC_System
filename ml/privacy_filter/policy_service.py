"""HTTP front end for the deterministic privacy policy.

`orchestrator.ingest_data` calls a privacy filter over HTTP
(`PRIVACY_FILTER_URL`, default `/filter_data`). Privacy routing itself is no
longer an ML classifier — it is the deterministic rule engine in
`policy_engine.py`, whose `filter_for_publication()` is documented as
"backward-compatible with the previous service contract (consumed by
orchestrator.ingest_data)". That function was never given an HTTP wrapper, so
this module supplies one and nothing else.

It deliberately does NOT use `predict.py`: that module imports
`_quarantine/sensitivity_classifier.py` and, when the model file is absent,
trains a RandomForest on `np.random.rand` dummy data. Putting that in the ingest
path would make exp1/exp5 measure noise.

No policy logic lives here. Every decision comes from policy_engine.

    PORT=5011 PYTHONPATH=<repo>/ml python privacy_filter/policy_service.py
"""

import os
import logging

from flask import Flask, request, jsonify
from flask_cors import CORS

from privacy_filter.policy_engine import (
    POLICY_VERSION,
    filter_for_publication,
    filter_by_access,
)

app = Flask(__name__)
CORS(app)
logger = logging.getLogger("policy_service")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "deterministic-privacy-policy",
        "policy_version": POLICY_VERSION,
        "engine": "policy_engine",
    }), 200


@app.route("/filter_data", methods=["POST"])
def filter_data():
    """Public-ledger gate. Mirrors the contract orchestrator.ingest_data expects:
    the decision is returned under `result`."""
    payload = request.get_json(silent=True) or {}
    record = payload.get("iot_data")
    if record is None:
        return jsonify({"error": "missing required field: iot_data"}), 400

    try:
        decision = filter_for_publication(record)
    except Exception:
        # Fail closed: never let a policy error publish unfiltered data.
        logger.exception("policy evaluation failed")
        return jsonify({"error": "policy evaluation failed"}), 500

    return jsonify({"result": decision}), 200


@app.route("/filter_by_access", methods=["POST"])
def by_access():
    """Query-time sharing. Reversible, unlike the public-ledger gate."""
    payload = request.get_json(silent=True) or {}
    record = payload.get("iot_data")
    if record is None:
        return jsonify({"error": "missing required field: iot_data"}), 400
    access = payload.get("requester_access_level", "user")
    try:
        return jsonify({"result": filter_by_access(record, access)}), 200
    except Exception:
        logger.exception("access evaluation failed")
        return jsonify({"error": "access evaluation failed"}), 500


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    port = int(os.getenv("PORT", "5011"))
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
