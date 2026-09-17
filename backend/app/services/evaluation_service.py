
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.log_config import get_logger
from app.db.repositories.evaluation_repo import EvaluationItemRepository, EvaluationRunRepository
from app.db.models import EvaluationItem, EvaluationRun, EvaluationRunStatus
from app.evaluation.dataset import EvaluationCase, list_datasets, load_dataset
from app.core.exceptions import NotFoundError, ValidationError
from app.db.session import AsyncSessionLocal
from app.services.chat_service import ChatService, EvaluationAnswer
from app.evaluation.scoring import classify_bad_case, compute_citation_hit, compute_refusal_correct
from app.retrieval.vector_retriever import RetrievedChunk
from app.evaluation.ragas_runner import RagasMetrics, RagasSample, evaluate_batch
from app.llm.models import get_chat_model


logger = get_logger(__name__)

class EvaluationService:
    def __init__(self,session:AsyncSession):
        self.session = session
        self.run_repo = EvaluationRunRepository(session)
        self.item_repo = EvaluationItemRepository(session)

    #创建一个评测集的任务，将信息落库
    async def create_run(self,*,name:str,dataset_name:str)->EvaluationRun:
        cases = load_dataset(dataset_name)
        if not cases:
            raise ValidationError(f"评测集{dataset_name}为空")

        run = EvaluationRun(
            name = name,
            dataset_name =dataset_name,
            dataset_size = len(cases),
            status = EvaluationRunStatus.RUNNING,
            progress_total = len(cases),
        )

        await self.run_repo.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def get_run(self,run_id:UUID)->EvaluationRun:
        run = await self.run_repo.get(run_id)
        if run is None:
            raise NotFoundError("评测run不存在")
        return run

    async def list_runs(self,page:int,page_size:int):
        return await self.run_repo.list_page(page=page,page_size=page_size)

    async def delete_run(self,run_id:UUID)->None:
        deleted = await self.run_repo.delete(run_id)
        if not deleted:
            raise NotFoundError("评测run不存在")
        await self.session.commit()

    async def list_items(self,run_id:UUID,page:int,page_size:int,*,bad_case_only:bool,category:str|None):
        await self.get_run(run_id)
        return await self.item_repo.list_page(run_id=run_id,page=page,page_size=page_size,
                                              bad_case_only=bad_case_only,
                                              category=category)

    async def get_item(self,item_id:UUID) ->EvaluationItem:
        item = await self.item_repo.get(item_id)
        if item is None:
            raise NotFoundError("评测case不存在")
        return item

    def list_datasets(self)->list[tuple[str,int]]:
        return list_datasets()

    #用于给前端可以更正case中的某个条目的正确/错误
    async def update_item_bad_case(
            self,
            item_id:UUID,*,bad_case_category:str|None,
            bad_case_note:str|None,is_bad_case:bool|None,
    )->EvaluationItem:
        item = await self.get_item(item_id)

        if is_bad_case is False:
            item.is_bad_case =False
            item.bad_case_category =None
        else:
            if bad_case_category is not None:
                item.bad_case_category =bad_case_category
                item.is_bad_case=True
            elif is_bad_case is True:
                item.is_bad_case=True

        if bad_case_note is not None:
            item.bad_case_note =bad_case_note
        await self.session.commit()
        await self.session.refresh(item)
        return item

#核心函数，用于执行整个评测集流程
async def execute_evaluation_run(run_id:UUID)->None:
    '''
    流程：
    1、加载整个评测集case
    2、逐条调answer_for_evaluation,每条结束都更新数据库（让前端可以查询）
    3、全部跑完一起算指标
    4、算Bad Case归因
    任意阶段失败，不改变已经写入的items
    '''
    logger.info("evaluation run start:run_id =%s",run_id)
    try:
        async with AsyncSessionLocal() as session:
            run_repo =EvaluationRunRepository(session)
            run = await run_repo.get(run_id)
            if run is None:
                logger.warning("evaluation run nto found skip %s",run_id)
                return
            run.started_at = datetime.now(timezone.utc)
            await session.commit()
            dataset_name = run.dataset_name

        cases = load_dataset(dataset_name)

        for case in cases:
            await _run_single_case(run_id,case)

        await _finalize_run(run_id)

        #更新整个评测集的基本信息
        async with AsyncSessionLocal() as session:
            run = await EvaluationRunRepository(session).get(run_id)
            if run is not None:
                run.status = EvaluationRunStatus.COMPLETED
                run.finish_at =datetime.now(timezone.utc)
                await session.commit()
        logger.info("evaluation run done:run_id=%s",run_id)

    except Exception as exc:
        logger.exception("evaluation run failed:run_id=%s",run_id)
        #记录评测失败的时间和错误信息
        async with AsyncSessionLocal() as session:
            run = await EvaluationRunRepository(session).get(run_id)
            if run is not None:
                run.status =EvaluationRunStatus.FAILED
                run.finish_at=datetime.now(timezone.utc)
                run.error_message = (str(exc).strip() or exc.__class__.__name__)[:500]
                await session.commit()

