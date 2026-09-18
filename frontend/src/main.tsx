import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntdApp,ConfigProvider } from 'antd'
import { RouterProvider } from 'react-router-dom'
import zhCN from 'antd/locale/zh_CN'
import './index.css'
import { router } from './routes/index.tsx'
import './api/client.ts'
import {useAuthStore } from '@/stores/authStore'

useAuthStore.getState().hydrate()
const queryClient = new QueryClient({
  defaultOptions:{
    queries:{
      retry:1,
      staleTime:30_000,
      refetchOnWindowFocus:false,
    }
  }
})

const root = document.getElementById('root')
if (!root) throw new Error('root element not found')
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider locale={zhCN} theme={{token:{ colorPrimary:'#1677ff'}}}>
      <AntdApp>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router}/>
      </QueryClientProvider>
      </AntdApp>
    </ConfigProvider>
  </StrictMode>,
)
