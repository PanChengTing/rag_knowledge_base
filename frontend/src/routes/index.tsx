import { createBrowserRouter } from 'react-router-dom'
import { BasicLayout } from '../layouts/BasicLayout'
import { HomePage } from '../pages/HomePage'
import { DocumentsPage } from '@/pages/DocumentsPage'
import { DocumentsDetailPage } from '@/pages/DocumentsDetailPage'
import { ChatPage } from '@/pages/ChatPage'

export const router = createBrowserRouter([{
    path:'/',
    element:<BasicLayout/>,
    children:[{index:true,element:<HomePage/>},
        {path:'documents',element:<DocumentsPage/>},
        {path:'chat',element:<ChatPage/>},
        {path:'documents/:id',element:<DocumentsDetailPage/> }]
}])