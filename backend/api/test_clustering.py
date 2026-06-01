import sys
import os
sys.path.append(os.path.dirname(__file__))

from sqlalchemy.orm import Session
from sqlalchemy.orm import Session
from database import SessionLocal, Article
from datetime import datetime, timedelta, timezone
from embedder import _get_chroma
import numpy as np
import hdbscan

def test_clustering():
    db = SessionLocal()
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    articles = db.query(Article).filter(Article.embedding_indexed == 1, Article.created_at >= cutoff).all()
    print(f"Found {len(articles)} indexed articles.")

    collection = _get_chroma()
    if collection.count() == 0:
        print("Chroma is empty")
        return
    ids = [str(a.id) for a in articles]
    chroma_result = collection.get(ids=ids, include=["embeddings"])
    
    id_to_vector = {}
    for chroma_id, emb in zip(chroma_result["ids"], chroma_result["embeddings"]):
        id_to_vector[int(chroma_id)] = emb
        
    valid_articles = [a for a in articles if a.id in id_to_vector]
    print(f"Found {len(valid_articles)} valid vectors.")
    if not valid_articles:
        return

    vectors = [id_to_vector[a.id] for a in valid_articles]
    matrix = np.array(vectors, dtype=np.float32)
    
    # 1. Unnormalized
    labels_unnorm = hdbscan.HDBSCAN(min_cluster_size=3).fit_predict(matrix)
    print(f"Unnormalized clusters: {len(set(labels_unnorm) - {-1})}, Noise: {sum(labels_unnorm == -1)}")
    
    # 2. L2 Normalized
    matrix_norm = matrix / np.linalg.norm(matrix, axis=1, keepdims=True)
    labels_norm = hdbscan.HDBSCAN(min_cluster_size=3).fit_predict(matrix_norm)
    print(f"L2 Normalized clusters: {len(set(labels_norm) - {-1})}, Noise: {sum(labels_norm == -1)}")

    # 3. L2 Normalized with metric='euclidean' and higher min_cluster_size
    labels_norm2 = hdbscan.HDBSCAN(min_cluster_size=5).fit_predict(matrix_norm)
    print(f"L2 Normalized (min_size=5) clusters: {len(set(labels_norm2) - {-1})}, Noise: {sum(labels_norm2 == -1)}")

    # 4. Agglomerative Clustering
    from sklearn.cluster import AgglomerativeClustering
    labels_agg = AgglomerativeClustering(n_clusters=None, distance_threshold=0.5, metric='cosine', linkage='average').fit_predict(matrix)
    print(f"Agglomerative (thresh=0.5) clusters: {len(set(labels_agg))}")

    labels_agg2 = AgglomerativeClustering(n_clusters=None, distance_threshold=0.3, metric='cosine', linkage='average').fit_predict(matrix)
    print(f"Agglomerative (thresh=0.3) clusters: {len(set(labels_agg2))}")

if __name__ == "__main__":
    test_clustering()

    labels_eps = hdbscan.HDBSCAN(min_cluster_size=3, cluster_selection_epsilon=0.4).fit_predict(matrix_norm)
    print(f"HDBSCAN (eps=0.4) clusters: {len(set(labels_eps) - {-1})}, Noise: {sum(labels_eps == -1)}")
