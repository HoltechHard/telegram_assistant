import grpc
import riva.client
from settings.config import get_config

class WhisperGRPCClient:
    """
    Persistent authenticated gRPC client (Singleton).
    Supports:
      - NVIDIA Whisper Cloud (Primary/Fallback)
      - Local Riva (Primary/Fallback)
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        self.config = get_config()
        self.asr_local = None
        self.asr_cloud = None
        self._setup_local()
        self._setup_cloud()

    def _setup_local(self):
        if self.config.speech.riva_local_uri:
            try:
                auth = riva.client.Auth(
                    uri=self.config.speech.riva_local_uri,
                    use_ssl=False
                )
                self.asr_local = riva.client.ASRService(auth)
            except Exception:
                pass

    def _setup_cloud(self):
        if self.config.speech.whisper_server and self.config.speech.api_key:
            try:
                metadata = [
                    ("authorization", f"Bearer {self.config.speech.api_key}"),
                    ("function-id", self.config.speech.function_id),
                ]
                auth = riva.client.Auth(
                    uri=self.config.speech.whisper_server,
                    use_ssl=True,
                    metadata_args=metadata
                )
                self.asr_cloud = riva.client.ASRService(auth)
            except Exception:
                pass

    def transcribe_bytes(self, audio_data: bytes, config: riva.client.RecognitionConfig):
        """Transcription with dynamic fallback."""
        if self.asr_local:
            try:
                return self.asr_local.offline_recognize(audio_data, config)
            except grpc.RpcError as e:
                if e.code() == grpc.StatusCode.UNAVAILABLE:
                    if not self.asr_cloud:
                        raise e
                else:
                    raise e

        if self.asr_cloud:
            try:
                return self.asr_cloud.offline_recognize(audio_data, config)
            except Exception as e:
                raise e

        raise RuntimeError("No transcription backend available")
