import { client } from "../client/client.gen";
import {message} from 'antd'
import { formatApiError } from "../utils/error";

client.setConfig({
    baseUrl:'',
    throwOnError:true
})

client.interceptors.response.use(async (response)=>{
    if (!response.ok){
        message.error(await formatApiError(response))
    }
    return response
})  