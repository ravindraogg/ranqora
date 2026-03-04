import logging
import math
import networkx as nx
from typing import List, Dict, Any
from neo4j import GraphDatabase, exceptions

from app.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

logger = logging.getLogger(__name__)

class GraphService:
    def __init__(self):
        self.driver = None
        try:
            self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            self.driver.verify_connectivity()
            self._init_schema()
            logger.info("Connected to Neo4j successfully. Graph Engine enabled.")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j on boot: {e}")

    def _ensure_driver(self) -> bool:
        """Reconnect to Neo4j if the driver is not set (e.g. Neo4j started after the app)."""
        if self.driver:
            try:
                self.driver.verify_connectivity()
                return True
            except Exception:
                self.driver = None  # stale — force reconnect below
        try:
            self.driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
            self.driver.verify_connectivity()
            self._init_schema()  # ensure constraints are present on reconnect
            logger.info("Reconnected to Neo4j successfully.")
            return True
        except Exception as e:
            logger.warning(f"Neo4j not reachable: {e}")
            return False

    def _init_schema(self):
        """Create constraints to optimize graph ingestions."""
        if not self._ensure_driver():
            return
            
        queries = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (d:Dataset) REQUIRE d.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (q:Query) REQUIRE q.text IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Paper) REQUIRE p.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Task) REQUIRE t.name IS UNIQUE"
        ]
        with self.driver.session() as session:
            for q in queries:
                session.run(q)

    def ingest_candidates(self, query: str, tasks: List[str] | None, candidates: List[Dict[str, Any]]):
        """
        Ingest the retrieved targets into Neo4j graph.
        Links Datasets to the Query, extracted Tasks, and dynamically creates Paper nodes from ArXiv.
        """
        if not self._ensure_driver() or not candidates:
            return

        with self.driver.session() as session:
            # Upsert Query context
            try:
                session.run("MERGE (q:Query {text: $query_text})", query_text=query)
                if tasks:
                    session.run("""
                        MATCH (q:Query {text: $query_text})
                        UNWIND $tasks AS task_name
                        MERGE (t:Task {name: toLower(task_name)})
                        MERGE (q)-[:ALIGNED_TO]->(t)
                    """, query_text=query, tasks=tasks)
            except Exception as e:
                logger.error(f"Failed to ingest query context into Neo4j: {e}")
                raise

            for cand in candidates:
                ds_id = cand["id"]
                source = cand["source"]
                tags = cand.get("tags", [])
                
                try:
                    if source == "arxiv":
                        session.run("""
                            MERGE (p:Paper {id: $id})
                            SET p.url = $url, p.title = $desc
                            WITH p
                            MATCH (q:Query {text: $query_text})
                            MERGE (q)-[:RETRIEVED]->(p)
                        """, id=ds_id, url=cand.get("url", ""), desc=cand.get("description", "")[:100], query_text=query)
                        
                        if tags:
                            session.run("""
                                MATCH (p:Paper {id: $id})
                                UNWIND $tags AS tag
                                MERGE (d:Dataset {id: tag})
                                MERGE (p)-[:CITES_DATASET]->(d)
                            """, id=ds_id, tags=tags)
                    else:
                        session.run("""
                            MERGE (d:Dataset {id: $id})
                            SET d.source = $source, d.downloads = $downloads, d.likes = $likes
                            WITH d
                            MATCH (q:Query {text: $query_text})
                            MERGE (q)-[:RETRIEVED]->(d)
                        """, id=ds_id, source=source, downloads=cand.get("downloads", 0), likes=cand.get("likes", 0), query_text=query)
                        
                        if tags:
                            session.run("""
                                MATCH (d:Dataset {id: $id})
                                UNWIND $tags AS tag
                                MERGE (t:Task {name: toLower(tag)})
                                MERGE (d)-[:USE_CASE]->(t)
                            """, id=ds_id, tags=tags)
                except Exception as e:
                    logger.error(f"Failed to ingest candidate {ds_id}: {e}")
                    raise


    def calculate_graph_scores(self, candidate_ids: List[str]) -> Dict[str, float]:
        """
        Calculates pure Graph Centrality Score (G_i) for the given candidates.
        G_i = normalized( 0.5 * log(1 + citations) + 0.5 * PageRank(D_i) )
        
        This is PURE centrality — no downloads/likes here (those go into P_i).
        Uses NetworkX for PageRank to avoid requiring Neo4j Enterprise GDS plugin.
        """
        scores = {ds_id: 0.0 for ds_id in candidate_ids}
        if not self._ensure_driver():
            return scores
            
        with self.driver.session() as session:
            # 1. Pull the subgraph structure
            edges_result = session.run("""
                MATCH (n)-[r]->(m)
                WHERE (n:Dataset OR n:Paper OR n:Query) AND (m:Dataset OR m:Paper OR m:Query OR m:Task)
                RETURN elementId(n) AS source, elementId(m) AS target, 
                       labels(m) AS target_labels, m.id AS target_id
            """)
            
            # 2. Build local NX DiGraph
            G = nx.DiGraph()
            
            # 3. Citation counts (In-Degree for CITES_DATASET or RETRIEVED edges)
            citations = {ds_id: 0 for ds_id in candidate_ids}
            
            for record in edges_result:
                u = record["source"]
                v = record["target"]
                G.add_edge(u, v)
                
                t_id = record["target_id"]
                if t_id and t_id in citations:
                    citations[t_id] += 1
            
            # 4. Compute PageRank
            try:
                pagerank = nx.pagerank(G, alpha=0.85, max_iter=100)
            except Exception:
                pagerank = {}

            # 5. Map neo4j elementIds back to dataset IDs
            id_mapping_result = session.run("""
                MATCH (d:Dataset)
                WHERE d.id IN $candidates
                RETURN d.id AS ds_id, elementId(d) AS internal_id
            """, candidates=candidate_ids)
            
            internal_map = {rec["ds_id"]: rec["internal_id"] for rec in id_mapping_result}
            
            # 6. Composite G_i = pure centrality only
            max_cite = max(citations.values()) if citations else 1
            
            for ds_id in candidate_ids:
                internal_id = internal_map.get(ds_id)
                
                cite_count = citations.get(ds_id, 0)
                c_score = math.log1p(cite_count) / math.log1p(max_cite) if max_cite > 0 else 0.0
                
                p_score = pagerank.get(internal_id, 0.0)
                
                raw_g = (0.5 * c_score) + (0.5 * min(p_score * 100, 1.0))
                scores[ds_id] = min(max(raw_g, 0.0), 1.0)
                
        return scores

# Module singleton
graph_service = GraphService()
