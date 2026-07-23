<script setup lang="ts">
import { inject, onMounted, ref, type Ref } from "vue";
import { api, jsonBody } from "../api";
const user=inject<Ref<any>>("adminUser")!;
const data=ref<any>(null), message=ref(""), error=ref("");
async function load(){data.value=await api("/api/v1/admin/quality/runs");}
async function run(job_type:string){const row=await api<any>("/api/v1/admin/jobs",{method:"POST",body:jsonBody({job_type,parameters:{}})});message.value=`任务 ${row.id} 已排队`;}
onMounted(()=>load().catch(e=>error.value=e.message));
</script>
<template><h1 class="page-title">质量评测</h1><div class="alert">主检索质量使用 calibrated_query_only；metadata_filter_safety 只表示元数据过滤安全。两者均不验证 PPG 血压估算准确性。</div><div v-if="error" class="error">{{error}}</div><div v-if="message" class="alert">{{message}}</div>
  <div class="toolbar" v-if="['admin','reviewer'].includes(user.role)"><button class="btn primary" @click="run('quality_gate')">运行严格质量门</button><button class="btn" @click="run('retrieval_evaluation')">检索评测</button><button class="btn" @click="run('report_evaluation')">报告评测</button><button class="btn" @click="run('api_experiment')">匿名 API 实验</button></div>
  <div v-if="data" class="grid two"><section class="card"><h3>Calibrated query-only（主指标）</h3><pre class="code">{{JSON.stringify(data.trust_calibration?.retrieval_summary||{},null,2)}}</pre></section><section class="card"><h3>Metadata filter safety（安全检查）</h3><pre class="code">{{JSON.stringify(data.trust_calibration?.metadata_filter_safety_summary||{},null,2)}}</pre></section><section class="card"><h3>严格质量门</h3><pre class="code">{{JSON.stringify({passed:data.quality_gate?.passed,criteria:data.quality_gate?.criteria,metrics:data.quality_gate?.metrics},null,2)}}</pre></section><section class="card"><h3>性能</h3><pre class="code">{{JSON.stringify(data.benchmark||{},null,2)}}</pre></section></div>
</template>
