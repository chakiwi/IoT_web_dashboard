export type ScanEvent = {
  id:number;event_id:string;card_uid:string;result:'recognized'|'unregistered'|'inactive_card';
  station_id:string;station_name:string;station_location:string;student_code:string|null;
  full_name:string|null;class_name:string|null;occurred_at:string;received_at:string;
};
export type Student = {id:number;student_code:string;full_name:string;class_name:string;email:string|null;
  is_active:number;card_uid:string|null;card_active:number|null;last_station_id:string|null;last_scan_at:string|null};
export type Station = {id:string;station_name:string;location:string;is_enabled:number;
  is_online:boolean;last_seen_at:string|null;last_ip:string|null;scan_count:number};
export type Stats = {students:number;scans_today:number;recognized_today:number;flagged_today:number;
 registered_rate:number;stations_online:number;stations_total:number;server_time:string};
export type Config = {demo_mode:boolean;database:string;api:string;transport:string[];timezone:string;server_time:string};
export async function request<T>(url:string, token:string|null, options:RequestInit={}):Promise<T>{
  const headers:Record<string,string>={};
  if(options.body) headers['Content-Type']='application/json';
  if(token)headers['Authorization']='Bearer '+token;
  const response=await fetch(url,{...options,headers:{...headers,...options.headers},cache:'no-store'});
  if(!response.ok){
    const body=await response.json().catch(()=>({}));
    const reason=typeof body.detail==='string'?body.detail:response.status+' '+response.statusText;
    const error=new Error(reason) as Error & {status?:number};error.status=response.status;throw error;
  }
  return response.json() as Promise<T>;
}
export function fmtTime(value:string|null|undefined,full=false){
 if(!value)return '—';
 try{return new Intl.DateTimeFormat('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit',second:'2-digit',...(full?({day:'2-digit',month:'2-digit',year:'numeric'} as const):{})}).format(new Date(value));}
 catch{return value;}
}
