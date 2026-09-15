import { streamChat, type ChatStreamEvent } from "@/api/chatStream"
import { conversationsQueryKey } from "@/api/queryKeys"
import { createConversation, getConversation, type CitationRead, type MessageRead } from "@/client"
import type { AgentStep, QueryRouteRead, VerifyResultRead } from "@/client/types.gen"
import { AgentStepsPanel } from "@/components/AgentStepsPanel"
import { CitationList, type CitationListHandle } from "@/components/CitationList"
import { ConversationSidebar } from "@/components/ConversationsSidebar"
import { gfmComponents } from "@/components/markdownComponents"
import { QueryRoutePanel } from "@/components/QueryRoutePanel"
import { TraceIdPanel } from "@/components/TraceIdPanel"
import { formatApiError } from "@/utils/error"
import { PlusOutlined, RobotOutlined, SendOutlined, UserOutlined } from "@ant-design/icons"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Alert, Avatar, Button, Empty, Input, Layout, Space, Spin, Tag, Typography } from "antd"
import { Content } from "antd/es/layout/layout"
import Sider from "antd/es/layout/Sider"
import React, { useEffect, useMemo, useRef, useState } from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from 'remark-gfm'

const {Title,Paragraph,Text} = Typography
const {TextArea} = Input
const STORAGE_KEY='rag.chat.conversation_id'
type AssistantStatus='streaming'|'done'|'error'
const REFUSAL_ANSWER ='抱歉，知识库中没有找到与该问题相关的可靠依据'
interface UiMessage{
    id:string
    role:'user'|'assistant'
    content:string
    citations:CitationRead[]
    queryRoute?:QueryRouteRead|null
    agentSteps?:AgentStep[]|null
    status?:AssistantStatus
    error?:string|null
    verifyResult?:VerifyResultRead|null
    refused?:boolean
    traceId?:string|null
    traceUrl?:string|null
}

function fromServerMessage(m:MessageRead):UiMessage{
    console.log('后端历史消息:', m.id, m)
    return {
        id:m.id,
        role:m.role === 'assistant'?'assistant':'user',
        content:m.content,
        citations:m.citations??[],
        queryRoute:m.query_route??null,
        agentSteps:m.agent_steps??null,
        status:'done',
        verifyResult:m.verify_result ??null,
        traceId:m.trace_id ?? null,
        traceUrl:m.trace_url ?? null,
        // 文案为拒答文案则判断为拒绝
        refused:m.role === 'assistant'&&m.content === REFUSAL_ANSWER
    }
}

