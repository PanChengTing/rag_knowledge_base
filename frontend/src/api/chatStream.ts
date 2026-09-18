import { fetchEventSource } from '@microsoft/fetch-event-source'
import { type AgentStep, type CitationRead,type QueryRouteRead} from '@/client/types.gen'
import { getAuthToken, useAuthStore } from '@/stores/authStore'

export interface ChatStartEvent{
    type:'start'
    traceId:string|null
    traceUrl:string|null
}

export interface ChatCitationsEvent{
    type:'citations'
    citations:CitationRead[]
}

export interface ChatQueryRouteEvent{
    type:'query_route'
    query_route:QueryRouteRead
}

export interface ChatTokenEvent{
    type:'token'
    delta:string
}

export interface ChatEndEvent{
    type:'end'
    message_id:string
    refused:boolean
}

export interface ChatErrorEvent{
    type:'error'
    code:string
    message:string
}

export interface ChatAgentStepsEvent{
    type:'agent_steps'
    steps:AgentStep[]
}

export interface ChatVerifyResultEvent{
    type:'verify_result'
    verified:boolean
    reason:string|null
    replacementAnswer:string|null
}

export type ChatStreamEvent = 
|ChatStartEvent|ChatCitationsEvent|ChatTokenEvent
|ChatEndEvent|ChatErrorEvent|ChatQueryRouteEvent
|ChatAgentStepsEvent|ChatVerifyResultEvent

interface StreamChatParams{
    conversationId:string
    question:string
    signal?:AbortSignal
    onEvent:(event:ChatStreamEvent)=>void
}

class FatalSseError extends Error {}

//onEvent负责会把流式输出的回答输出
//入参表示接收一个参数但是从里面取出这四个参数
export async function streamChat(
{conversationId,question,signal,onEvent}:
StreamChatParams):Promise<void> {
    const token = getAuthToken()
    const headers:Record<string,string> ={"Content-Type": "application/json"}
    if (token){
        headers.Authorization =`Bearer ${token}`
    }
    await fetchEventSource(
        `/api/conversations/${conversationId}/chat`,{
            method: "POST",
            headers,
            body: JSON.stringify({
            question,
            }),
            signal,
            openWhenHidden:true,
            async onopen(response) {
                if (response.status === 401){
                    useAuthStore.getState().logout()
                    if (window.location.pathname!=='/login'){
                        const back = window.location.pathname + window.location.search
                        window.location.replace(`/login?back=${encodeURIComponent(back)}`)
                    }
                    throw new FatalSseError('请先登录')
                }
                //确实SSE传输流是否正常打开了
                if(response.ok && response.headers.get('content-type')?.includes('text/event-stream')){
                    return
                }
                const text = await response.text().catch(()=>'')
                throw new FatalSseError(text||`HTTP ${response.status}`)
            },
            onmessage(msg) {
                if(!msg.data) return
                const data = msg.data?JSON.parse(msg.data):{}
                //分发到各个EVENT中，根据流式传输中的数据
                switch(msg.event){
                    case 'message_start':
                        onEvent({type:'start',traceId:data.trace_id??null,traceUrl:data.trace_url??null})
                        break
                    case 'citations':
                        onEvent({type:'citations',citations:data.citations??[]})
                        break
                    case 'token':
                        onEvent({type:'token',delta:data.delta??''})
                        break
                    case 'message_end':
                        onEvent({
                            type:'end',
                            message_id:data.message_id,
                            refused:Boolean(data.refused),
                        })
                        break
                    case 'query_route':
                        onEvent({
                            type:'query_route',
                            query_route:data as QueryRouteRead})
                        break
                    case 'agent_steps':
                        onEvent({type:'agent_steps',steps:(data.steps?? []) as AgentStep[]})
                        break
                    case 'verify_result':
                        onEvent({
                            type:'verify_result',
                            verified:Boolean(data.verified),
                            reason:data.reason??null,
                            replacementAnswer:data.replacementAnswer??null,
                        })
                        break
                    case 'error':
                        onEvent({
                            type:'error',
                            code:data.code??'error',
                            message:data.message??'请求失败'
                        })
                        break
                }
            },
            onclose(){

            },
            onerror(err){
                throw err
            }
        }
    )
}