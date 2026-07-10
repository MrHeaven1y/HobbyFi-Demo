import requests
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("app.retrieval.embedder")

class Embedder:
    
    """Singleton Wrapper for the Hugging Face Inference API."""
    _instance = None

    def __new__(cls, *args, **kwargs): # called before __init__ constructor
        if cls._instance is None: # class variable
            logger.info("initializing_hf_embedder", model="all-MiniLM-L6-v2")
            cls._instance = super(Embedder, cls).__new__(cls)
            cls._instance.api_url = "https://api-inference.huggingface.co/pipeline/feature-extraction/sentence-transformers/all-MiniLM-L6-v2"
            cls._instance.headers = {"Authorization": f"Bearer {settings.HUGGINGFACE_TOKEN}"}
            logger.info("hf_embedder_initialized")

        return cls._instance

    def embed(self, text: str) -> list[float]: # embedding function
        """Embeds a single string into a vector via Hugging Face API."""
        try:
            response = requests.post(
                self.api_url, 
                headers=self.headers, 
                json={"inputs": [text]}
            )
            response.raise_for_status()
            # HF returns a list of embeddings. Return the first one.
            return response.json()[0]
        except Exception as e:
            logger.error("hf_embedding_failed", error=str(e))
            raise