"""
Agent Long-Term Memory (LTM) Store
-----------------------------------
Persists successful discovery outcomes to Neo4j to:
1. Improve future search speed (cache previous hits)
2. Learn which search variants work for specific domains
3. Build a "Knowledge Graph" of dataset-task-query relationships
"""

import logging
from typing import List, Dict, Any, Optional
from app.services.graph_service import graph_service

logger = logging.getLogger(__name__)

class MemoryStore:
    """
    Handles the persistence and retrieval of agent experiences.
    Uses Neo4j as the underlying storage engine.
    """

    def __init__(self):
        self.graph = graph_service

    async def save_session_outcome(
        self, 
        query: str, 
        domain: str, 
        tasks: List[str], 
        top_datasets: List[Dict[str, Any]],
        confidence: float
    ):
        """
        Saves the best results of a discovery session to the graph memory.
        Creates relationships: (Query)-[:SUCCESSFUL_RECO]->(Dataset)
        """
        if not self.graph._ensure_driver() or not top_datasets:
            return

        with self.graph.driver.session() as session:
            try:
                # 1. Ensure Query and Domain nodes exist
                session.run("""
                    MERGE (q:Query {text: $query})
                    SET q.domain = $domain, q.confidence = $confidence, q.last_run = datetime()
                """, {"query": query, "domain": domain, "confidence": confidence})

                # 2. Link successful datasets
                # We only store top relevance ones to keep memory clean
                successful_ids = [d["id"] for d in top_datasets[:10]]
                
                session.run("""
                    MATCH (q:Query {text: $query})
                    UNWIND $datasets AS ds_data
                    MERGE (d:Dataset {id: ds_data.id})
                    SET d.source = ds_data.source, d.downloads = ds_data.downloads
                    MERGE (q)-[r:SUCCESSFUL_RECO]->(d)
                    SET r.relevance_at_time = coalesce(ds_data.similarity_score, 0.5),
                        r.timestamp = datetime()
                """, {"query": query, "datasets": top_datasets[:10]})

            except Exception as e:
                logger.error(f"Failed to save session outcome to MemoryStore: {e}")

    async def get_past_experience(self, query: str, domain: str) -> List[Dict[str, Any]]:
        """
        Checks if we have similar past queries and successful datasets.
        """
        if not self.graph._ensure_driver():
            return []

        with self.graph.driver.session() as session:
            try:
                # Search for similar queries or exact matches
                # In a real system, we'd use vector search on the Query nodes.
                # For now, we'll do simple text match or domain-based retrieval.
                # Fixed: Pass parameters as a dict to avoid clash with session.run's 'query' argument
                result = session.run("""
                    MATCH (q:Query)-[r:SUCCESSFUL_RECO]->(d:Dataset)
                    WHERE q.text CONTAINS $query_text OR q.domain = $domain
                    RETURN d.id AS id, d.source AS source, d.downloads AS downloads, 
                           r.relevance_at_time AS score, q.text AS past_query
                    ORDER BY r.relevance_at_time DESC
                    LIMIT 10
                """, {"query_text": query, "domain": domain})

                experiences = []
                for record in result:
                    experiences.append({
                        "id": record["id"],
                        "source": record["source"],
                        "downloads": record["downloads"],
                        "relevance": record["score"],
                        "reason": f"Found via past successful query: '{record['past_query']}'",
                        "is_memory_hit": True
                    })
                return experiences

            except Exception as e:
                logger.error(f"Failed to retrieve experience from MemoryStore: {e}")
                return []

    async def record_feedback(self, query: str, dataset_id: str, event_type: str):
        """
        Strengthens the memory link between a query and a dataset 
        when a user interacts with it.
        """
        if not self.graph._ensure_driver():
            return

        # Weight of the interaction
        weight = 0.2 if event_type == 'click' else 0.5 # bookmark/download

        with self.graph.driver.session() as session:
            try:
                session.run("""
                    MATCH (q:Query {text: $query})
                    MATCH (d:Dataset {id: $dataset_id})
                    MERGE (q)-[r:SUCCESSFUL_RECO]->(d)
                    SET r.relevance_at_time = coalesce(r.relevance_at_time, 0.5) + $weight,
                        r.last_interaction = datetime(),
                        r.interactions = coalesce(r.interactions, 0) + 1
                    WITH r
                    SET r.relevance_at_time = CASE WHEN r.relevance_at_time > 1.0 THEN 1.0 ELSE r.relevance_at_time END
                """, {"query": query, "dataset_id": dataset_id, "weight": weight})
            except Exception as e:
                logger.error(f"Failed to record memory feedback: {e}")

# Singleton instance
memory_store = MemoryStore()