export function ChatPage(){
    const queryClient = useQueryClient()
    const [conversationId,setConversationId] = useState<string|null>(
        ()=>localStorage.getItem(STORAGE_KEY)
    )
    const [draft,setDraft] = useState('')
    //历史消息队列
    const [pendingMessages,setPendingMessages] = useState<UiMessage[]>([])
    const [isStreaming,setIsStreaming] = useState(false)
    //终止输出
    const abortRef = useRef<AbortController|null>(null)
    //滑动
    const scrollRef = useRef<HTMLDivElement>(null)

    //创建会话，第一次进入页面才会调用
    const createMutation = useMutation({
        mutationFn:async ()=>{
            const res = await createConversation({body:{title:'新对话'}})
            return res.data!
        },
        onSuccess:async(conversation)=>{
            localStorage.setItem(STORAGE_KEY,conversation.id)
            setConversationId(conversation.id)
            setPendingMessages([])
            queryClient.removeQueries({queryKey:['conversation']})
            await queryClient.invalidateQueries({queryKey:conversationsQueryKey})
        },
    })

    //观察conversation对象，如果没有了，自动创建一个
    //第二次进入页面应该会从storage里面读取一个
    useEffect(()=>{
        if(!conversationId && !createMutation.isPending){
            createMutation.mutate()
        }
    },[conversationId])

    //拉取历史消息
    const historyQuery = useQuery({
        queryKey:['conversation',conversationId],
        queryFn:async ()=>{
            const res = await getConversation({path:{conversation_id:conversationId!}})
            return res.data!
        },
        enabled:Boolean(conversationId)
    })

    // 历史消息有变化的话，清空pending
    useEffect(
        ()=>{
            if (historyQuery.data){
                setPendingMessages([])
            }
        },[historyQuery.data]
    )
    const allMessages = useMemo<UiMessage[]>(()=>{
        const history = (historyQuery.data?.message??[]).map(fromServerMessage)
        return [...history,...pendingMessages]
    },[historyQuery.data,pendingMessages])

    //自动滚动到底部
    useEffect(()=>{
        scrollRef.current?.scrollTo({top:scrollRef.current.scrollHeight,behavior:'smooth'})
    },[allMessages])

    //组件卸载或新建对话时取消进行中的请求
    useEffect(()=>{
        return ()=>{
            abortRef.current?.abort()
        }
    },[])

    const handleNewConversation = ()=>{
        abortRef.current?.abort()
        createMutation.mutate()
    }

    const handleSelectConversation = (id:string)=>{
        if (id === conversationId) return
        abortRef.current?.abort()
        setPendingMessages([])
        setIsStreaming(false)
        localStorage.setItem(STORAGE_KEY,id)
        setConversationId(id)
    }

    const handleConversationDeleted = (deletedId:string) =>{
        if (deletedId!==conversationId) return
        abortRef.current?.abort()
        setPendingMessages([])
        setIsStreaming(false)
        localStorage.removeItem(STORAGE_KEY)
        setConversationId(null)
        queryClient.removeQueries({queryKey:['conversation',deletedId]})
    }

    //更新消息，只是一种处理消息的规则
    const updateAssistant = (updater:(prev:UiMessage)=>UiMessage)=>{
        setPendingMessages((prev)=>{
            const last = prev[prev.length - 1]

                console.log('更新前最后一条:', last)
                console.log('更新前 agentSteps:', last?.agentSteps)

                if (!last || last.role !== 'assistant') {
                console.warn('最后一条不是 assistant，无法更新')
                return prev
                }

                const next = prev.slice()
                next[next.length - 1] = updater(last)

                console.log(
                '更新后 agentSteps:',
                next[next.length - 1]?.agentSteps,
                )

                return next
        })
    }

    //在这里把问题发送给了服务器，打开了整个流式输出
    const handleSend = async ()=>{
        //删除字符串的前后空白字符
        const question = draft.trim()
        if (!question || !conversationId||isStreaming) return
        setDraft('')
        const userMsg:UiMessage ={
            id:`local-user-${Date.now}`,
            role:'user',
            content:question,
            citations:[],
            status:'done'
        }
        const assistantMsg:UiMessage ={
            id:`local-assistant-${Date.now}`,
            role:'assistant',
            content:'',
            citations:[],
            status:'streaming'
        }
        setPendingMessages((prev)=>[...prev,userMsg,assistantMsg])
        setIsStreaming(true)

        const ctrl = new AbortController()
        abortRef.current = ctrl
        try{
            await streamChat({
                conversationId,
                question,
                signal:ctrl.signal,
                //根据流式输出逐步填充整个对象UIMessage
                onEvent:(event:ChatStreamEvent)=>{
                    switch(event.type){
                        case 'start':
                            updateAssistant((prev)=>({...prev,traceId:event.traceId,traceUrl:event.traceUrl}))
                            break
                        case 'citations':
                            updateAssistant((prev)=>({...prev,citations:event.citations}))
                            break
                        case 'query_route':
                            updateAssistant((prev)=>({...prev,queryRoute:event.query_route}))
                            break
                        case 'token':
                            updateAssistant((prev)=>({...prev,content:prev.content+event.delta}))
                            break
                        case 'end':
                            updateAssistant((prev)=>({...prev,
                                status:'done',
                            refused:prev.refused||event.refused}))
                            break
                        case 'agent_steps':
                            console.log(event.steps)
                            updateAssistant((prev)=>({...prev,agentSteps:event.steps}))
                            break
                        case 'verify_result':
                            updateAssistant((prev)=>{
                                const verifyResult:VerifyResultRead={
                                    verified:event.verified,
                                    reason:event.reason,
                                }
                                if (!event.verified&& event.replacementAnswer){
                                    return  {
                                        ...prev,
                                        content:event.replacementAnswer,
                                        citations:[],
                                        refused:true,
                                        verifyResult,
                                    }
                                }
                                return {...prev,verifyResult}
                            })
                            break
                        case 'error':
                            updateAssistant((prev)=>({...prev,status:'error',error:event.message}))
                            break
                    }
                }
            })
            await Promise.all([
                queryClient.invalidateQueries({queryKey:['conversation',conversationId]}),
                queryClient.invalidateQueries({queryKey:conversationsQueryKey})
            ])
            
        }catch(err){
            const fallback = err instanceof Response ? await formatApiError(err):(err as Error).message
            updateAssistant((prev)=>({...prev,status:'error',error:fallback||'问答请求失败'})) 
        }finally{
            setIsStreaming(false)
            abortRef.current=null
        }
    }

    const handleKeyDown = (e:React.KeyboardEvent<HTMLTextAreaElement>)=>{
        if (e.key === 'Enter' && !e.shiftKey &&!e.nativeEvent.isComposing){
            e.preventDefault()
            handleSend()
        }
    }

    return (
  <Layout
    style={{
      height: 'calc(100vh - 112px)',
      background: '#fff',
      borderRadius: 8,
      overflow: 'hidden',
      border: '1px solid #f0f0f0',
    }}
  >
    <Sider
      width={260}
      theme="light"
      style={{
        borderRight: '1px solid #f0f0f0',
        background: '#fafafa',
      }}
    >
      <ConversationSidebar
        currentId={conversationId}
        onSelect={handleSelectConversation}
        onDeleted={handleConversationDeleted}
        onCreateNew={handleNewConversation}
        isCreating={createMutation.isPending}
      />
    </Sider>

    <Content
      style={{
        flex: 1,
        minWidth: 0,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div
        ref={scrollRef}
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: 24,
        }}
      >
        {historyQuery.isLoading ? (
          <Spin />
        ) : allMessages.length === 0 ? (
          <Empty description="还没有问题，在下方输入开始提问" />
        ) : (
          allMessages.map((msg) => (
            <MessageBubble
              key={msg.id}
              message={msg}
            />
          ))
        )}
      </div>
      
      <div
        style={{
          padding: 12,
          borderTop: '1px solid #f0f0f0',
          display: 'flex',
          gap: 8,
          background: '#fafafa',
        }}
      >
        <TextArea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="输入你的问题，按 Enter 发送，Shift+Enter 换行"
            autoSize={{ minRows: 2, maxRows: 6 }}
            disabled={!conversationId || isStreaming}
        />

        <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            loading={isStreaming}
            disabled={!conversationId || !draft.trim()}
        >
            发送
        </Button>
        </div>
        </Content>
    </Layout>
    )
}

