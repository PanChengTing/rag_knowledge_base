from dataclasses import dataclass
import json
from pathlib import Path

from app.core.exceptions import NotFoundError, ValidationError


DATASETS_DIR = Path(__file__).resolve().parent/"datasets"

@dataclass(frozen=True)
class EvaluationCase:
    case_id:str
    question:str
    expected_answer:str
    expected_document_names:list[str]
    expected_keywords:list[str]
    should_refuse:bool
    tags:list[str]

def list_datasets()->list[tuple[str,int]]:
    #返回JSONL的路径名称和总列数
    if not DATASETS_DIR.exists():
        return []
    results:list[tuple[str,int]]=[]
    for path in sorted(DATASETS_DIR.glob("*.jsonl")):
        with path.open("r",encoding="uft-8") as f:
            count = sum (1 for line in f if line.strip())
        results.append((path.stem,count))
    return results

#把JSON转换成对象列表
def load_dataset(name:str)->list[EvaluationCase]:
    path = DATASETS_DIR/f"{name}.jsonl"
    if not path.exists():
        raise NotFoundError(f"评测集不存在：{name}")

    case:list[EvaluationCase]=[]
    with path.open("r",encoding="utf-8") as f:
        for line_no,raw in enumerate(f,start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValidationError(
                    f"评测集{name} 第{line_no}行JSON非法：{exc.msg}"
                ) from exc
            case.append(_parse_case(data,line_no=line_no,dataset=name))
    return case

#把某一行的数据转换成对象
def _parse_case(data:dict,*,line_no:int,dataset:str)->EvaluationCase:
    try:
        return EvaluationCase(
            case_id=str(data["id"]),
            question=str(data["question"]),
            expected_answer=str(data.get("expected_answer")),
            expected_document_names=list(data.get("expected_document_names") or []),
            expected_keywords=list(data.get("expected_keywords") or []),
            should_refuse=bool(data.get("should_refuse",False)),
            tags=list(data.get("tags")or[]),
        )
    except KeyError as exc:
        raise ValidationError(
            f"评测集{dataset} 第{line_no}行缺失字段：{exc.argsz[0]}"
        ) from exc