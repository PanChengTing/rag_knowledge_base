export const conversationsQueryKey = ['conversaions'] as const
export const evaluationDatasetsKey =['evaluation-datasets'] as const
export const evaluationRunsKey=['evaluation-runs'] as const
export const evaluationRunKey=(runId:string)=>['evaluation-run',runId] as const
export const evaluationItemsKey =(runId:string,filters:{badCaseOnly:boolean;category:string|null;page:number})=>
['evaluation-items',runId,filters] as const