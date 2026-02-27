from app.embeddings import HashFallbackEmbedder
from app.models import DatasetMetadata
from app.ranking import rank_datasets


def test_rank_datasets_returns_sorted_top_k():
    datasets = [
        DatasetMetadata(id="a", name="cats", description="cat images", tags=["vision"]),
        DatasetMetadata(id="b", name="finance", description="stock market time series", tags=["tabular"]),
        DatasetMetadata(id="c", name="medical", description="radiology scans", tags=["medical", "vision"]),
    ]
    ranked = rank_datasets(
        query="medical imaging segmentation",
        datasets=datasets,
        embedder=HashFallbackEmbedder(),
        top_k=2,
    )

    assert len(ranked) == 2
    assert ranked[0].score >= ranked[1].score
    assert ranked[0].rank == 1
    assert ranked[1].rank == 2
