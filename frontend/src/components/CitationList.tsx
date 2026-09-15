import type { CitationRead } from "@/client";
import { Collapse, Tag, Typography } from "antd";
import { forwardRef, useImperativeHandle, useState } from "react";
import { Link } from "react-router-dom";

const {Paragraph} = Typography
type SourceTagMeta = {color:string;label:string}

export interface CitationListHandle{
    expandAndScroll:(n:number) =>void
}

interface CitationListProps{
    citations:CitationRead[]
    messageId:string
}

//生成锚点，通过messageID和引用编号
function anchorId(messageId:string,n:number):string{
    return `cite-${messageId}-${n}`
}

// 有ID返回ID，没有ID返回ordinal
function panelKey(c:CitationRead):string{
    return c.id||`ord-${c.ordinal}`
}

function formatSourceTag(sources?:string[]):SourceTagMeta|null{
    if (!sources || sources.length === 0) return null
    const hasVector = sources.includes('vector')
    const hasKeyword = sources.includes('keyword')
    if (hasKeyword&&hasVector) return {color:'purple',label:'混和'}
    if (hasVector) return {color:'blue',label:'向量'}
    if (hasKeyword) return {color:'orange',label:'关键词'}
    return null
}

//定义了一个可以接收CitationListProps参数，并且允许父组件通过REF调用特定功能的组件
export const CitationList = forwardRef<CitationListHandle,CitationListProps>(
    function CitationList ({citations,messageId},ref){
        const [activeKey,setActiveKey]= useState<string[]>([])
        useImperativeHandle(
            ref,()=>({
                expandAndScroll:(n:number)=>{
                    const target = citations.find((c)=>c.ordinal === n)
                    if (!target) return
                    const key = panelKey(target)
                    //为了保持上一个展开的面板，prev里面时当前的activeKey
                    // 这句话时如果prev里面已经有了数据就保持不变，不存在就添加到数组末尾
                    setActiveKey((prev)=>(prev.includes(key)?prev:[...prev,key]))
                    requestAnimationFrame(()=>{
                        document.getElementById(anchorId(messageId,n))
                        ?.scrollIntoView({behavior:'smooth',block:'center'})
                    })
                }
            }),[citations,messageId]
        )

        if(citations.length===0) return null
        const items = citations.map((c)=>{
            const sourceTag = formatSourceTag(c.retrieval_meta?.sources)
            const rerankScore = c.retrieval_meta?.rerank_score
            return {
                key:panelKey(c),
                label:(
                    <span id={anchorId(messageId,c.ordinal)}>
                        <Tag color="blue" style={{ marginInlineEnd:8}}>{`[${c.ordinal}]`}</Tag>
                        {sourceTag?(
                            <Tag color={sourceTag.color} style={{ marginInlineEnd:8}}>
                                {sourceTag.label}
                            </Tag>
                        ):null}
                        {rerankScore!=null ?(
                            <Tag color="gold" style={{ marginInlineEnd:8}}>
                                {`rerank ${rerankScore.toFixed(2)}`}
                            </Tag>
                        ):null}
                        {c.document_id?(<Link to={`/documents/${c.document_id}`}>{c.document_name}</Link>)
                        :(<span>{c.document_name}</span>)}
                        {c.page_no!=null?(
                            <span style={{marginInlineStart:8,color:'#999'}}>第{c.page_no}页</span>
                        ):null}
                    </span>
                ),
                children:(
                    <Paragraph
                    style={{whiteSpace:'pre-wrap',marginBottom:0,color:'#555'}}
                    ellipsis={{rows:6,expandable:true,symbol:'展开'}}>
                        {c.quote}
                    </Paragraph>
                ), }
        })
   

        return (
            <Collapse
                size="small"
                ghost
                items={items}
                activeKey={activeKey}
                onChange={(keys)=>setActiveKey(typeof keys === 'string'?[keys]:keys)}
                style={{marginTop:12,background:'#fafafa',borderRadius:6}}
                />
        )
    }
    )
