import asyncio

from app.core.log_config import get_logger
from app.core.config import settings
from app.core.exceptions import ConfigurationError

from qcloud_cos import CosClientError, CosConfig,CosS3Client, CosServiceError

logger = get_logger(__name__)

class CosClient:
    def __init__(self)->None:
        if not settings.cos_configured:
            raise ConfigurationError("腾讯云COS未配置")

        config = CosConfig(
            Region= settings.cos_region,
            SecretId=settings.cos_secret_id,
            SecretKey= settings.cos_secret_key,
        )
        self._client = CosS3Client(config)
        self._bucket = settings.cos_bucket
    async def ping(self)->bool:
        try:
            await asyncio.to_thread(self._client.head_bucket,Bucket=self._bucket)
            return True
        except (CosClientError,CosServiceError) as exc:
            logger.warning("COS ping failed:%s",exc.get_status_code())
            return False
    @property
    def bucket(self)->str:
        return self._bucket

    @property
    def region(self)->str:
        return settings.cos_region
    
    #增加文档，key是唯一标识，body文件内容，content_type文件类型
    #to_thread 把同步操作放到线程里
    async def put_object(self,*,key:str,body:bytes,content_type:str) ->None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
        )
    #获取文档
    async def get_object(self,key:str)->bytes:
        def _read()->bytes:
            response = self._client.get_object(Bucket=self.bucket,Key=key)
            return response["Body"].get_raw_stream().read()

        return await asyncio.to_thread(_read)

    #删除文档
    async def delete_object(self,key:str)->None:
        await asyncio.to_thread(
            self._client.delete_object,
            Bucket=self._bucket,
            Key=key
        )

_cos_client:CosClient|None = None
def get_cos_client()->CosClient:
    global _cos_client
    if _cos_client is None:
        _cos_client = CosClient()
    return _cos_client