interface MessageBubbleProps {
  message: UiMessage
}
const CITATION_HASH_PREFIX = '#cite-'

/**
 * 把答案里的引用编号 `[N]` 改写成 markdown hash 链接，交给下方 CitationList 处理点击。
 *
 * 严格只匹配纯 `[N]`（不含反引号、不含尖括号），格式由后端 prompt 强约束。
 * 链接文本用 `[[N]](url)` 这种“成对方括号嵌套”形式，CommonMark 解析最稳定。
 */
function linkifyCitations(
  content: string,
  maxIndex: number,
  messageId: string,
): string {
  if (maxIndex <= 0) return content

  return content.replace(/\[(\d+)\]/g, (raw, num: string) => {
    const n = Number(num)
    if (n < 1 || n > maxIndex) return raw

    return `[[${n}]](${CITATION_HASH_PREFIX}${messageId}-${n})`
  })
}

function createMarkdownComponents(onCitationClick:(n:number)=>void){
        return{
            a:(props:React.ComponentProps<'a'>)=>{
                const href = props.href??''
                if (href.startsWith(CITATION_HASH_PREFIX)){
                    const n=Number(href.split('-').pop())
                    return (
                        <a
                        {...props}
                        href={href}
                        onClick={(e)=>{
                            e.preventDefault()
                            if (Number.isFinite(n)) onCitationClick(n)
                        }
                        }
                        />
                    )
                }
                return <a {...props} target="_blank" rel="noreferrer"/>
            },...gfmComponents,
        }
}

