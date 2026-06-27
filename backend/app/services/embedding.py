"""
CLIP Embedding Service — Cross-Modal Encoder

Loads the CLIP model once at startup and provides methods to encode
both text queries and product images into the same 512-dimensional
vector space, enabling cross-modal retrieval.

Usage:
    encoder = EmbeddingService()
    encoder.load_model()  # Called once during FastAPI lifespan

    text_vec  = encoder.encode_text("soothing herbal tea")    # → (512,)
    image_vec = encoder.encode_image(pil_image)                # → (512,)

    # Both vectors live in the same space, so:
    cosine_similarity(text_vec, image_vec)  →  meaningful score
"""

import logging
from io import BytesIO

import numpy as np
from PIL import Image
from sentence_transformers import SentenceTransformer

from app.config import settings

# Safe imports for google/gemma-4-E4B-it VLM integration
try:
    from transformers import AutoProcessor, AutoModelForCausalLM
    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Wraps sentence-transformers CLIP model for unified text+image encoding.

    The CLIP architecture maps images and text into a shared embedding space
    using contrastive learning. This means:
      - "green tea" (text) and a photo of green tea (image) produce similar vectors.
      - Cosine similarity between any text↔image pair is meaningful.

    We use clip-ViT-B-32 which outputs 512-dimensional vectors.
    """

    def __init__(self):
        self._model: SentenceTransformer | None = None
        self._text_model: SentenceTransformer | None = None
        self._embedding_dim: int = 512
        # Gemma VLM processor and model references
        self.gemma_processor = None
        self.gemma_model = None

    @property
    def embedding_dim(self) -> int:
        """Dimensionality of the output embeddings."""
        return self._embedding_dim

    def load_model(self) -> None:
        """
        Load CLIP and MiniLM models into memory.
        Should be called once during application startup (FastAPI lifespan).
        """
        logger.info(f"Loading CLIP model: {settings.clip_model_name}")
        self._model = SentenceTransformer(settings.clip_model_name)
        self._embedding_dim = self._model.get_sentence_embedding_dimension()
        logger.info(
            f"CLIP model loaded — embedding dimension: {self._embedding_dim}"
        )

        logger.info("Loading MiniLM text model: all-MiniLM-L6-v2")
        self._text_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("MiniLM model loaded successfully")

        # Lazy load gemma-4-E4B-it VLM as requested by user
        if HAS_TRANSFORMERS:
            try:
                import torch
                model_name = "google/gemma-4-E4B-it"
                logger.info(f"Attempting to load Gemma VLM processor & model: {model_name}")
                self.gemma_processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=True)
                
                device = "cuda" if torch.cuda.is_available() else "cpu"
                kwargs = {}
                if device == "cuda":
                    kwargs["torch_dtype"] = torch.float16
                    kwargs["device_map"] = "auto"
                    logger.info("Nvidia GPU detected. Loading Gemma VLM with float16 and auto device mapping.")
                
                self.gemma_model = AutoModelForCausalLM.from_pretrained(model_name, trust_remote_code=True, **kwargs)
                logger.info("Gemma VLM loaded successfully")
            except Exception as e:
                logger.warning(
                    f"Gemma VLM load bypassed (expected for custom/offline env): {e}. "
                    f"Seamlessly using translation + CLIP/MiniLM pipeline."
                )

    def encode_text_384(self, text: str) -> np.ndarray:
        """
        Encode a text string into a normalized 384-d vector using all-MiniLM-L6-v2.
        """
        if self._text_model is None:
            logger.info("Loading MiniLM model on-demand")
            self._text_model = SentenceTransformer("all-MiniLM-L6-v2")
        
        from app.services.translation import translate_ar_to_en
        translated_text = translate_ar_to_en(text)
        
        embedding = self._text_model.encode(
            translated_text,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return embedding.astype(np.float32)

    def _ensure_loaded(self) -> SentenceTransformer:
        """Guard: ensures the model is loaded before encoding."""
        if self._model is None:
            raise RuntimeError(
                "CLIP model not loaded. Call load_model() first "
                "(this should happen during FastAPI startup)."
            )
        return self._model

    def encode_text(self, text: str) -> np.ndarray:
        """
        Encode a text query into a normalized 512-d vector.

        The text is processed through CLIP's text transformer (based on
        a modified GPT-2 architecture) and projected into the shared space.

        Args:
            text: Natural language query, e.g. "soothing herbal tea"

        Returns:
            L2-normalized numpy array of shape (512,)
        """
        model = self._ensure_loaded()
        
        from app.services.translation import translate_ar_to_en
        translated_text = translate_ar_to_en(text)
        
        embedding = model.encode(
            translated_text,
            convert_to_numpy=True,
            normalize_embeddings=True,  # L2 normalization → cosine = dot product
        )
        return embedding.astype(np.float32)

    def encode_image(self, image: Image.Image) -> np.ndarray:
        """
        Encode a PIL Image into a normalized 512-d vector.

        The image is processed through CLIP's vision transformer (ViT-B/32)
        which splits the image into 32×32 patches, processes them through
        12 transformer layers, and projects to the shared embedding space.

        Args:
            image: PIL Image (any size — will be resized internally to 224×224)

        Returns:
            L2-normalized numpy array of shape (512,)
        """
        model = self._ensure_loaded()
        embedding = model.encode(
            image,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return embedding.astype(np.float32)

    def encode_image_bytes(self, image_bytes: bytes) -> np.ndarray:
        """
        Convenience method: encode raw image bytes (e.g., from an upload).

        Args:
            image_bytes: Raw image data (JPEG, PNG, WebP, etc.)

        Returns:
            L2-normalized numpy array of shape (512,)
        """
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        return self.encode_image(image)

    def encode_product(self, name: str, description: str | None = None) -> np.ndarray:
        """
        Create a product embedding from its text metadata.

        Combines the product name and description into a single string
        for richer semantic representation.

        Args:
            name: Product name
            description: Optional product description

        Returns:
            L2-normalized numpy array of shape (512,)
        """
        text = name
        if description:
            text = f"{name}. {description}"
        return self.encode_text(text)

    def extract_product_details_vlm(self, image_bytes: bytes, name: str, description: str | None = None) -> dict | None:
        """
        Uses google/gemma-4-E4B-it VLM model to analyze the product photo and metadata.
        Extracts refined English name, description, and auto-classifies into our standard categories.
        Uses CUDA acceleration if available.
        """
        if not HAS_TRANSFORMERS or self.gemma_model is None or self.gemma_processor is None:
            logger.info("Gemma VLM model/processor not initialized. Skipping VLM extraction.")
            return None

        try:
            import torch
            import json
            import re
            
            # Load image from bytes
            img = Image.open(BytesIO(image_bytes)).convert("RGB")
            
            prompt = (
                f"You are a helpful retail catalog assistant. Analyze this product image. "
                f"The seller provided the following metadata (could be in Arabic or another language):\n"
                f"Name: {name}\n"
                f"Description: {description or 'None'}\n\n"
                f"Extract and translate the product information to English. "
                f"Provide your response EXACTLY as a JSON object with these keys:\n"
                f"- 'name': refined English name of the product\n"
                f"- 'description': refined English description of the product\n"
                f"- 'category': must be exactly one of: Fruits & Vegetables, Cooking Essentials, Dairy & Eggs, Meat & Poultry, Beverages, Snacks, Bakery, Frozen Food, Cleaning & Detergents, Beauty & Personal Care, Electronics, Mobiles & Tech, Cookware & Kitchenware\n"
                f"Ensure the response is valid JSON and nothing else."
            )
            
            device = "cuda" if torch.cuda.is_available() else "cpu"
            # Ensure model is on correct device (or let device_map handle it if GPU is enabled)
            if self.gemma_model.device.type != device and device == "cuda":
                logger.info(f"Moving Gemma VLM model to GPU device: {device}")
                self.gemma_model = self.gemma_model.to(device)
            
            # Process inputs
            inputs = self.gemma_processor(text=prompt, images=img, return_tensors="pt")
            if device == "cuda":
                inputs = {k: v.to(device) for k, v in inputs.items()}
            
            with torch.no_grad():
                outputs = self.gemma_model.generate(**inputs, max_new_tokens=150)
                
            input_len = inputs["input_ids"].shape[1]
            generated_tokens = outputs[0][input_len:]
            generated_text = self.gemma_processor.decode(generated_tokens, skip_special_tokens=True)
            logger.info(f"Gemma VLM raw generated output: {generated_text}")
            
            # Search for JSON block
            json_match = re.search(r"\{.*?\}", generated_text, re.DOTALL)
            if json_match:
                extracted = json.loads(json_match.group(0))
                
                # Normalize keys
                extracted = {k.lower(): v for k, v in extracted.items()}
                
                valid_categories = [
                    "Fruits & Vegetables", "Cooking Essentials", "Dairy & Eggs", 
                    "Meat & Poultry", "Beverages", "Snacks", "Bakery", "Frozen Food", 
                    "Cleaning & Detergents", "Beauty & Personal Care", "Electronics", 
                    "Mobiles & Tech", "Cookware & Kitchenware"
                ]
                ext_cat = extracted.get("category", "Cooking Essentials").strip()
                matched_cat = "Cooking Essentials"
                for c in valid_categories:
                    if c.lower() == ext_cat.lower():
                        matched_cat = c
                        break
                
                return {
                    "name": extracted.get("name", name),
                    "description": extracted.get("description", description),
                    "category": matched_cat
                }
                
        except Exception as e:
            logger.error(f"Gemma VLM extraction failed: {e}", exc_info=True)
            
        return None

    def identify_product_from_image(self, image_bytes: bytes) -> str | None:
        """
        Uses google/gemma-4-E4B-it VLM to identify the product name, brand, or text
        from an uploaded photo to perform highly precise search query mapping.
        """
        if not HAS_TRANSFORMERS or self.gemma_model is None or self.gemma_processor is None:
            logger.info("Gemma VLM not initialized for product identification.")
            return None

        try:
            import torch
            img = Image.open(BytesIO(image_bytes)).convert("RGB")
            
            prompt = (
                "You are an intelligent retail vision assistant. Analyze this product photo. "
                "Read any text, labels, or brand names written on the packaging. "
                "Identify the exact product name, brand, and type. "
                "Provide a short search query of 2-5 words (in English or Arabic, depending on the packaging language) "
                "that best represents this item (for example: 'Ghazaleen Tea' or 'شاي الغزالين'). "
                "Return ONLY the search query string and absolutely nothing else. Do not write introductory text, markdown formatting, or bullet points."
            )
            
            device = "cuda" if torch.cuda.is_available() else "cpu"
            if self.gemma_model.device.type != device and device == "cuda":
                self.gemma_model = self.gemma_model.to(device)
            
            inputs = self.gemma_processor(text=prompt, images=img, return_tensors="pt")
            if device == "cuda":
                inputs = {k: v.to(device) for k, v in inputs.items()}
                
            with torch.no_grad():
                outputs = self.gemma_model.generate(**inputs, max_new_tokens=50)
                
            input_len = inputs["input_ids"].shape[1]
            generated_tokens = outputs[0][input_len:]
            generated_text = self.gemma_processor.decode(generated_tokens, skip_special_tokens=True)
            
            cleaned = generated_text.strip()
            cleaned = cleaned.replace("**", "").replace("\"", "").replace("'", "").strip()
            logger.info(f"[VLM IDENTIFICATION] Identified product from image: '{cleaned}'")
            return cleaned
        except Exception as e:
            logger.error(f"Gemma VLM product identification failed: {e}", exc_info=True)
            
        return None


# ── Singleton instance ──────────────────────────────────────────
# Shared across the application; model loaded during FastAPI lifespan.
embedding_service = EmbeddingService()