async def _run_single_case(run_id:UUID,case:EvaluationCase)->None:
    async with AsyncSessionLocal() as session:
        chat_service = ChatService(session)
        answer:EvaluationAnswer = await chat_service.answer_for_evaluation(case.question)

        citation_hit =(
            None
            if case.should_refuse
            else compute_citation_hit(
                actual_citaions=answer.citations,
                expected_document_names=case.expected_document_names,
                expected_keywords=case.expected_keywords,
            )
        )

        refusal_correct = compute_refusal_correct(answer.refused,case.should_refuse)
        item = EvaluationItem(
            run_id =run_id,
            case_id =case.case_id,
            question =case.question,
            expected_answer = case.expected_answer,
            expected_document_names = case.expected_document_names,
            expected_keywords = case.expected_keywords,
            should_refuse = case.should_refuse,
            tags=case.tags,
            actual_answer = answer.answer,
            actual_refused = answer.refused,
            citations = answer.citations,
            retrieved_chunks_meta = [_chunk_meta(c) for c in answer.chunks],
            query_route = answer.query_route or None,
            agent_steps = answer.agent_steps or None,
            verify_result = _verify_payload(answer.verify_result),
            trace_id = answer.trace_id,
            latency_ms = answer.latency_ms,
            first_token_latency_ms =answer.first_token_latency_ms,
            error_message =answer.error_message,
            citation_hit = citation_hit,
            refusal_correct = refusal_correct
        )
        await EvaluationRunRepository(session).add(item)
        run = await EvaluationRunRepository(session).get(run_id)
        if run is not None:
            run.progress_completed += 1
            if answer.error_message:
                run.progress_failed +=1
        await session.commit()

async def _finalize_run(run_id:UUID)->None:
    async with AsyncSessionLocal() as session:
        item_repo = EvaluationItemRepository(session)
        items = await item_repo.list_by_run(run_id)
        if not items:
            return
        samples_with_index:list[tuple[int,RagasSample]] =[]
        for idx,item in enumerate(items):
            if item.should_refuse or item.error_message or not item.retrieved_chunks_meta:
                continue
            samples_with_index.append(
                (
                    idx,
                    RagasSample(
                        question=item.question,
                        answer=item.actual_answer,
                        retrieved_contexts=[
                            str(c.get("content","")) for c in item.retrieved_chunks_meta
                        ],
                        reference_answer=item.expected_answer,
                    )
                )
            )
        #因为可能有的样本被过滤掉了，所以需要再对应一下
        metrics_list:list[RagasMetrics|None] =[None]*len(items)
        if samples_with_index:
            indexed_metrics = await evaluate_batch([s for _,s in samples_with_index])
            for (idx,_),m in zip(samples_with_index,indexed_metrics,strict=True):
                metrics_list[idx]=m
                logger.warning(samples_with_index[idx])

        for item,metrics in zip(items,metrics_list,strict=True):
            if metrics is not None:
                item.faithfulness = metrics.faithfulness
                item.answer_relevancy = metrics.answer_relevancy
                item.context_precision = metrics.context_precision
                item.context_recall = metrics.context_recall

            rule = classify_bad_case(
                should_refuse=item.should_refuse,
                actual_refused=item.actual_refused,
                refusal_correct=item.refusal_correct,
                citation_hit=item.citation_hit,
                faithfulness=item.faithfulness,
                answer_relevancy=item.answer_relevancy,
                context_precision=item.context_precision,
                context_recall=item.context_recall,
                has_error=bool(item.error_message)
            )
            item.is_bad_case = rule.is_bad_case
            item.bad_case_category = rule.category

        run = await EvaluationRunRepository(session).get(run_id)
        if run is not None:
            run.faithfulness =_avg([i.faithfulness for i in items])
            run.answer_relevancy =_avg([i.answer_relevancy for i in items])
            run.context_precision =_avg([i.context_precision for i in items])
            run.context_recall =_avg([i.context_recall for i in items])
            non_refusal_hits = [i.citation_hit for i in items if i.citation_hit is not None]
            run.citation_hit_rate =(
                sum(1 for h in non_refusal_hits if h)/len(non_refusal_hits)
                if non_refusal_hits else None
            )
            run.refusal_accuracy =sum(1 for i in items if i.refusal_correct)/len(items)
            run.avg_latency_ms = sum(i.latency_ms for i in items)/len(items)
            first_token_values = [
                i.first_token_latency_ms for i in items if i.first_token_latency_ms is not None
            ]
            run.avg_first_token_latency_ms = (sum(first_token_values)/len(first_token_values) if first_token_values else None)

        await session.commit()
    
#将RetrievedChunk序列化为dict
def _chunk_meta(chunk:RetrievedChunk)->dict:
    return {
        "chunk_id":str(chunk.chunk_id),
        "document_id":str(chunk.document_id),
        "document_name":chunk.document_name,
        "page_no":chunk.page_no,
        "section_path":chunk.section_path,
        "content":chunk.content,
        "rerank_score":chunk.rerank_score,
        "vector_score":chunk.vector_score,
        "rrf_score":chunk.rrf_score,
    }

def _verify_payload(result)->dict|None:
    if result is None:
        return None
    return {"verified":result.verified,"reason":result.reason or None}

def _avg(values:list[float|None])->float|None:
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return sum(nums)/len(nums)