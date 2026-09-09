import { deleteDocument, getDocument, getDocumentsChunk, listDocumentsChunks, retryDocument } from "@/client"
import type { DocumentChunkDetail, DocumentChunkRead, DocumentRead } from "@/client/types.gen"
import { buildDocumentFileUrl, canPreviewInline, isHtmlMime, isMarkdownMime, isPdfMime } from "@/utils/documentFile"
import { getStatusColor, getStatusLabel, isTerminalStatus } from "@/utils/documentStatus"
import { ArrowLeftOutlined, DeleteOutlined, DownloadOutlined, EyeOutlined, RedoOutlined } from "@ant-design/icons"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Alert, Button, Card, Descriptions, Empty, List, message, Modal, Pagination, Popconfirm, Skeleton, Space, Statistic, Tag, Typography } from "antd"
import { useEffect, useMemo, useState } from "react"
import ReactMarkdown from "react-markdown"
import { Link, useNavigate, useParams } from "react-router-dom"

 const {Title,Text,Paragraph} = Typography
 const CHUNK_PAGE_SIZE=20
const DELETABLE_STATUSES:ReadonlySet<DocumentRead['status']> 
= new Set(['failed','ready','uploading'])
function formatSize(size:number):string {
    if (size<1024) return `${size}B`
    if (size<1024*1024) return `${(size/1024).toFixed(1)} KB`
    return `${(size/1024/1024).toFixed(2)} MB`
}


function PreviewArea({mime_type,previewUrl}:{mime_type:string;previewUrl:string}){
    if (isPdfMime(mime_type)||isHtmlMime(mime_type)){
        //返回iframe页面
        return (
            <iframe
                title="document-preview"
                src={previewUrl}
                style={{width:'100%',height:600,border:'1px solid #f0f0f0'}}></iframe>
        )
    }
    //markdown用的自定义的组件
    if (isMarkdownMime(mime_type)){
        return <MarkdownPreview url={previewUrl}></MarkdownPreview>
    }
    //不支持预览提示
    return (<Alert
            type="info"
            showIcon
            message="该格式不支持内联预览"
            description="DOCX等富文本格式请下载后用本地编辑器查看。"></Alert>
    )
}

function MarkdownPreview({url}:{url:string}){
    const [content,setContent] = useState<string|null>(null)
    const [error,setError] = useState<string|null>(null)
    //组件第一次显示或url发生变化的时候会执行
    useEffect(()=>{
        let cancelled =false
        setContent(null)
        setError(null)
        //向预览地址发送get请求
        fetch(url).then(
            //r是服务器响应
            async (r)=>{
                if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
                return r.text()
            }).then((text)=>{
                if (!cancelled) setContent(text)
            }).catch((e:Error)=>{
                if (!cancelled) setError(e.message)
            })
        // EFFECT失效时执行，可以视为一个清理函数
        return ()=>{
            cancelled = true
        }
    },[url])
    if(error) return <Alert type="error" message="加载Markdown失败" description={error}></Alert>
    if (content === null) return <Skeleton active/>
    return (
        <div style={{ padding:16,maxHeight:600,overflow:'auto'}}>
            <ReactMarkdown>{content}</ReactMarkdown>
        </div>
    )
}   

interface ChunksQueryResult{
    isLoading:boolean
    data:|{
        items:DocumentChunkRead[]
        total:number
        stats?:|{
            total:number
            avg_length:number
            min_length:number
            max_length:number
        }|null
    }|undefined
}

