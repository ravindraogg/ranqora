import logging
import threading
import math
import networkx as nx
from typing import List, Dict, Any
from neo4j import GraphDatabase, exceptions

from app.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
from app.services.embedding_service import get_embeddings
from sklearn.metrics.pairwise import cosine_similarity

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
            "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Task) REQUIRE t.name IS UNIQUE",
            # Drop old index if exists and recreate with correct dimension (384)
            "DROP INDEX dataset_vector_index IF EXISTS",
            "CREATE VECTOR INDEX dataset_vector_index IF NOT EXISTS FOR (d:Dataset) ON (d.embedding) OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}}"
        ]
        with self.driver.session() as session:
            for q in queries:
                try:
                    session.run(q)
                except Exception as e:
                    logger.warning(f"Schema query failed (non-fatal): {q} - {e}")

    def ingest_candidates(self, query: str, tasks: List[str] | None, candidates: List[Dict[str, Any]], domain: str | None = None, stop_event: threading.Event | None = None):
        """
        Ingest the retrieved targets into Neo4j graph.
        Links Datasets to the Query, extracted Tasks, and dynamically creates Paper nodes from ArXiv.
        """
        if not self._ensure_driver() or not candidates:
            return

        datasets_to_embed = []
        for cand in candidates:
            if cand.get("source") != "arxiv":
                desc = cand.get("description", "") or ""
                title = cand.get("id", "") or ""
                datasets_to_embed.append({
                    "id": cand["id"],
                    "text": title + " " + desc[:200]
                })
        
        sim_edges = []
        if datasets_to_embed:
            texts = [d["text"] for d in datasets_to_embed]
            try:
                embs = get_embeddings(texts)
                sim_matrix = cosine_similarity(embs)
                for i in range(len(datasets_to_embed)):
                    for j in range(i + 1, len(datasets_to_embed)):
                        if sim_matrix[i][j] > 0.75:
                            sim_edges.append((datasets_to_embed[i]["id"], datasets_to_embed[j]["id"]))
            except Exception as e:
                logger.error(f"Failed to compute embeddings for similarity edges: {e}")

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

        # Prepare batches for UNWIND
        papers_batch = []
        datasets_batch = []
        
        for cand in candidates:
            ds_id = cand["id"]
            source = cand["source"]
            tags = cand.get("tags", [])
            
            if source == "arxiv":
                papers_batch.append({
                    "id": ds_id,
                    "url": cand.get("url", ""),
                    "title": cand.get("description", "")[:100],
                    "citations": cand.get("citations", cand.get("citationCount", 1)),
                    "tags": tags
                })
            else:
                datasets_batch.append({
                    "id": ds_id,
                    "source": source,
                    "downloads": cand.get("downloads", 0),
                    "likes": cand.get("likes", 0),
                    "tags": tags,
                    "score": cand.get("similarity_score", 0)
                })

        if stop_event and stop_event.is_set():
            logger.info("Graph ingestion aborted via stop_event.")
            return

        with self.driver.session() as session:
            try:
                # 1. Upsert Query & Tasks (Fix 4: Add q.domain)
                session.run(
                    "MERGE (q:Query {text: $query_text}) SET q.domain = $domain", 
                    query_text=query,
                    domain=domain or (tasks[0] if tasks else "general")
                )
                if tasks:
                    session.run("""
                        MATCH (q:Query {text: $query_text})
                        UNWIND $tasks AS t_name
                        MERGE (t:Task {name: toLower(t_name)})
                        MERGE (q)-[:ALIGNED_TO]->(t)
                    """, query_text=query, tasks=tasks)

                # 2. Batch Paper Ingestion
                if papers_batch:
                    session.run("""
                        UNWIND $batch AS p_data
                        MERGE (p:Paper {id: p_data.id})
                        SET p.url = p_data.url, p.title = p_data.title, p.citations = p_data.citations
                        WITH p, p_data
                        MATCH (q:Query {text: $query_text})
                        MERGE (q)-[:RETRIEVED]->(p)
                        WITH p, p_data
                        UNWIND p_data.tags AS tag
                        MERGE (d:Dataset {id: tag})
                        MERGE (p)-[:CITES_DATASET]->(d)
                    """, batch=papers_batch, query_text=query)

                # 3. Batch Practical Dataset Ingestion (Fix 3: Add SUCCESSFUL_RECO properly)
                if datasets_batch:
                    session.run("""
                        UNWIND $batch AS d_data
                        MERGE (d:Dataset {id: d_data.id})
                        SET d.source = d_data.source, d.downloads = d_data.downloads, d.likes = d_data.likes
                        WITH d, d_data
                        MERGE (s:Source {name: d_data.source})
                        MERGE (s)-[:HOSTS]->(d)
                        WITH d, d_data
                        MATCH (q:Query {text: $query_text})
                        MERGE (q)-[:RETRIEVED]->(d)
                        MERGE (q)-[r:SUCCESSFUL_RECO]->(d)
                        SET r.relevance_at_time = d_data.score
                        WITH d, d_data
                        UNWIND d_data.tags AS tag
                        MERGE (t:Task {name: toLower(tag)})
                        MERGE (d)-[:USED_FOR]->(t)
                        MERGE (t)-[:USES]->(d)
                    """, batch=datasets_batch, query_text=query)
                    
                    # Benchmark Relationships
                    if tasks:
                        session.run("""
                            UNWIND $batch AS d_data
                            MATCH (d:Dataset {id: d_data.id})
                            WHERE d_data.downloads > 5000 
                               OR any(t in d_data.tags WHERE t CONTAINS 'benchmark' OR t CONTAINS 'dataset')
                            UNWIND $tasks AS task_name
                            MERGE (t:Task {name: toLower(task_name)})
                            MERGE (d)-[:BENCHMARK_FOR]->(t)
                        """, batch=datasets_batch, tasks=tasks)
            except Exception as e:
                logger.error(f"Failed to batch ingest results into Neo4j: {e}")
                # Don't raise, graph is enrichment

            if sim_edges:
                try:
                    session.run("""
                        UNWIND $edges AS edge
                        MATCH (d1:Dataset {id: edge[0]})
                        MATCH (d2:Dataset {id: edge[1]})
                        MERGE (d1)-[:SIMILAR_TO]->(d2)
                        MERGE (d2)-[:SIMILAR_TO]->(d1)
                    """, edges=sim_edges)
                except Exception as e:
                    logger.error(f"Failed to ingest similarity edges: {e}")


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
                MATCH (n)-[r]-(m)
                WHERE (n:Dataset AND n.id IN $candidates) 
                   OR (m:Dataset AND m.id IN $candidates)
                RETURN elementId(n) AS source, elementId(m) AS target, 
                       labels(m) AS target_labels, m.id AS target_id,
                       type(r) AS rel_type, n.citations AS source_citations
            """, candidates=candidate_ids)
            
            # 2. Build local NX DiGraph
            G = nx.DiGraph()
            
            # 3. Citation counts (In-Degree for CITES_DATASET or RETRIEVED edges)
            citations = {ds_id: 0 for ds_id in candidate_ids}
            
            for record in edges_result:
                u = record["source"]
                v = record["target"]
                rel = record["rel_type"]
                src_cites = record.get("source_citations")
                src_cites = int(src_cites) if src_cites else 1
                
                weight = 1.0
                if rel == "CITES_DATASET":
                    weight = 3.0 + min(float(src_cites) * 0.1, 10.0)
                elif rel in ("SIMILAR_TO", "CITES"):
                    weight = 2.0
                elif rel == "BENCHMARK_FOR":
                    weight = 4.0
                    
                G.add_edge(u, v, weight=weight)
                
                t_id = record["target_id"]
                if t_id and t_id in citations:
                    if rel == "CITES_DATASET":
                        citations[t_id] += src_cites
                    else:
                        citations[t_id] += 1
            
            # 4. Compute PageRank
            try:
                pagerank = nx.pagerank(G, alpha=0.85, weight='weight', max_iter=100)
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

    def record_successful_discovery(self, query: str, dataset_id: str, score: float = 0.85):
        """
        Fix 7: Persist successful results in the graph.
        Links a query to a dataset with a SUCCESSFUL_RECO relationship.
        """
        if not self._ensure_driver():
            return
            
        with self.driver.session() as session:
            try:
                session.run("""
                    MERGE (q:Query {text: $query_text})
                    MERGE (d:Dataset {id: $dataset_id})
                    MERGE (q)-[r:SUCCESSFUL_RECO]->(d)
                    SET r.score = $score, r.timestamp = datetime()
                """, query_text=query, dataset_id=dataset_id, score=score)
            except Exception as e:
                logger.error(f"Failed to record successful discovery in Neo4j: {e}")

    def vector_search(self, embedding: List[float], top_k: int = 20) -> List[Dict[str, Any]]:
        """
        Fix 1: Embedding-based nearest neighbor search in Neo4j.
        Used for Query Expansion.
        """
        if not self._ensure_driver():
            return []
            
        results = []
        with self.driver.session() as session:
            try:
                # Use the vector index we created in _init_schema
                res = session.run("""
                    CALL db.index.vector.queryNodes('dataset_vector_index', $top_k, $emb)
                    YIELD node, score
                    RETURN node.id AS id, node.source AS source, labels(node) AS labels, score
                """, emb=embedding, top_k=top_k)
                
                for record in res:
                    results.append({
                        "id": record["id"],
                        "source": record["source"],
                        "labels": record["labels"],
                        "score": record["score"]
                    })
            except Exception as e:
                logger.warning(f"Vector search failed (likely index not ready or unsupported): {e}")
                
        return results

# Module singleton
graph_service = GraphService()
