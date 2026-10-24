from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env', override=False)

def local_path(key: str, default: str) -> Path:
    path = Path(os.getenv(key, default))
    return path if path.is_absolute() else ROOT / path

@dataclass(frozen=True)
class Settings:
    db: Path = local_path('OPSPILOT_DB', 'runtime/opspilot.db')
    chroma: Path = local_path('OPSPILOT_CHROMA', 'runtime/chroma')
    model_cache: Path = local_path('OPSPILOT_MODEL_CACHE', 'runtime/models')
    embedding_model: str = os.getenv('OPSPILOT_EMBEDDING_MODEL', 'sentence-transformers/all-MiniLM-L6-v2')
    api_key: str = os.getenv('LLM_API_KEY', '')
    model: str = os.getenv('LLM_MODEL', '')
    base_url: str = os.getenv('LLM_BASE_URL', 'https://api.openai.com/v1')
    timeout: float = float(os.getenv('LLM_TIMEOUT', '30'))

    @property
    def mode(self) -> str:
        return 'llm' if self.api_key and self.model else 'offline_demo'

settings = Settings()