function ChunksSection({docStatus,chunksQuery,page,onPageChange,onPickChunk,}:{
    docStatus:DocumentRead['status']
    chunksQuery:ChunksQueryResult
    page:number,
    onPageChange:(p:number)=>void
    onPickChunk:(id:string)=>void
}) {
    if (docStatus !=='ready'){
        return <Empty description="等待入库完成后展示切分结果"></Empty>
    }
    if (chunksQuery.isLoading || !chunksQuery.data){
        return <Skeleton active/>
    }
    const {items,total,stats} = chunksQuery.data
    if (total === 0){
        return <Empty description="没有chunk"></Empty> 
    }
    return (
        <>
        {stats?(
            <Space size="large" style={{ marginBottom:16}} wrap>
                <Statistic title="切片总数" value={stats.total}></Statistic>
                <Statistic title="平均字符数" value={stats.avg_length}></Statistic>
                <Statistic title="最短" value={stats.min_length}></Statistic>
                <Statistic title="最长" value={stats.max_length}></Statistic>
            </Space>
        ):null}
        <List<DocumentChunkRead>
            dataSource={items}
            bordered
            renderItem={(chunk)=>(
                <List.Item style={{cursor:'pointer'}}
                            onClick={()=>onPickChunk(chunk.id)}>
                <List.Item.Meta
                    title={
                        <Space wrap>
                            <Text strong>#{chunk.chunk_index}</Text>
                            {chunk.page_no !=null ? <Tag color="blue">第{chunk.page_no}</Tag>:null}
                            {chunk.section_path?(
                                <Text type="secondary" ellipsis style={{maxWidth:320}}>
                                    {chunk.section_path}
                                </Text>
                            ):null}
                            <Tag>字符数{chunk.char_count}</Tag>
                            <Text type="secondary" code>{chunk.chunk_hash.slice(0,8)}</Text>
                        </Space>
                    }>
                    description={
                        <Paragraph type="secondary" style={{marginBottom:0,whiteSpace:'pre-wrap'}}>
                            {chunk.content_excerpt}
                        </Paragraph>
                    }
                    </List.Item.Meta>
                </List.Item>
            )}></List>
            <Pagination
                style={{marginTop:16,textAlign:'right'}}
                align="end"
                current={page}
                pageSize={CHUNK_PAGE_SIZE}
                total={total}
                showSizeChanger={false}
                onChange={onPageChange}
                />
        </>
    )
}

function ChunkDetailBody({chunk}:{chunk:DocumentChunkDetail}){
    return (
        <>
        <Space wrap style={{ marginBottom:12}}>
            <Text strong>#{chunk.chunk_index}</Text>
            {chunk.page_no!=null?<Tag color="blue">第{chunk.page_no}页</Tag>:null}
            <Tag>字符数{chunk.char_count}</Tag>\
            <Text type="secondary" code>{chunk.chunk_hash}</Text>
        </Space>
        {chunk.section_path?<Paragraph type="secondary">{chunk.section_path}</Paragraph>:null}
        <pre style={{
            background:'#fafafa',
            border:'1px solid $f0f0f0',
            padding:12,
            maxHeight:480,
            overflow:'auto',
            whiteSpace:'pre-wrap',
            wordBreak:'break-word',
        }}>
            {chunk.content}
        </pre>
        </>
    )
}

