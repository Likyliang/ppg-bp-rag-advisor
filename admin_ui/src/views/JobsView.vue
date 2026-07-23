<script setup lang="ts">
import { inject, onMounted, ref, type Ref } from "vue";
import { api, jsonBody } from "../api";
const user=inject<Ref<any>>("adminUser")!;const rows=ref<any[]>([]), events=ref<Record<string,any[]>>({}), error=ref("");
const reviewerJobTypes=new Set(["quality_gate","retrieval_evaluation","report_evaluation","api_experiment","kb_audit"]);
function canRetry(row:any){return user.value.role==='admin'||(user.value.role==='reviewer'&&reviewerJobTypes.has(row.job_type));}
async function load(){const result=await api<any>("/api/v1/admin/jobs");rows.value=result.jobs;}
async function retry(id:string){await api(`/api/v1/admin/jobs/${id}/retry`,{method:"POST"});await load();}
async function cancel(id:string){await api(`/api/v1/admin/jobs/${id}/cancel`,{method:"POST"});await load();}
async function loadEvents(id:string){const result=await api<any>(`/api/v1/admin/jobs/${id}/events`);events.value[id]=result.events;}
onMounted(()=>load().catch(e=>error.value=e.message));
</script>
<template><h1 class="page-title">任务中心</h1><div class="alert">独立 worker 启动命令：<code>python -m app.admin.worker</code>。知识库、全文索引和质量门按资源锁执行；任务参数只来自服务端白名单。</div><div v-if="error" class="error">{{error}}</div><button class="btn" @click="load">刷新</button><section class="card" style="margin-top:10px"><table><thead><tr><th>任务</th><th>状态/进度</th><th>时间</th><th>日志 / 事件</th><th>操作</th></tr></thead><tbody><tr v-for="row in rows" :key="row.id"><td>{{row.job_type}}<br><code>{{row.id}}</code><br><span class="muted">锁：{{row.resource_lock}} · 第 {{row.attempt}} 次</span></td><td><span class="badge" :class="row.status">{{row.status}}</span> {{row.progress}}%</td><td>{{row.created_at}}<br><span class="muted">{{row.error_code}}</span></td><td><details><summary>脱敏日志</summary><pre class="code">{{row.log_tail}}</pre></details><button class="btn" @click="loadEvents(row.id)">加载事件</button><div v-for="event in events[row.id]||[]" :key="event.sequence" class="muted">{{event.created_at}} · {{event.level}} · {{event.message}}</div></td><td><button class="btn" v-if="['failed','cancelled','interrupted'].includes(row.status) && canRetry(row)" @click="retry(row.id)">重试</button><button class="btn danger" v-if="['queued','running','cancelling'].includes(row.status) && user.role==='admin'" @click="cancel(row.id)">{{row.status==='queued'?'取消':'终止进程'}}</button></td></tr></tbody></table></section>
</template>