/**
 * assistant 气泡顶部状态：拒答提示 + 校验结果 Tag/Alert。
 *
 * 优先级：拒答提示在最上（用户最关心“答案是否可信”），校验结果其次。
 * 拒答场景下不再单独显示 verify Alert，避免重复警告。
 */
function AssistantHeader({
  message,
}: {
  message: UiMessage
}) {
  if (message.refused) {
    return (
      <Alert
        type="warning"
        showIcon
        message="未在知识库中找到可靠依据"
        description={
          message.verifyResult &&
          message.verifyResult.verified === false
            ? `答案校验未通过：${
                message.verifyResult.reason ?? '缺乏引用支撑'
              }，已替换为拒答`
            : undefined
        }
        style={{ marginBottom: 8 }}
      />
    )
  }

  if (message.verifyResult?.verified === true) {
    return (
      <div style={{ marginBottom: 8 }}>
        <Tag color="green">已校验</Tag>
      </div>
    )
  }

  return null
}

function MessageBubble({ message }: MessageBubbleProps) {
    const isUser = message.role === 'user'
    const citationRef = useRef<CitationListHandle>(null)

    const components = useMemo(
        () =>
        createMarkdownComponents((n) =>
            citationRef.current?.expandAndScroll(n),
        ),
        [],
    )

    const renderedContent = useMemo(
        () =>
        linkifyCitations(
            message.content,
            message.citations.length,
            message.id,
        ),
        [message.content, message.citations.length, message.id],
    )

    return (
        <div
        style={{
            display: 'flex',
            gap: 12,
            marginBottom: 24,
            flexDirection: isUser ? 'row-reverse' : 'row',
        }}
        >
        <Avatar
            icon={isUser ? <UserOutlined /> : <RobotOutlined />}
            style={{
            background: isUser ? '#1677ff' : '#52c41a',
            flexShrink: 0,
            }}
        />

        <div
            style={{
            maxWidth: '78%',
            background: isUser ? '#e6f4ff' : '#f6f6f6',
            padding: '12px 16px',
            borderRadius: 8,
            }}
        >
            {message.error ? (
            <Alert
                type="error"
                message={message.error}
                style={{ marginBottom: 8 }}
            />
            ) : null}

            {message.content ? (
            isUser ? (
                <Text style={{ whiteSpace: 'pre-wrap' }}>
                {message.content}
                </Text>
            ) : (
                <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={components}
                >
                {renderedContent}
                </ReactMarkdown>
            )
            ) : message.status === 'streaming' ? (
            <Text type="secondary">
                <Spin size="small" /> 正在思考...
            </Text>
            ) : null}
            {!isUser&&message.queryRoute?(
                <QueryRoutePanel queryRoute={message.queryRoute}/>
            ):null}
            {!isUser&&message.agentSteps&&message.agentSteps.length>0?(
                    <AgentStepsPanel steps={message.agentSteps}></AgentStepsPanel>
            ):null}
            {!isUser?<AssistantHeader message={message}/>:null}
            {!isUser&&message.traceId?(
                <TraceIdPanel traceId={message.traceId} traceUrl={message.traceUrl}></TraceIdPanel>
            ):null}
            {!isUser && message.citations.length > 0 ? (
            <CitationList
                ref={citationRef}
                citations={message.citations}
                messageId={message.id}
            />
            ) : null}
        </div>
        </div>
    )
}

