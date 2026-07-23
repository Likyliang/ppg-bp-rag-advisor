<script setup lang="ts">
import { inject, onMounted, ref, type Ref } from "vue";
import { api, jsonBody } from "../api";
const user=inject<Ref<any>>("adminUser")!;
const items = ref<any[]>([]), manifests = ref<any>({}), message = ref(""), error = ref("");
const jobs = [
  ["rescreen","重新筛选来源"], ["ingest_chunks","重建摘要 chunks + 哈希向量"], ["build_chroma","重建 Chroma / BGE"],
  ["build_fulltext","重建本地全文切块/哈希向量"], ["build_openai_processed","构建 OpenAI 摘要 Embedding"], ["build_openai_fulltext","构建 OpenAI 全文 Embedding"],
];
async function load(){ try { const f=await api<any>("/api/v1/admin/freshness"); items.value=f.items; manifests.value=await api("/api/v1/admin/manifests"); } catch(e){error.value=(e as Error).message;} }
async function enqueue(job_type:string){ const row=await api<any>("/api/v1/admin/jobs",{method:"POST",body:jsonBody({job_type,parameters:{}})}); message.value=`任务 ${row.id} 已排队，请启动 worker`; await load(); }
onMounted(load);
</script>
<template><h1 class="page-title">知识库与索引</h1><div v-if="error" class="error">{{error}}</div><div v-if="message" class="alert">{{message}}</div>
  <div class="grid cards"><div class="card" v-for="item in items" :key="item.artifact"><h3>{{item.label}}</h3><span class="badge" :class="item.status">{{item.status}}</span><p class="muted">{{JSON.stringify(item.details)}}</p></div></div>
  <section class="card" style="margin-top:14px"><h3>允许的构建任务</h3><div class="toolbar" v-if="user.role==='admin'"><button class="btn" v-for="job in jobs" :key="job[0]" @click="enqueue(job[0])">{{job[1]}}</button></div><p v-else class="muted">当前角色只读；构建任务仅管理员可创建。</p><p class="muted">任务只接受服务端白名单参数；OpenAI 与本地 Chroma/BGE 是两个明确独立的构建任务。</p></section>
  <section class="card" style="margin-top:14px"><h3>清单摘要</h3><pre class="code">{{JSON.stringify(manifests,null,2)}}</pre></section>
</template>
