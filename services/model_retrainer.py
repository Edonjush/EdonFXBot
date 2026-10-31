"""Safe retraining facade: produces isolated candidates, never deploys them."""
import logging
from pathlib import Path

from ml.temporal_validation import train_candidate
from config.settings import HISTORICAL_DATA_PATH, MODELS_DIR

logger = logging.getLogger(__name__)


class ModelRetrainer:
    def __init__(self, dataset_path=None, output_root=None, **_ignored_legacy_paths):
        self.dataset_path = Path(dataset_path) if dataset_path else Path(HISTORICAL_DATA_PATH)
        self.output_root = Path(output_root) if output_root else Path(MODELS_DIR)

    def retrain(self):
        """Backward-compatible entry point; candidate-only by design."""
        try:
            result = train_candidate(
                dataset_path=self.dataset_path,
                output_root=self.output_root,
                lookahead=12,
            )
            logger.info("Candidate saved at %s; production artifacts unchanged", result["candidate_dir"])
            return {
                "success": True,
                "candidate_dir": result["candidate_dir"],
                "validation_balanced_accuracy": round(result["metadata"]["validation"]["balanced_accuracy"], 4),
                "out_of_sample_balanced_accuracy": round(result["metadata"]["out_of_sample_test"]["balanced_accuracy"], 4),
                "deployment_approved": False,
                "message": "Candidate trained and evaluated; production model was not modified.",
            }
        except Exception as exc:
            logger.exception("Candidate retraining failed")
            return {"success": False, "deployment_approved": False, "message": str(exc)}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(ModelRetrainer().retrain())
