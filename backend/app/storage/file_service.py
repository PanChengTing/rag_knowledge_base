
from app.core.log_config import get_logger
from app.storage.cos_client import CosClient, get_cos_client

from qcloud_cos import CosClientError,CosServiceError

logger = get_logger(__name__)

class FileService:
    def __init__(self,cos:CosClient|None = None) ->None:
        self._cos = cos or get_cos_client()

    @property
    def bucket(self)->str:
        return self._cos.bucket

    @property
    def region(self)->str:
        return self._cos.region

    @staticmethod
    def build_object_key(file_hash:str,suffix:str)->str:
        #file_hash作为天然幂等，同个文件多次上传命中一个object
        #suffix保留文件扩展名，方便预览
        #静态方法是因为它不依赖任何实例，不使用self
        return f"documents/{file_hash}{suffix}"

    async def upload(self,*,content:bytes,file_hash:str,suffix:str,mine_type:str):
        key = self.build_object_key(file_hash,suffix)
        await self._cos.put_object(key=key,body=content,content_type=mine_type)
        return key

    async def download(self,object_key:str) -> bytes:
        return await self._cos.get_object(object_key)

    async def delete(self,object_key:str) -> None:
        try:
            await self._cos.delete_object(object_key)
        except (CosClientError,CosServiceError) as exc:
            logger.warning("cos delete failed: key =%s err=%s",object_key,exc)

def get_file_service() ->FileService:
    return FileService()