from sentence_transformers import SentenceTransformer
from app.core.logging import get_logger

logger = get_logger("app.retrieval.embedder")

class Embedder:
    
    """Singleton Wrapper for the SentenceTransformer model."""
    _instance = None

    def __new__(cls, *args, **kwargs): # called before __init__ constructor
        if cls._instance is None: # class variable
            
            logger.info("loading_embedding_model", model="all-MiniLM-L6-v2")
            cls._instance = super(Embedder, cls).__new__(cls)
            cls._instance.model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Embedding_model_loaded")

        return cls._instance

    def embed(self, text: str) -> list[float]: # embedding function
        """Embeds a single string into a vector."""
        return self.model.encode(text).tolist()
    
    