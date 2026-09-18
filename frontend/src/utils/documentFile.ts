import { getAuthToken } from "@/stores/authStore"

const MARKDOWN_MIMES = new Set([
    'text/markdown',
    'text/x-markdown',
    'text/plain',
])

const PREVIEWABLE_MIMES = new Set([
    'application/pdf',
    'text/html',
    'application/xhtml+xml',
    ...MARKDOWN_MIMES,
])

//构建发给后端的请求，download 1 是强制下载
export function buildDocumentFileUrl(documentId:string,options:{download?:boolean}={}):string{
    const param = options.download?'1':'0'
  const token = getAuthToken()
  const base = `/api/documents/${documentId}/file?download=${param}`
  return token ? `${base}&token=${encodeURIComponent(token)}` : base
}

export function canPreviewInline(mime_type:string):boolean{
    return PREVIEWABLE_MIMES.has(mime_type)
}

export function isMarkdownMime(mime_type:string):boolean{
    return MARKDOWN_MIMES.has(mime_type)
}

export function isPdfMime(mime_type:string):boolean{
    return mime_type === 'application/pdf'
}
export function isHtmlMime(mime_type:string):boolean{
    return mime_type === 'text/html' || mime_type === 'application/xhtml+xml'
} 