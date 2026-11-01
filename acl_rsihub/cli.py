"""Source check only. There is no live/run command yet."""
import argparse
import json

from .native import LOCK, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check"])
    args = parser.parse_args()
    root = verify()
    cfg = json.loads(LOCK.read_text())
    print(
        json.dumps(
            {
                "status": "rsihub_source_verified",
                "revision": cfg["revision"],
                "source": str(root),
                "paid_runs_started": cfg["protocol"]["paid_runs_started"],
                "model_calls": 0,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
