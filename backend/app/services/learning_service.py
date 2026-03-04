import os
import json
import logging
import pandas as pd
import lightgbm as lgb
from typing import List, Dict, Any
from sklearn.model_selection import train_test_split

logger = logging.getLogger(__name__)

FEEDBACK_LOG_PATH = "feedback_logs.jsonl"
MODEL_PATH = "lgb_ranker.txt"

class LearningToRankService:
    def __init__(self):
        self.model = None
        self._load_model()
        
    def _load_model(self):
        """Load trained LightGBM ranker if it exists."""
        if os.path.exists(MODEL_PATH):
            try:
                self.model = lgb.Booster(model_file=MODEL_PATH)
                logger.info("Adaptive Ranking Model (LightGBM) Loaded.")
            except Exception as e:
                logger.error(f"Failed to load ranker model: {e}")

    def log_feedback(self, query: str, dataset_id: str, event_type: str, features: Dict[str, float]):
        """
        Record user interaction (click, download). 
        Maps events to a pseudo-relevance score.
        """
        relevance = 0
        if event_type == "click":
            relevance = 1
        elif event_type == "bookmark":
            relevance = 2
        elif event_type == "download":
            relevance = 3
            
        record = {
            "query": query,
            "dataset_id": dataset_id,
            "relevance": relevance,
            "E_i": features.get("semantic", 0),
            "T_i": features.get("task", 0),
            "Q_i": features.get("quality", 0),
            "L_i": features.get("license", 0),
            "F_i": features.get("freshness", 0),
            "G_i": features.get("graph", 0)
        }
        
        with open(FEEDBACK_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
            
        logger.info(f"Logged {event_type} feedback for {dataset_id}")

    def train_model(self):
        """
        Trains LightGBM lambdarank model on accumulated feedback data.
        Needs sufficient data grouped by query.
        """
        if not os.path.exists(FEEDBACK_LOG_PATH):
            return "No training data available."
            
        df = pd.read_json(FEEDBACK_LOG_PATH, lines=True)
        if len(df) < 20: 
            return "Need at least 20 interaction events to train adaptive model."

        # Group data by query for Lambdarank
        df = df.sort_values(by="query")
        
        X = df[['E_i', 'T_i', 'Q_i', 'L_i', 'F_i', 'G_i']]
        y = df['relevance']
        groups = df.groupby('query').size().values
        
        # Train model
        train_data = lgb.Dataset(X, label=y, group=groups)
        
        params = {
            'objective': 'lambdarank',
            'metric': 'ndcg',
            'ndcg_eval_at': [7],
            'learning_rate': 0.05,
            'num_leaves': 15,
            'verbose': -1
        }
        
        self.model = lgb.train(params, train_data, num_boost_round=100)
        self.model.save_model(MODEL_PATH)
        
        return "Model trained successfully and saved."

    def predict_score(self, features: Dict[str, float]) -> float:
        """
        Produce dynamic ranking score.
        Falls back to static heuristic formula if machine isn't trained yet.
        """
        X = [[
            features.get("semantic", 0),
            features.get("task", 0),
            features.get("quality", 0),
            features.get("license", 0),
            features.get("freshness", 0),
            features.get("graph", 0)
        ]]
        
        if self.model:
            return float(self.model.predict(X)[0])
        else:
            # Fallback to Phase 3 heuristics mapping
            return (
                0.30 * X[0][0] +
                0.30 * X[0][1] +
                0.15 * X[0][2] +
                0.10 * X[0][3] +
                0.10 * X[0][4] +
                0.05 * X[0][5]
            )

learning_ranker = LearningToRankService()
