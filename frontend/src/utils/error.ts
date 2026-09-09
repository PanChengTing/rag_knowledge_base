export interface ApiError{
    code:string
    message:string
}

export async function formatApiError(response:Response):Promise<string>{
    try{
        const body = (await response.clone().json()) as Partial<ApiError>
        if (body?.message) return body.message
    } catch{
        //非json响应
    }
    
    return `${response.status} ${response.statusText||'请求失败'}`
}