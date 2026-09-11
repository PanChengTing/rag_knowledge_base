import { Collapse, Tag, Typography } from "antd";
import type {QueryRouteRead} from '@/client/types.gen'
import type React from "react";

const {Paragraph,Text} = Typography

const ROUTE_META:Record<QueryRouteRead['route'],{color:string;label:string;hint:string}>
={
    original:{color:'default',label:'Original',hint:'问题清晰，无需修改'},
    rewrite:{color:'blue',label:'Rewrite',hint:'已改写为独立完整问题'},
    hyde:{color:'purple',label:'Hyde',hint:'已生成假设答案用于检索'},
    multi_query:{color:'orange',label:'Multi_Query',hint:'已扩展为多个子查询'},
}

interface QueryRoutePanelProps{
    queryRoute:QueryRouteRead
}

function DetailRow({label,children}:{label:string;children:React.ReactNode}){
    return (
        <div>
            <Text strong style={{fontSize:12,color:'#888'}}>
                {label}
            </Text>
            <div style={{marginTop:4}}>{children}</div>
        </div>
    )
}

const paragraphStyle:React.CSSProperties ={
    whiteSpace:'pre-wrap',
    marginBottom:0,
    color:'#555'
}

function RouteDetail({queryRoute}:{queryRoute:QueryRouteRead}){
    switch (queryRoute.route){
        case "rewrite":
            return (
                <DetailRow label ="改写后的查询">
                    <Paragraph style={paragraphStyle}>{queryRoute.rewritten_query}</Paragraph>
                </DetailRow>
            )
        case "hyde":
            return (
                <DetailRow label ="假设答案">
                    <Paragraph style={paragraphStyle}>{queryRoute.hyde_answer}</Paragraph>
                </DetailRow>
            )
        case "multi_query":
            return (
                <DetailRow label ="子查询列表">
                    <ol style={{paddingInlineStart:20,margin:0,color:'#555'}}>
                        {(queryRoute.multi_querys ?? []).map((q,i)=>(
                            <li key={i} style={{marginBottom:4}}>{q}</li>
                        ))}

                    </ol>
                </DetailRow>
            )
        default:
            return null
    }
}

export function QueryRoutePanel({queryRoute}:QueryRoutePanelProps){
    if (queryRoute.route === 'original') return null
    const meta = ROUTE_META[queryRoute.route]

    return (
        <Collapse
            size="small"
            ghost
            style={{ marginTop:12,background:'#fafafa',borderRadius:6}}
            items={[
                {
                    key:'route',
                    label:(
                        <span>
                            <Tag color={meta.color} style={{ marginInlineEnd:8}}>
                                {meta.label}
                            </Tag>
                        </span>
                    ),
                    children:<RouteDetail queryRoute={queryRoute}/>
                },
            ]}
        />
    )
}