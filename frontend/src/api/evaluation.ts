import type { EvaluationItemRead, EvaluationItemUpdate, EvaluationRunRead } from "@/client/types.gen"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import{ evaluationDatasetsKey, evaluationItemsKey, evaluationRunKey, evaluationRunsKey }from '@/api/queryKeys'
import{
    listEvaluationDatasets as sdkListEvaluationDatasets,
    listEvaluationRuns as sdkListEvaluationRuns,
    getEvaluationRun as sdkGetEvaluationRun,
    listEvaluationItems as sdkListEvaluationItems,
    createEvaluationRun as sdkCreateEvaluationRun,
    deleteEvaluationRun as sdkDeleteEvaluationRun,
    updateEvaluationItem as sdkUpdateEvaluationItem,
} from '@/client/sdk.gen'

type BadCaseCategory = NonNullable<EvaluationItemRead['bad_case_category']>

export function useEvaluationDatasets(){
    return useQuery(
        {
            //这是唯一的key,如果key相同，则复用查询结果
            queryKey:evaluationDatasetsKey,
            queryFn:async ()=>(await sdkListEvaluationDatasets()).data
        }
    )
}

//轮询一整页的评测run的状态
export function useEvaluationRuns(page=1,pageSize=20){
    return useQuery(
        {
            queryKey:[...evaluationRunsKey,page,pageSize],
            queryFn:async ()=>
                (await sdkListEvaluationRuns({query:{page,page_size:pageSize}})).data,
            //轮询时间。如果还在运行中。5s再查询一下状态
            refetchInterval:(query)=>{
                const items = query.state.data?.items ?? []
                return items.some((r)=>r.status === 'running')?5000:false
            },
        }
    )
}

//轮询查询一个评测RUN的状态
export function useEvaluationRun(runId:string|undefined){
    return useQuery({
        queryKey:runId?evaluationRunKey(runId):["evaluation-run",'none'],
        enabled:Boolean(runId),
        queryFn:async ()=>
        (await sdkGetEvaluationRun({path:{run_id:runId!}})).data,
        refetchInterval:(query)=>{
            const run = query.state.data as EvaluationRunRead|undefined
            return run?.status === 'running'?5000:false
        }
    })
}

export function userEvaluationItems(
    runId:string|undefined,
    filters:{
        page:number
        pageSize:number
        badCaseOnly:boolean
        category:BadCaseCategory|null
    },
){
    return useQuery({
        queryKey:runId?evaluationItemsKey(runId,{
            badCaseOnly:filters.badCaseOnly,
            category:filters.category,
            page:filters.page,
        }):['evaluation-items','none'],
        enabled:Boolean(runId),
        queryFn:async ()=>(
            await sdkListEvaluationItems({
                path:{run_id:runId!},
                query:{
                    page:filters.page,
                    page_size:filters.pageSize,
                    bad_case_only:filters.badCaseOnly,
                    category:filters.category ??undefined,
                },
            })
        ).data
    })
}

export function useCreateEvaluationRun(){
    const queryClient = useQueryClient()
    return useMutation({
        mutationFn:async (body:{name:string,dataset_name:string})=>(
            await sdkCreateEvaluationRun({body})
        ).data,
        onSuccess:()=>{
            queryClient.invalidateQueries({queryKey:evaluationRunsKey})
        }
    })
}

export function useDeleteEvaluationRun(){
    const queryClient = useQueryClient()
    return useMutation({
        mutationFn:async (runId:string) =>
            sdkDeleteEvaluationRun({path:{run_id:runId}}),
        onSuccess:()=>{
            queryClient.invalidateQueries({queryKey:evaluationRunsKey})
        }
    })
}

export function useUpdateEvaluationItem(runId:string){
    const queryClient = useQueryClient()
    return useMutation({
        mutationFn:async (params:{itemId:string;body:EvaluationItemUpdate})=>(
            await sdkUpdateEvaluationItem({
                path:{item_id:params.itemId},
                body:params.body
            })
        ).data,
        onSuccess:()=>{
            queryClient.invalidateQueries({queryKey:['evaluation-items',runId]})
            queryClient.invalidateQueries({queryKey:evaluationRunKey(runId)})
        }
    })
}

export type{BadCaseCategory}