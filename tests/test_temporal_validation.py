import unittest
import pandas as pd

from ml.temporal_validation import chronological_purged_split


class TemporalSplitTests(unittest.TestCase):
    def test_chronological_split_purges_label_horizon(self):
        X = pd.DataFrame({"f": range(200)})
        y = pd.Series([0, 1] * 100)
        split = chronological_purged_split(X, y, lookahead=12)
        b = split.boundaries
        self.assertEqual(split.X_train.iloc[-1, 0], b["train"][1] - 1)
        self.assertEqual(split.X_validation.iloc[0, 0], b["validation"][0])
        self.assertEqual(split.X_test.iloc[0, 0], b["test"][0])
        self.assertEqual(b["purge_after_train"][1] - b["purge_after_train"][0], 12)
        self.assertEqual(b["purge_after_validation"][1] - b["purge_after_validation"][0], 12)

    def test_rejects_non_binary_fold_missing_class(self):
        X = pd.DataFrame({"f": range(200)})
        y = pd.Series([0] * 200)
        with self.assertRaises(ValueError):
            chronological_purged_split(X, y, lookahead=12)

    def test_purge_counts_original_candles_when_neutral_targets_exist(self):
        X = pd.DataFrame({"f": range(200)})
        y = pd.Series([0 if i % 2 == 0 else 1 for i in range(200)], dtype=float)
        # Many neutral observations; they must not shrink the purge distance.
        y.iloc[::3] = float("nan")
        split = chronological_purged_split(X, y, lookahead=12)
        b = split.boundaries
        self.assertEqual(b["purge_after_train"][1] - b["purge_after_train"][0], 12)
        self.assertEqual(b["purge_after_validation"][1] - b["purge_after_validation"][0], 12)
        self.assertLess(split.X_train.iloc[-1, 0], b["train"][1])
        self.assertTrue(split.y_train.notna().all())


if __name__ == "__main__":
    unittest.main()