export function DocumentsDetailPage(){
   const {id=' '} = useParams<{id:string}>()
   const navigate = useNavigate()
   const queryClient = useQueryClient()

   const [chunkPage,setChunkPage] = useState(1)
   const [activChunkID,setActivChunkID] = useState<string|null>(null)

    const docQuery = useQuery({
        //这个查询的参数，documents是唯一标识，page页数 pageSize页面大小 statusFilter 状态
        queryKey:['documents','detail',id],
        queryFn:async()=>{
            // 生成后端查询的url
            const res = await getDocument({path:{document_id:id}})
            return res.data!
        },
        enabled:!!id,
        refetchInterval:(q)=>{
            const data = q.state.data
            // false表示停止轮询，如果query没有数据就停止了
            if (!data) return false
            return isTerminalStatus(data.status)?false:3000
        }
    })

    const doc = docQuery.data
    const chunksQuery = useQuery({
        //这个查询的参数，documents是唯一标识，page页数 pageSize页面大小 statusFilter 状态
        queryKey:['documents','detail',id,'chunks',chunkPage],
        queryFn:async()=>{
            // 生成后端查询的url
            const res = await listDocumentsChunks({path:{document_id:id},
            query:{page:chunkPage,page_size:CHUNK_PAGE_SIZE}})
            return res.data!
        },
        enabled:!!id && doc?.status === 'ready'
    })

    const chunkDetailQuery = useQuery({
        //这个查询的参数，documents是唯一标识，page页数 pageSize页面大小 statusFilter 状态
        queryKey:['documents','detail',id,'chunks',activChunkID],
        queryFn:async()=>{
            // 生成后端查询的url
            const res = await getDocumentsChunk({path:{document_id:id,chunk_id:activChunkID!}})
            return res.data!
        },
        enabled:!!activChunkID,
    })

    const retryMutation = useMutation({
        mutationFn:async() =>{
            const res = await retryDocument({path:{document_id:id}})
            return res.data!
        },
        onSuccess:()=>{
            message.success(`已重新提交解析`)
            queryClient.invalidateQueries({queryKey:['documents']})
        },
    })

    const deleteMutation = useMutation({
        mutationFn:async() =>{
            await deleteDocument({path:{document_id:id}})
        },
        onSuccess:()=>{
            message.success(`文档已删除`)
            queryClient.invalidateQueries({queryKey:['documents']})
            navigate('/documents')//成功后切换页面
        },
    })

    const previewUrl = useMemo(()=>buildDocumentFileUrl(id,{download:false}),[id])
    const downloadUrl = useMemo(()=>buildDocumentFileUrl(id,{download:true}),[id])

    if (docQuery.isLoading) return <Skeleton active/>
    if (!doc) return null

    const canDelete = DELETABLE_STATUSES.has(doc.status)
    const canRetry = doc.status === 'failed'
    const supportsInlinePreview = canPreviewInline(doc.mime_type)

    return (
        <div>
            <Space style={{marginBottom:16}} wrap>
                <Link to="/documents"><Button icon={<ArrowLeftOutlined/>}>返回文档列表</Button></Link>
                <Button icon={<DownloadOutlined/>} href={downloadUrl} target="_blank" rel="noreferrer">
                    下载
                </Button>
                {supportsInlinePreview?(<Button icon={<EyeOutlined/>} href={previewUrl} target="_blank" rel="noreferrer">
                    新窗口打开
                </Button>):null}
                {canRetry?(<Button icon={<RedoOutlined/>} 
                loading={retryMutation.isPending} 
                onClick={()=>retryMutation.mutate()}>
                    重试解析
                </Button>):null}
                <Popconfirm 
                    title="确认删除文档？"
                    description="将同时删除文档内容、所有切片及云端原文件，无法恢复。"
                    okText="删除"
                    okButtonProps={{danger:true}}
                    cancelText="取消"
                    disabled={!canDelete}
                    onConfirm={()=> deleteMutation.mutate()}>
                        <Button
                            danger
                            icon={<DeleteOutlined></DeleteOutlined>}
                            disabled={!canDelete}
                            loading={deleteMutation.isPending}>
                            删除
                        </Button>
                </Popconfirm>
            </Space>
            <Title level={3} style={{marginBottom:16}}>{doc.name}</Title>
            {doc.status === 'failed' && doc.error_message ?(
                <Alert
                    type="error"
                    message =  "入库失败"
                    description={doc.error_message}
                    showIcon
                    style={{ marginBottom:16 }}></Alert>
            ):null}
            <Descriptions bordered column={1} size='middle' style={{marginBottom:24}}>
                <Descriptions.Item label="状态">
                    <Tag color={getStatusColor(doc.status)}>{getStatusLabel(doc.status)}</Tag>
                </Descriptions.Item>
                <Descriptions.Item label="ID">{doc.id}</Descriptions.Item>
                <Descriptions.Item label="文件hash">{doc.file_hash}</Descriptions.Item>
                <Descriptions.Item label="MIME类型">{doc.mime_type}</Descriptions.Item>
                <Descriptions.Item label="大小">{formatSize(doc.size)}</Descriptions.Item>
                <Descriptions.Item label="上传时间">{new Date(doc.created_at).toLocaleString('zh-CN')}</Descriptions.Item>
                <Descriptions.Item label="更新时间">{new Date(doc.updated_at).toLocaleString('zh-CN')}</Descriptions.Item>
            </Descriptions>
            <Card title="原文预览" style={{ marginBottom:24 }}>
                <PreviewArea mime_type={doc.mime_type} previewUrl={previewUrl}></PreviewArea>
            </Card>
            <Card title="切分结果">
                <ChunksSection 
                docStatus={doc.status}
                chunksQuery={chunksQuery}
                page={chunkPage}
                onPageChange={setChunkPage}
                onPickChunk={setActivChunkID}></ChunksSection>
            </Card>
            <Modal
                title="Chunk 完整内容"
                open={!!activChunkID}
                onCancel={()=>setActivChunkID(null)}
                footer={null}
                width={720}
            >
                {chunkDetailQuery.isLoading?(
                    <Skeleton active/>
                ):chunkDetailQuery.data?(<ChunkDetailBody chunk={chunkDetailQuery.data}></ChunkDetailBody>):null}
            </Modal>
        </div>
    )
 }
