export const conversationsQueryKey = ['conversaions'] as const
export const evaluationDatasetsKey =['evaluation-datasets'] as const
export const evaluationRunsKey=['evaluation-runs'] as const
export const evaluationRunKey=(runId:string)=>['evaluation-run',runId] as const
export const evaluationItemsKey =(runId:string,filters:{badCaseOnly:boolean;category:string|null;page:number})=>
['evaluation-items',runId,filters] as const
export const currentUserKey = ['auth','me'] as const
export const usersListKey = (page:number,page_size:number)=>['users',{page,page_size}] as const
export const rolesListKey = ['roles'] as const