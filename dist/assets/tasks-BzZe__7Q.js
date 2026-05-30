import{a9 as g,k as c,a0 as f,aY as w}from"./index-B4ZF2GRA.js";/**
 * @license lucide-vue-next v0.378.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const k=t=>t.replace(/([a-z0-9])([A-Z])/g,"$1-$2").toLowerCase();/**
 * @license lucide-vue-next v0.378.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */var u={xmlns:"http://www.w3.org/2000/svg",width:24,height:24,viewBox:"0 0 24 24",fill:"none",stroke:"currentColor","stroke-width":2,"stroke-linecap":"round","stroke-linejoin":"round"};/**
 * @license lucide-vue-next v0.378.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const h=({size:t,strokeWidth:e=2,absoluteStrokeWidth:i,color:n,iconNode:l,name:p,class:a,...s},{slots:r})=>g("svg",{...u,width:t||u.width,height:t||u.height,stroke:n||u.stroke,"stroke-width":i?Number(e)*24/Number(t):e,class:["lucide",`lucide-${k(p??"icon")}`],...s},[...l.map(o=>g(...o)),...r.default?[r.default()]:[]]);/**
 * @license lucide-vue-next v0.378.0 - ISC
 *
 * This source code is licensed under the ISC license.
 * See the LICENSE file in the root directory of this source tree.
 */const I=(t,e)=>(i,{slots:n})=>g(h,{...i,iconNode:e,name:t},n),d={list:t=>c.get("/api/tasks",{params:t}),create:t=>c.post("/api/tasks",t),update:(t,e)=>c.patch(`/api/tasks/${t}`,e),remove:t=>c.delete(`/api/tasks/${t}`)},m=!1,O=[{id:1,title:"Перезвонить инженеру АгроХолдинг-Юг",status:"todo",priority:"high",due_date:new Date(Date.now()+864e5).toISOString(),tags:["клиент","звонок"],created_at:new Date().toISOString(),updated_at:new Date().toISOString()},{id:2,title:"Подготовить ТЭО для завода Сибмаш",status:"in_progress",priority:"urgent",description:"Расчёт ROI замены подшипников на линии №3",tags:["ТЭО"],created_at:new Date().toISOString(),updated_at:new Date().toISOString()},{id:3,title:"Согласовать счёт №2041",status:"blocked",priority:"medium",tags:["счёт"],created_at:new Date().toISOString(),updated_at:new Date().toISOString()},{id:4,title:"Отправить КП клиенту Норильск-Логистик",status:"done",priority:"medium",tags:["КП"],created_at:new Date().toISOString(),updated_at:new Date().toISOString()}],_=f("tasks",()=>{const t=w([]),e=w(!1);async function i(a){e.value=!0;try{if(!m){const{data:s}=await d.list(a);t.value=s}return t.value}finally{e.value=!1}}async function n(a){const{data:s}=await d.create(a);return t.value.unshift(s),s}async function l(a,s){const{data:r}=await d.update(a,s),o=t.value.find(S=>S.id===a);return o&&Object.assign(o,r),r}async function p(a){await d.remove(a),t.value=t.value.filter(s=>s.id!==a)}return{items:t,loading:e,list:i,create:n,update:l,remove:p}});export{I as c,_ as u};
