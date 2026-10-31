"""Train a leakage-aware ML candidate; never overwrite production artifacts."""
from pathlib import Path
import logging

from ml.temporal_validation import train_candidate

ROOT = Path(__file__).resolve().parents[1]
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

if __name__ == "__main__":
    result = train_candidate(
        dataset_path=ROOT / "ml" / "historical_data.csv",
        output_root=ROOT / "models",
        lookahead=12,
    )
    print("\nCandidate training complete")
    print(f"Candidate directory: {result['candidate_dir']}")
    print(f"Validation balanced accuracy: {result['metadata']['validation']['balanced_accuracy']:.4f}")
    print(f"Out-of-sample balanced accuracy: {result['metadata']['out_of_sample_test']['balanced_accuracy']:.4f}")
    print("Deployment approved: NO")
